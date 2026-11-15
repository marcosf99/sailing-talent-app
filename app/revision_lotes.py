"""Tablas de revisión humana para clubes y fichas existentes."""
import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from services import revision_lotes as servicio
from services import resultados_importados
from services.revision_participantes import nombre_inicial
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
    automaticas=set()
    if datos_regata is not None:
        with st.expander('Alta automática de fichas nuevas'):
            automaticas=_automaticos(proveedor,identificador,resumen,revision,prefijo,al_guardar,datos_regata)
    with st.expander('2. Vincular participantes en una tabla', expanded=bool(resumen['propuestas'])):
        _participantes(proveedor, identificador, resumen, revision['importacion']['numero_tripulantes'], clubes, prefijo, al_guardar, datos_regata, revision,automaticas)
    nuevas = [r for r in resumen['propuestas'] if r['coincidencias'] == 0 and r['participante']['id_club_identificado'] is not None]
    if nuevas and datos_regata is not None:
        with st.expander('3. Crear fichas sin DNI e incorporar resultados'):
            _nuevos(proveedor, identificador, resumen, nuevas, revision['importacion']['numero_tripulantes'], clubes,
                    prefijo, al_guardar, datos_regata, revision)


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
            pendientes = salida.get('equipos_pendientes', 0)
            aviso = (f' {pendientes} equipos esperan la identidad del otro miembro; completa sus fichas para incorporar esos resultados.'
                     if pendientes else ' Ya puedes consultarlos en las fichas.')
            al_guardar(f'{salida["vinculados"]} fichas vinculadas y {salida["resultados_incorporados"]} resultados incorporados.' + aviso)
        elif operacion in ('altas_resultados','altas_automaticas'):
            al_guardar(f'{salida["creados"]} fichas creadas con identificador provisional y {salida["resultados_incorporados"]} resultados incorporados. El DNI se puede completar en Gestión de deportistas.')
        else:
            al_guardar(f'{salida["vinculados"]} fichas vinculadas. Hay {salida["resultados_preparados"]} resultados preparados; puedes incorporarlos en la sección de resultados revisados.')


def _automaticos(proveedor,identificador,resumen,revision,prefijo,al_guardar,datos_regata):
    st.caption('Se crearán fichas TEMP- si todas las coincidencias están por debajo del umbral. '
        'El valor es una similitud orientativa, no una probabilidad de identidad. '
        'Se exige nombre y apellidos completos, club identificado y equipo preparado. '
        'Las posibles abreviaturas o apellidos omitidos siguen en revisión aunque tengan una puntuación baja. '
        'La separación de nombre y apellidos es provisional y puede corregirse después en Gestión de deportistas.')
    umbral=st.number_input('Umbral para crear fichas nuevas (similitud inferior)',
        min_value=.65,max_value=.85,value=.75,step=.01,format='%.2f',key=prefijo+'_umbral_altas')
    if umbral>.75:
        st.warning('Subir el umbral crea más fichas nuevas y aumenta el riesgo de duplicados por nombres abreviados o errores. Recomendado para empezar: 0,75.')
    plan=servicio.plan_altas_automaticas(revision,resumen['propuestas'],umbral)
    ids={d['participante'] for d in plan['decisiones']}
    personas={r['participante']['id_participante_importado']:r['participante'] for r in resumen['propuestas']}
    st.write(f"{len(ids)} fichas nuevas preparadas; {len({personas[i]['id_fila'] for i in ids})} resultados se incorporarán.")
    if ids:
        st.dataframe(pd.DataFrame([{'Puesto':personas[i]['fila']['posicion_general'],
            'Nombre en la clasificación':personas[i]['nombre_original'],
            'Similitud máxima':float(plan['maximas'][i])} for i in sorted(ids)]),hide_index=True,width='stretch')
    if plan['pendientes'] and st.checkbox('Mostrar por qué siguen pendientes otros participantes',key=prefijo+'_ver_pendientes_auto'):
        with st.expander('Casos que siguen pendientes',expanded=True):
            st.table(pd.DataFrame([{'Puesto':p['puesto'],'Nombre':p['nombre'],'Motivo':p['motivo']} for p in plan['pendientes']]))
    if st.button('Crear fichas nuevas automáticamente e incorporar resultados',disabled=not ids,key=prefijo+'_guardar_automaticas'):
        _guardar(proveedor,'altas_automaticas',identificador,{'umbral':umbral},resumen['version'],al_guardar,datos_regata)
    return ids


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


def _participantes(proveedor, identificador, resumen, tripulantes, clubes, prefijo, al_guardar, datos_regata=None, revision=None,automaticas=None):
    st.caption('Puedes seleccionar todas las coincidencias propuestas y desmarcar las que no correspondan. Comprueba nombre, club y nacimiento. '
               'Las identidades ambiguas, las búsquedas de otra ficha y las altas nuevas se resuelven en el formulario individual de abajo.')
    automaticas=automaticas or set()
    dudosas = [r for r in resumen['propuestas'] if r['propuesta'] is None and r['coincidencias'] > 0 and r['participante']['id_participante_importado'] not in automaticas]
    if dudosas:
        st.warning('Hay participantes con identidades por comprobar. No se ofrecen como altas automáticas para evitar duplicados.')
        st.table(pd.DataFrame([{
            'Puesto': r['participante']['fila']['posicion_general'],
            'Participante pendiente': r['participante']['nombre_original'],
            'Fichas similares que comprobar': ' / '.join(
                c['nombre'] + ' ' + c['apellidos'] for c in r.get('candidatos', [])),
            'Motivo': r['motivo']} for r in dudosas]))
        st.caption('Activa «Revisar una identidad individual · coincidencias dudosas o correcciones» más abajo. '
                   'Selecciona la persona y, si es distinta de las fichas similares, elige Crear deportista y confirma que es otra persona. '
                   'Revisa ambos miembros antes de incorporar el resultado del equipo.')
    propuestas = [r for r in resumen['propuestas'] if r['propuesta'] is not None and r['participante']['id_participante_importado'] not in automaticas]
    if not propuestas:
        st.info('No hay fichas existentes propuestas para vincular. Las altas nuevas aparecen en Crear fichas sin DNI; las coincidencias dudosas pueden revisarse individualmente.')
        return
    previstas = [dict(participante=r['participante']['id_participante_importado'],
                      campos={'rol_propuesto':r['participante']['rol_propuesto']}) for r in propuestas]
    faltas = servicio.incidencias_altas(revision, previstas) if revision else {}
    mapa = {r['participante']['id_participante_importado']: r for r in propuestas}
    nombres_club = {c['id_club']: c['nombre'] for c in clubes}
    todos = st.checkbox('Seleccionar todas las coincidencias propuestas', key=prefijo+'_todos_participantes')
    filas = []
    for r in propuestas:
        p, ficha = r['participante'], r['propuesta']
        filas.append({'Vincular': bool(todos and ficha),
            'Estado del equipo': faltas.get(p['id_fila'], 'Preparado al confirmar sus miembros'), 'Puesto': p['fila']['posicion_general'],
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
        st.caption('Se vincularán todas las fichas que selecciones y se incorporarán los resultados de los equipos completos. '
                   'Si falta identificar a su pareja, el vínculo se guardará y el resultado quedará pendiente. '
                   'Después podrás crear o vincular al otro miembro. Los conflictos de identidad, roles o resultados revierten el lote.')
    else:
        st.caption('Este paso vincula identidades y prepara los resultados para su incorporación posterior.')
    recordar = st.checkbox('Recordar los nombres seleccionados como variantes de sus fichas', key=prefijo+'_recordar_nombres')
    st.caption('Si marcas esta opción, confirma también el club de la fuente de cada participante seleccionado.')
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
                version_ficha=ficha['version_ficha'], rol=rol, **({'recordar_nombre':True} if recordar else {})))
        _guardar(proveedor, 'vinculos_resultados' if incorporar else 'vinculos', identificador, decisiones,
                 resumen['version'], al_guardar, datos_regata if incorporar else None)


def _nuevos(proveedor, identificador, resumen, nuevas, tripulantes, clubes, prefijo, al_guardar, datos_regata, revision):
    st.caption('Solo se ofrecen altas sin fichas similares y con el club confirmado. Revisa la separación de nombres y apellidos. '
               'Se asignará un identificador TEMP- a cada ficha; no es un DNI. El nacimiento desconocido seguirá sin registrar. '
               'Los Datos de la regata indicados arriba se usarán para incorporar los resultados.')
    previsiones = [dict(participante=r['participante']['id_participante_importado'],
                        campos={'rol_propuesto': r['participante']['rol_propuesto']}) for r in nuevas]
    faltas = servicio.incidencias_altas(revision, previsiones)
    if faltas:
        st.info('Los equipos pendientes quedan sin seleccionar. Puedes guardar los completos y volver después a los demás.')
        for falta in faltas.values():
            st.caption(falta)
    todos = st.checkbox('Seleccionar todas las altas propuestas', key=prefijo+'_todas_altas')
    nombres_club = {c['id_club']: c['nombre'] for c in clubes}
    filas, mapa = [], {}
    for r in nuevas:
        p = r['participante']
        ident = p['id_participante_importado']
        mapa[ident] = r
        nombre,apellidos=nombre_inicial(p)
        filas.append({'Crear': bool(todos and p['id_fila'] not in faltas),
            'Estado del equipo': faltas.get(p['id_fila'], 'Completo para este lote'), 'Puesto': p['fila']['posicion_general'], 'Puntos': p['fila']['puntos'],
            'Nombre en la fuente': p['nombre_original'], 'Nombre': nombre,
            'Apellidos': apellidos,
            'Club': nombres_club.get(p['id_club_identificado']),
            'Rol': 'Patrón' if tripulantes==1 else ROLES.get(p['rol_propuesto'])})
    marco = pd.DataFrame(filas, index=list(mapa))
    editado = st.data_editor(marco, hide_index=True, width='stretch', num_rows='fixed', key=prefijo+'_altas',
        disabled=['Estado del equipo','Puesto','Puntos','Nombre en la fuente','Club'] + (['Rol'] if tripulantes==1 else []),
        column_config={'Crear': st.column_config.CheckboxColumn('Crear'),
                       'Rol': st.column_config.SelectboxColumn('Rol', options=list(ROLES.values()))})
    confirmar = st.checkbox('He revisado las altas seleccionadas, los clubes, la regata, los puestos y los puntos.', key=prefijo+'_confirmar_altas')
    elegidas = editado[editado['Crear'] == True]
    decisiones = []
    for ident, fila in elegidas.iterrows():
        r, p = mapa[ident], mapa[ident]['participante']
        rol = next((k for k,v in ROLES.items() if fila['Rol']==v),None)
        decisiones.append(dict(participante=int(ident), version=r['version'], campos=dict(
            nombre=fila['Nombre'],apellidos=fila['Apellidos'],fecha_nacimiento=p['fecha_nacimiento_propuesta'],
            sexo=p['sexo_propuesto'],id_club=p['id_club_identificado'],rol_propuesto=rol,
            observaciones_revision='Alta por lote revisada; identificador provisional pendiente de DNI.')))
    parecidas = servicio.similitudes_altas(revision, decisiones)
    distintos = False
    if parecidas:
        st.warning('Hay nombres similares entre las nuevas fichas seleccionadas. Pueden ser familiares o una persona repetida: compruébalos antes de crear el lote.')
        st.table(pd.DataFrame(parecidas))
        distintos = st.checkbox('Confirmo que las personas con nombres similares de este lote son distintas.',
            key=prefijo+'_distintos_'+servicio._huella(decisiones)[:12])
    if st.button('Crear fichas seleccionadas e incorporar resultados',
                 disabled=elegidas.empty or not confirmar or (bool(parecidas) and not distintos), key=prefijo+'_guardar_altas'):
        if any(d['campos']['rol_propuesto'] is None for d in decisiones):
            st.error('Confirma el rol de cada miembro antes de crear las fichas.')
            return
        if distintos:
            for d in decisiones:
                d['confirmar_distinto_lote'] = True
                d['campos']['observaciones_revision'] += ' Confirmada identidad distinta de las otras altas similares del lote.'
        problemas = servicio.incidencias_altas(revision, decisiones)
        if problemas:
            for problema in problemas.values():
                st.error(problema)
            return
        _guardar(proveedor,'altas_resultados',identificador,decisiones,resumen['version'],al_guardar,datos_regata)
