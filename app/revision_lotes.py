"""Tablas de revisión humana para clubes y fichas existentes."""
import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from services import revision_lotes as servicio
from services import resultados_importados
from services.deportistas import ValidacionError, ConflictoError


SIN_CLUB = 'Dejar pendiente'
ROLES = {'Patron': 'Patrón', 'Tripulante': 'Tripulante'}


def mostrar(proveedor, motor, lectura, revision, clubes, al_guardar, datos_regata=None):
    identificador = revision['importacion']['id_importacion']
    if revision['importacion']['estado'] not in ('recibida', 'extraida', 'en_revision', 'parcialmente_importada'):
        return
    version = resultados_importados.version_resultados(revision)
    try:
        resumen = lectura((proveedor, 'revision_lotes', identificador, version), servicio.cargar_resumen, motor, identificador)
    except (SQLAlchemyError, KeyError, OSError, ValidacionError):
        st.warning('No se pudieron preparar las tablas de revisión conjunta. Puedes continuar con el formulario individual o actualizar la revisión.')
        return
    prefijo = f'revision_lotes_{proveedor}_{identificador}_{resumen["version"][:12]}'
    with st.expander('1. Resolver clubes del documento', expanded=bool(resumen['grupos_club'])):
        _clubes(proveedor, identificador, resumen['grupos_club'], clubes, prefijo, al_guardar)
    with st.expander('2. Vincular participantes en una tabla', expanded=bool(resumen['propuestas'])):
        _participantes(proveedor, identificador, resumen, revision['importacion']['numero_tripulantes'], clubes, prefijo, al_guardar, datos_regata)
    nuevas = [r for r in resumen['propuestas'] if r['coincidencias'] == 0 and r['participante']['id_club_identificado'] is not None]
    if nuevas and datos_regata is not None:
        with st.expander('3. Crear fichas sin DNI e incorporar resultados'):
            _nuevos(proveedor, identificador, resumen, nuevas, revision['importacion']['numero_tripulantes'], clubes,
                    prefijo, al_guardar, datos_regata)


def _guardar(proveedor, operacion, identificador, decisiones, version, al_guardar, datos_regata=None):
    try:
        if datos_regata is None:
            salida = servicio.guardar_en_proveedor(proveedor, operacion, identificador, decisiones, version)
        else:
            salida = servicio.guardar_en_proveedor(proveedor, operacion, identificador, decisiones, version, datos_regata)
    except (ValidacionError, ConflictoError) as error:
        st.error(str(error))
    except (SQLAlchemyError, KeyError, OSError):
        st.error('No se pudo confirmar el lote. Actualiza la revisión para comprobar su estado antes de reintentar.')
    else:
        if operacion == 'clubes':
            al_guardar(f'{salida["clubes"]} clubes confirmados para {salida["participantes"]} participantes pendientes. Las propuestas se han actualizado.')
        elif operacion == 'vinculos_resultados':
            al_guardar(f'{salida["vinculados"]} fichas vinculadas y {salida["resultados_incorporados"]} resultados incorporados. Ya puedes consultarlos en las fichas.')
        elif operacion == 'altas_resultados':
            al_guardar(f'{salida["creados"]} fichas creadas con identificador provisional y {salida["resultados_incorporados"]} resultados incorporados. El DNI se puede completar en Gestión de deportistas.')
        else:
            al_guardar(f'{salida["vinculados"]} fichas vinculadas. Hay {salida["resultados_preparados"]} resultados preparados; puedes incorporarlos en la sección de resultados revisados.')


def _clubes(proveedor, identificador, grupos, clubes, prefijo, al_guardar):
    st.caption('Confirma un club una vez para todos los participantes pendientes que comparten ese texto. '
               'Los participantes ya confirmados y las filas importadas o excluidas se conservan. Si falta el texto del club, revísalo individualmente.')
    if not grupos:
        st.info('No hay textos de clubes pendientes para resolver conjuntamente.')
        return
    nombres = [f'{c["nombre"]} · {c["federacion"]}' for c in clubes]
    etiquetas = {c['id_club']: nombre + (f' · registro {c["id_club"]}' if nombres.count(nombre)>1 else '')
                 for c, nombre in zip(clubes, nombres)}
    por_etiqueta = {v: k for k, v in etiquetas.items()}
    mapa = {g['normalizado']: g for g in grupos}
    todos = st.checkbox('Seleccionar todos los clubes propuestos', key=prefijo+'_todos_clubes')
    marco = pd.DataFrame([{'Confirmar': bool(todos and g['id_club_propuesto'] in etiquetas), 'Club en la fuente': ' / '.join(g['textos']),
        'Participantes pendientes': len(g['participantes']),
        'Club identificado': etiquetas.get(g['id_club_propuesto'], SIN_CLUB),
        'Motivo de la propuesta': g['motivo'], 'Recordar equivalencia': False}
        for g in grupos], index=list(mapa))
    editado = st.data_editor(marco, hide_index=True, width='stretch', num_rows='fixed',
        key=prefijo+'_clubes', disabled=['Club en la fuente', 'Participantes pendientes', 'Motivo de la propuesta'],
        column_config={'Confirmar': st.column_config.CheckboxColumn('Confirmar'),
                       'Club identificado': st.column_config.SelectboxColumn('Club identificado', options=[SIN_CLUB]+list(por_etiqueta), required=True),
                       'Recordar equivalencia': st.column_config.CheckboxColumn('Recordar equivalencia',
                           help='Guarda esta abreviatura para proponer el mismo club en otras clasificaciones. No se reemplazan equivalencias previas.')})
    st.caption('Deja sin seleccionar los clubes que necesiten revisión. Recordar equivalencia es opcional: úsalo solo cuando la abreviatura identifique al club en futuras clasificaciones.')
    confirmar = st.checkbox('He revisado los clubes seleccionados y las equivalencias que se recordarán.', key=prefijo+'_confirmar_clubes')
    seleccionadas = editado[editado['Confirmar'] == True]
    if st.button('Confirmar clubes seleccionados', disabled=seleccionadas.empty or not confirmar,
                 key=prefijo+'_guardar_clubes'):
        decisiones = []
        for normal, fila in seleccionadas.iterrows():
            if fila['Club identificado'] not in por_etiqueta:
                st.error('Selecciona un club para cada fila marcada o déjala sin seleccionar.')
                return
            decisiones.append(dict(normalizado=normal, id_club=por_etiqueta[fila['Club identificado']],
                recordar=bool(fila['Recordar equivalencia']), version=mapa[normal]['version']))
        _guardar(proveedor, 'clubes', identificador, decisiones, None, al_guardar)


def _participantes(proveedor, identificador, resumen, tripulantes, clubes, prefijo, al_guardar, datos_regata=None):
    st.caption('Puedes seleccionar todas las coincidencias propuestas y desmarcar las que no correspondan. Comprueba nombre, club y nacimiento. '
               'Las identidades ambiguas, las búsquedas de otra ficha y las altas nuevas se resuelven en el formulario individual de abajo.')
    propuestas = [r for r in resumen['propuestas'] if r['propuesta'] is not None]
    if not propuestas:
        st.info('No hay fichas existentes propuestas para vincular. Las altas nuevas aparecen en Crear fichas sin DNI; las coincidencias dudosas pueden revisarse individualmente.')
        return
    mapa = {r['participante']['id_participante_importado']: r for r in propuestas}
    nombres_club = {c['id_club']: c['nombre'] for c in clubes}
    todos = st.checkbox('Seleccionar todas las coincidencias propuestas', key=prefijo+'_todos_participantes')
    filas = []
    for r in propuestas:
        p, ficha = r['participante'], r['propuesta']
        filas.append({'Vincular': bool(todos and ficha), 'Puesto': p['fila']['posicion_general'],
            'Puntos': p['fila']['puntos'],
            'Nombre en la fuente': p['nombre_original'], 'Club en la fuente': p['club_original'],
            'Club identificado en fuente': nombres_club.get(p['id_club_identificado']),
            'Ficha propuesta': f'{ficha["nombre"]} {ficha["apellidos"]} · {ficha["dni"]}' if ficha else 'Revisión individual',
            'Club de la ficha': ficha['club'] if ficha else None,
            'Nacimiento de la ficha': ficha['fecha_nacimiento'] if ficha else None,
            'Motivos': r['motivo'], 'Rol': 'Patrón' if tripulantes == 1 else ROLES.get(p['rol_propuesto'])})
    marco = pd.DataFrame(filas, index=list(mapa))
    editado = st.data_editor(marco, hide_index=True, width='stretch', num_rows='fixed',
        key=prefijo+'_participantes', disabled=[c for c in marco if c not in (('Vincular', 'Rol') if tripulantes == 2 else ('Vincular',))],
        column_config={'Vincular': st.column_config.CheckboxColumn('Vincular'),
            'Rol': st.column_config.SelectboxColumn('Rol', options=list(ROLES.values())),
            'Nacimiento de la ficha': st.column_config.DateColumn('Nacimiento de la ficha', format='DD/MM/YYYY')})
    if tripulantes == 2:
        st.caption('En clases dobles debes confirmar el rol de cada miembro. Una tripulación completa necesita un patrón y un tripulante.')
    incorporar = False
    if datos_regata is not None:
        incorporar = st.checkbox('Vincular e incorporar los resultados en este paso', value=True, key=prefijo+'_incorporar')
        st.caption('Se utilizarán los Datos de la regata indicados arriba. En clases dobles deben estar completos ambos miembros y sus roles. Si hay un conflicto, no se guarda ninguna parte del lote.')
    else:
        st.caption('Este paso vincula identidades y prepara los resultados para su incorporación posterior.')
    confirmar = st.checkbox('Confirmo que cada ficha seleccionada corresponde al participante de su fila.', key=prefijo+'_confirmar_vinculos')
    if incorporar:
        confirmar = st.checkbox('He revisado los datos de la regata, puestos y puntos del lote.', key=prefijo+'_confirmar_resultados') and confirmar
    seleccionadas = editado[editado['Vincular'] == True]
    etiqueta = 'Vincular e incorporar resultados seleccionados' if incorporar else 'Confirmar vinculaciones seleccionadas'
    if st.button(etiqueta, type='primary', disabled=seleccionadas.empty or not confirmar,
                 key=prefijo+'_guardar_vinculos'):
        decisiones = []
        for ident, fila in seleccionadas.iterrows():
            ficha = mapa[ident]['propuesta']
            if not ficha:
                st.error('Una fila seleccionada necesita revisión individual. Déjala sin marcar y utiliza el formulario inferior.')
                return
            rol = next((k for k, v in ROLES.items() if fila['Rol'] == v), None)
            if rol is None:
                st.error('Confirma el rol de los miembros seleccionados antes de guardar.')
                return
            decisiones.append(dict(participante=int(ident), dni=ficha['dni'],
                version_ficha=ficha['version_ficha'], rol=rol))
        _guardar(proveedor, 'vinculos_resultados' if incorporar else 'vinculos', identificador, decisiones,
                 resumen['version'], al_guardar, datos_regata if incorporar else None)


def _nuevos(proveedor, identificador, resumen, nuevas, tripulantes, clubes, prefijo, al_guardar, datos_regata):
    st.caption('Solo se ofrecen altas sin fichas similares y con el club confirmado. Revisa la separación de nombres y apellidos. '
               'Se asignará un identificador TEMP- a cada ficha; no es un DNI. El nacimiento desconocido seguirá sin registrar. '
               'Los Datos de la regata indicados arriba se usarán para incorporar los resultados.')
    todos = st.checkbox('Seleccionar todas las altas propuestas', key=prefijo+'_todas_altas')
    nombres_club = {c['id_club']: c['nombre'] for c in clubes}
    filas, mapa = [], {}
    for r in nuevas:
        p = r['participante']
        ident = p['id_participante_importado']
        mapa[ident] = r
        partes = p['nombre_original'].split(' ', 1)
        filas.append({'Crear': todos, 'Puesto': p['fila']['posicion_general'], 'Puntos': p['fila']['puntos'],
            'Nombre en la fuente': p['nombre_original'], 'Nombre': p['nombre_propuesto'] or partes[0],
            'Apellidos': p['apellidos_propuestos'] or (partes[1] if len(partes)>1 else ''),
            'Club': nombres_club.get(p['id_club_identificado']),
            'Rol': 'Patrón' if tripulantes==1 else ROLES.get(p['rol_propuesto'])})
    marco = pd.DataFrame(filas, index=list(mapa))
    editado = st.data_editor(marco, hide_index=True, width='stretch', num_rows='fixed', key=prefijo+'_altas',
        disabled=['Puesto','Puntos','Nombre en la fuente','Club'] + (['Rol'] if tripulantes==1 else []),
        column_config={'Crear': st.column_config.CheckboxColumn('Crear'),
                       'Rol': st.column_config.SelectboxColumn('Rol', options=list(ROLES.values()))})
    confirmar = st.checkbox('He revisado las altas seleccionadas, los clubes, la regata, los puestos y los puntos.', key=prefijo+'_confirmar_altas')
    elegidas = editado[editado['Crear'] == True]
    if st.button('Crear fichas seleccionadas e incorporar resultados', disabled=elegidas.empty or not confirmar, key=prefijo+'_guardar_altas'):
        decisiones = []
        for ident, fila in elegidas.iterrows():
            r, p = mapa[ident], mapa[ident]['participante']
            rol = next((k for k,v in ROLES.items() if fila['Rol']==v),None)
            if not rol:
                st.error('Confirma el rol de cada miembro antes de crear las fichas.')
                return
            decisiones.append(dict(participante=int(ident), version=r['version'], campos=dict(
                nombre=fila['Nombre'],apellidos=fila['Apellidos'],fecha_nacimiento=p['fecha_nacimiento_propuesta'],
                sexo=p['sexo_propuesto'],id_club=p['id_club_identificado'],rol_propuesto=rol,
                observaciones_revision='Alta por lote revisada; identificador provisional pendiente de DNI.')))
        _guardar(proveedor,'altas_resultados',identificador,decisiones,resumen['version'],al_guardar,datos_regata)
