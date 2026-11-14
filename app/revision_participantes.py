"""Revisión de participantes seleccionados en los borradores de clasificación."""
from datetime import date

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from app import datos, revision_lotes, datos_pendientes
from services import importaciones as borradores
from services import revision_participantes as servicio
from services import resultados_importados as resultados


ERRORES = (SQLAlchemyError, KeyError, OSError)


def _nombre_inicial(participante):
    """Sugiere una separación editable, conservando la revisión ya guardada."""
    if any(participante[c] is not None for c in ('nombre_propuesto', 'apellidos_propuestos')):
        return participante['nombre_propuesto'] or '', participante['apellidos_propuestos'] or ''
    original = ' '.join((participante['nombre_original'] or '').split())
    if ',' in original:
        apellidos, nombre = original.split(',', 1)
        return nombre.strip(), apellidos.strip()
    partes = original.split(' ', 1)
    return partes[0], partes[1] if len(partes) > 1 else ''


def _exito(mensaje, pantalla):
    st.session_state['lecturas'] = {}
    st.session_state['revision_mensaje'] = mensaje
    pantalla.empty()
    st.rerun()


def _campos_regata(imp, prefijo, disabled=False):
    nombre = st.text_input('Nombre de la regata', value=imp.get('nombre_competicion_propuesto') or '',
                           max_chars=200, key=prefijo + 'nombre', disabled=disabled)
    a, b = st.columns(2)
    inicio = a.date_input('Inicio de la regata', value=imp.get('fecha_inicio_propuesta'), key=prefijo + 'inicio', disabled=disabled)
    fin = b.date_input('Fin de la regata', value=imp.get('fecha_fin_propuesta'), key=prefijo + 'fin', disabled=disabled)
    localidad = st.text_input('Localidad de la regata', value=imp.get('localidad_propuesta') or '',
                              max_chars=100, key=prefijo + 'localidad', disabled=disabled)
    tipos = ['sin_confirmar', 'provisional', 'definitiva']
    tipo = st.selectbox('Estado de la clasificación de origen', tipos,
                        index=tipos.index(imp.get('tipo_clasificacion', 'sin_confirmar')),
                        format_func=lambda t: {'sin_confirmar': 'Sin confirmar', 'provisional': 'Provisional', 'definitiva': 'Definitiva'}[t],
                        key=prefijo + 'tipo', disabled=disabled)
    return dict(nombre=nombre, fecha_inicio=inicio, fecha_fin=fin, localidad=localidad, tipo_clasificacion=tipo)


def _mostrar_resultados(proveedor, revision, pantalla):
    imp = revision['importacion']
    version = resultados.version_resultados(revision)
    prefijo = f'revision_resultados_{proveedor}_{imp["id_importacion"]}_{version[:12]}_'
    editable = imp['estado'] in ('recibida', 'extraida', 'en_revision', 'parcialmente_importada')
    incompleta = any(not imp.get(c) for c in ('nombre_competicion_propuesto', 'fecha_inicio_propuesta', 'fecha_fin_propuesta')) or imp.get('tipo_clasificacion') not in ('provisional', 'definitiva')
    with st.expander('Datos de la regata', expanded=incompleta):
        campos_regata = _campos_regata(imp, prefijo + 'evento_', disabled=not editable)
    preparadas = resultados.filas_preparadas(revision)
    incorporadas = sum(f['estado'] == 'importada' for f in revision['filas'])
    st.subheader('Incorporar resultados revisados')
    st.caption(f'{incorporadas} resultados ya incorporados · {len(preparadas)} preparados. '
               'Las altas nuevas incorporan su resultado al completar el equipo. Este paso permite incorporar los de fichas existentes y resolver resultados pendientes.')
    if not preparadas:
        if imp['estado'] == 'completada':
            st.success('Todos los resultados seleccionados de este borrador están incorporados.')
        else:
            st.info('Confirma las identidades de una embarcación para incorporar su resultado. En dobles deben estar confirmados ambos miembros y sus roles.')
        return campos_regata
    if not editable:
        return campos_regata
    por_fila = {f['id_fila']: f for f in preparadas}
    def etiqueta(i):
        f = por_fila[i]
        nombres = ' / '.join(p['nombre_original'] for p in resultados.miembros_fila(revision, f))
        return f'Puesto {f["posicion_general"]} · {nombres} · {f["puntos"]} puntos'
    with st.expander('Revisar y guardar los resultados preparados', expanded=True):
        st.write(f'Clase: {imp["nombre_clase"]} · Nivel: {imp.get("nivel") or "Sin confirmar"}')
        elegidas = st.multiselect('Resultados que se incorporarán', list(por_fila), default=list(por_fila),
                                  format_func=etiqueta, key=prefijo + 'filas')
        st.caption('Se reutiliza el equipo compatible que cubra la regata. Si no existe, se crea una unidad desde el inicio de la regata y queda abierta hasta el cierre manual o por edad en Optimist. '
                   'Las identidades pendientes podrán completarse e incorporarse después.')
        confirmar = st.checkbox('He revisado la regata, los participantes, puestos y puntos que se incorporarán.', key=prefijo + 'confirmar')
        if st.button('Incorporar resultados seleccionados', type='primary', disabled=not elegidas or not confirmar,
                      key=prefijo + 'guardar'):
            try:
                total = resultados.incorporar_en_proveedor(proveedor, imp['id_importacion'], elegidas,
                    campos_regata, version)
            except (servicio.ValidacionError, servicio.ConflictoError) as error:
                st.error(str(error))
            except ERRORES:
                st.error('No se pudo confirmar la incorporación. Actualiza la revisión antes de reintentar.')
            else:
                _exito(f'{total} resultados incorporados. Ya puedes consultarlos en las fichas de los deportistas.', pantalla)
    return campos_regata


def mostrar(proveedor, motor, lectura):
    pantalla = st.empty()
    with pantalla.container():
        _mostrar(proveedor, motor, lectura, pantalla)


def _mostrar(proveedor, motor, lectura, pantalla):
    st.title('Revisión de participantes')
    st.write('Revisa las identidades seleccionadas y vincula una ficha existente o completa los datos para crearla.')
    etiqueta = 'Supabase' if proveedor == 'supabase' else 'Google Cloud SQL'
    st.info(f'Las decisiones se guardarán en {etiqueta}. La clasificación conservará su carácter provisional o definitivo.')
    mensaje = st.session_state.pop('revision_mensaje', None)
    if mensaje:
        st.success(mensaje)
    if st.button('Actualizar revisión', key='revision_actualizar'):
        st.session_state['lecturas'] = {}
    pagina = int(st.number_input('Página de borradores', min_value=1, value=1, key='revision_pagina'))
    try:
        lista = lectura((proveedor, 'revision_borradores', pagina), borradores.listar_borradores, motor, 50, (pagina - 1) * 50)
    except ERRORES:
        st.error('No se pudieron consultar los borradores. Revisa la conexión.')
        return
    if not lista:
        st.info('No hay borradores en esta página. Carga una clasificación o vuelve a la primera página.')
        return
    por_id = {b['id_importacion']: b for b in lista}
    clave_borrador = 'revision_borrador_' + proveedor
    if st.session_state.get(clave_borrador) not in por_id:
        st.session_state.pop(clave_borrador, None)
    identificador = st.selectbox('Borrador', list(por_id), key=clave_borrador,
                                 format_func=lambda i: f'{i} · {por_id[i]["nombre_archivo"] or por_id[i]["url_origen"]} · {por_id[i]["nombre_clase"]}')
    try:
        revision = lectura((proveedor, 'revision_contenido', identificador), servicio.cargar_revision, motor, identificador)
        clubes = lectura((proveedor, 'clubes'), datos.cargar_clubes, motor)
        federaciones = lectura((proveedor, 'federaciones'), datos.cargar_federaciones, motor)
    except (servicio.ValidacionError, *ERRORES) as error:
        st.error(str(error) if isinstance(error, servicio.ValidacionError) else 'No se pudo cargar la revisión. Comprueba la conexión.')
        return
    imp = revision['importacion']
    personas = revision['participantes_revision']
    confirmados = sum(p['dni_deportista_confirmado'] is not None for p in personas)
    columnas = st.columns(3)
    for col, nombre, numero in zip(columnas, ['Participantes seleccionados', 'Identidades confirmadas', 'Pendientes'],
                                  [len(personas), confirmados, len(personas) - confirmados]):
        col.metric(nombre, numero)
    excluidas = sum(f['cumple_criterio'] is False for f in revision['filas'])
    st.caption(f'{imp["nombre_clase"]} · {len(revision["seleccionadas"])} filas seleccionadas · {excluidas} excluidas del criterio. Solo se revisan las seleccionadas.')
    editable = imp['estado'] in ('recibida', 'extraida', 'en_revision', 'parcialmente_importada')
    if not editable:
        st.warning('Este borrador está cerrado para cambios de identidad.')
    datos_regata = _mostrar_resultados(proveedor, revision, pantalla)
    revision_lotes.mostrar(proveedor, motor, lectura, revision, clubes,
                           lambda mensaje: _exito(mensaje, pantalla), datos_regata=datos_regata)
    with st.expander('Participantes seleccionados'):
        st.dataframe(pd.DataFrame([{'Puesto': p['fila']['posicion_general'], 'Vela': p['fila']['numero_vela_original'],
                                    'Nombre en la fuente': p['nombre_original'], 'Club en la fuente': p['club_original'],
                                    'Documento confirmado': p['dni_deportista_confirmado'], 'Estado': p['estado']}
                                   for p in personas]), hide_index=True, width='stretch')
    incompletas = []
    for fila in revision['seleccionadas']:
        presentes = {p['orden_en_tripulacion'] for p in personas if p['id_fila'] == fila['id_fila']}
        huecos = [n for n in range(1, imp['numero_tripulantes'] + 1) if n not in presentes]
        if huecos and fila['estado'] != 'importada':
            incompletas.append((fila, huecos))
    if incompletas:
        with st.expander('Completar participantes que faltan', expanded=True):
            por_fila = {f['id_fila']: (f, huecos) for f, huecos in incompletas}
            fila_id = st.selectbox('Embarcación incompleta', list(por_fila), key=f'revision_fila_{identificador}',
                                   format_func=lambda i: f'Puesto {por_fila[i][0]["posicion_general"] or "sin confirmar"} · {por_fila[i][0]["numero_vela_original"] or "Sin vela"}')
            hueco = st.selectbox('Miembro por incorporar', por_fila[fila_id][1], key=f'revision_hueco_{fila_id}')
            nombre = st.text_input('Nombre completo tal como aparece en la clasificación', key=f'revision_falta_nombre_{fila_id}_{hueco}')
            if st.button('Añadir participante pendiente', disabled=not editable, key='revision_agregar'):
                try:
                    servicio.agregar_en_proveedor(proveedor, fila_id, nombre, hueco)
                except (servicio.ValidacionError, servicio.ConflictoError) as error:
                    st.error(str(error))
                except ERRORES:
                    st.error('No se pudo confirmar la incorporación. Actualiza la revisión antes de reintentar.')
                else:
                    _exito('Participante añadido a la revisión. Su ficha definitiva todavía está pendiente.', pantalla)
    datos_pendientes.mostrar(proveedor,motor,lectura)
    if not st.checkbox('Revisar una identidad individual · coincidencias dudosas o correcciones', key='revision_mostrar_individual'):
        return
    solo_pendientes = st.checkbox('Mostrar solo identidades pendientes', value=True, key=f'revision_solo_pendientes_{identificador}')
    visibles = [p for p in personas if not solo_pendientes or p['dni_deportista_confirmado'] is None]
    if not visibles:
        st.info('No quedan participantes con este filtro. Si faltan miembros, completa las embarcaciones indicadas arriba.')
        return
    por_persona = {p['id_participante_importado']: p for p in visibles}
    clave_persona = f'revision_persona_{proveedor}_{identificador}'
    if st.session_state.get(clave_persona) not in por_persona:
        st.session_state.pop(clave_persona, None)
    participante = st.selectbox('Participante que deseas revisar', list(por_persona), key=clave_persona,
                                format_func=lambda i: f'Puesto {por_persona[i]["fila"]["posicion_general"] or "sin confirmar"} · {por_persona[i]["nombre_original"]} · {"Confirmado" if por_persona[i]["dni_deportista_confirmado"] else "Pendiente"}')
    p = por_persona[participante]
    fila = p['fila']
    editable = editable and fila['estado'] != 'importada'
    prefijo = f'revision_{proveedor}_{identificador}_{participante}_{p["version"][:12]}_'
    st.subheader(p['nombre_original'])
    st.write(f'Club en la fuente: {p["club_original"] or "Sin indicar"}')
    st.caption(f'Vela: {fila["numero_vela_original"] or "Sin indicar"} · Página {fila["pagina_origen"] or "sin indicar"} · Puntos: {fila["puntos"] if fila["puntos"] is not None else "sin confirmar"}')
    if fila['incidencias']:
        st.warning(fila['incidencias'])
    if p['dni_deportista_confirmado']:
        st.success(f'Identidad confirmada: {p["dni_deportista_confirmado"]}. Para corregirla, selecciona Vincular ficha existente.')
    with st.expander('Fila original de la clasificación'):
        originales = fila['datos_originales']
        celdas = originales.get('celdas', originales)
        etiquetas = originales.get('columnas', {})
        st.dataframe(pd.DataFrame([{'Columna': etiquetas.get(c, c), 'Texto original': str(v)}
                                   for c, v in celdas.items()]), hide_index=True, width='stretch')
    with st.form(prefijo + 'buscar'):
        texto = st.text_input('Buscar otra ficha por nombre, apellidos o documento', key=prefijo + 'texto_busqueda')
        buscar = st.form_submit_button('Buscar fichas')
    if buscar:
        st.session_state[prefijo + 'consulta'] = texto.strip()
    consulta = st.session_state.get(prefijo + 'consulta', '')
    try:
        candidatos = lectura((proveedor, 'revision_candidatos', participante, p['version'], consulta),
                              servicio.buscar_coincidencias, motor, participante, consulta, 20)
    except (servicio.ValidacionError, *ERRORES):
        st.error('No se pudieron buscar las fichas existentes. Actualiza la revisión.')
        return
    st.subheader('Posibles coincidencias')
    if candidatos:
        st.dataframe(pd.DataFrame([{'Documento': c['dni'], 'Nombre': c['nombre'] + ' ' + c['apellidos'],
                                    'Club': c['club'], 'Federación': c['federacion'],
                                    'Año de nacimiento': c['fecha_nacimiento'].year if c.get('fecha_nacimiento') else None,
                                    'Similitud orientativa': float(c['indice_similitud']), 'Motivos': c['motivos']}
                                   for c in candidatos]), hide_index=True, width='stretch')
        st.caption('La similitud ayuda a ordenar candidatos; no confirma una identidad. Se muestran hasta veinte fichas. Precisa la búsqueda si lo necesitas.')
    else:
        st.info('No se han encontrado coincidencias con esta búsqueda. Puedes buscar otro nombre o documento antes de crear una ficha.')
    operaciones = ['Vincular ficha existente', 'Crear deportista', 'Dejar pendiente']
    operacion = st.radio('Decisión', operaciones, index=0 if candidatos or p['dni_deportista_confirmado'] else 2,
                         key=f'revision_accion_{proveedor}_{identificador}_{participante}', disabled=not editable)
    accion = {'Vincular ficha existente': 'vincular', 'Crear deportista': 'crear', 'Dejar pendiente': 'pendiente'}[operacion]
    elegido, confirmar = None, False
    if accion == 'vincular':
        por_ficha = {c['dni']: c for c in candidatos}
        elegido = st.selectbox('Ficha existente que corresponde a este participante', [''] + list(por_ficha),
                               format_func=lambda d: 'Selecciona una ficha' if not d else f'{por_ficha[d]["nombre"]} {por_ficha[d]["apellidos"]} · {d}',
                               key=prefijo + 'elegido', disabled=not editable) or None
        confirmar = st.checkbox('Confirmo que la ficha seleccionada corresponde a esta persona.', key=prefijo + 'confirmar_vinculo', disabled=not editable)
    campos = dict(dni=p['documento_propuesto'], nombre=p['nombre_propuesto'], apellidos=p['apellidos_propuestos'],
                  fecha_nacimiento=p['fecha_nacimiento_propuesta'], sexo=p['sexo_propuesto'])
    if accion in ('crear', 'pendiente'):
        nombre_inicial, apellidos_iniciales = _nombre_inicial(p)
        st.caption('Nombre y apellidos precargados de la clasificación: revisa su separación, especialmente en nombres compuestos. El DNI es opcional: si lo dejas vacío se asignará un identificador provisional TEMP-, editable después desde Gestión de deportistas.')
        a, b = st.columns(2)
        campos['dni'] = a.text_input('DNI / documento', value=p['documento_propuesto'] or '', max_chars=20, key=prefijo + 'dni', disabled=not editable)
        campos['nombre'] = b.text_input('Nombre', value=nombre_inicial, max_chars=100, key=prefijo + 'nombre', disabled=not editable)
        campos['apellidos'] = st.text_input('Apellidos', value=apellidos_iniciales, max_chars=150, key=prefijo + 'apellidos', disabled=not editable)
        a, b = st.columns(2)
        nacimiento = p['fecha_nacimiento_propuesta']
        campos['fecha_nacimiento'] = a.date_input('Fecha de nacimiento (opcional)', value=nacimiento,
                                                 min_value=min(date(1900, 1, 1), nacimiento) if nacimiento else date(1900, 1, 1),
                                                 max_value=date.today(), key=prefijo + 'nacimiento', disabled=not editable)
        sexos = [None, 'Femenino', 'Masculino']
        campos['sexo'] = b.selectbox('Sexo', sexos, index=sexos.index(p['sexo_propuesto']),
                                     format_func=lambda v: v or 'Sin registrar', key=prefijo + 'sexo', disabled=not editable)
    por_club = {c['id_club']: c for c in clubes}
    por_federacion = {f['id_federacion']: f for f in federaciones}
    original_club = p['id_club_identificado'] if p['id_club_identificado'] in por_club else None
    original_fed = por_club[original_club]['id_federacion'] if original_club is not None else None
    opciones_fed = [None] + list(por_federacion)
    federacion = st.selectbox('Federación para localizar el club de la fuente', opciones_fed,
                              index=opciones_fed.index(original_fed), key=prefijo + 'federacion', disabled=not editable,
                              format_func=lambda i: 'Todas las federaciones' if i is None else por_federacion[i]['nombre'])
    filtrados = [None] + [i for i, c in por_club.items() if federacion is None or c['id_federacion'] == federacion]
    clave_club = prefijo + 'club'
    if clave_club in st.session_state and st.session_state[clave_club] not in filtrados:
        del st.session_state[clave_club]
    campos['id_club'] = st.selectbox('Club identificado en la clasificación', filtrados,
                                    index=filtrados.index(original_club) if original_club in filtrados else 0,
                                    format_func=lambda i: 'Sin confirmar / sin club' if i is None else por_club[i]['nombre'],
                                    key=clave_club, disabled=not editable)
    st.caption('Al vincular una ficha existente, este club describe la fuente y no modifica el club actual de esa ficha.')
    if imp['numero_tripulantes'] == 1:
        campos['rol_propuesto'] = 'Patron'
        st.caption(f'{imp["nombre_clase"]} es una clase individual: rol asignado automáticamente como patrón.')
    else:
        roles = [None, 'Patron', 'Tripulante']
        campos['rol_propuesto'] = st.selectbox('Rol en la embarcación', roles, index=roles.index(p['rol_propuesto']),
                                              format_func=lambda r: {'Patron': 'Patrón', 'Tripulante': 'Tripulante'}.get(r, 'Sin confirmar'),
                                              key=prefijo + 'rol', disabled=not editable)
    campos['observaciones_revision'] = st.text_area('Observaciones de la revisión', value=p['observaciones_revision'] or '', key=prefijo + 'notas', disabled=not editable)
    miembros = resultados.miembros_fila(revision, fila)
    automatico = accion == 'crear' or (accion == 'vincular' and any(
        m['estado'] == 'nuevo_confirmado' and m['id_participante_importado'] != participante for m in miembros))
    campos_regata = None
    if automatico:
        st.subheader('Resultado asociado al alta')
        st.write(f'{datos_regata["nombre"] or "Regata sin nombre"} · {imp["nombre_clase"]} · Puesto general: {fila["posicion_general"]} · Puntos: {fila["puntos"]}')
        st.caption('El mismo botón guarda la ficha y el resultado. En dobles, el resultado se incorporará cuando estén confirmados ambos miembros y sus roles.')
        campos_regata = datos_regata
    distinto = False
    if accion == 'crear':
        distinto = st.checkbox('He revisado las coincidencias y confirmo que debo crear una ficha nueva.', key=prefijo + 'confirmar_nuevo', disabled=not editable)
    etiquetas = {'crear': 'Crear deportista y guardar resultado', 'vincular': 'Vincular ficha seleccionada', 'pendiente': 'Guardar pendiente'}
    if automatico and imp['numero_tripulantes'] == 2:
        otros = [m for m in miembros if m['id_participante_importado'] != participante]
        completa = (len(otros) == 1 and otros[0]['dni_deportista_confirmado']
                    and sorted([otros[0]['rol_propuesto'] or '', campos['rol_propuesto'] or '']) == ['Patron', 'Tripulante'])
        if accion == 'crear' and not completa:
            etiquetas['crear'] = 'Crear deportista y dejar equipo pendiente'
        elif accion == 'vincular' and completa:
            etiquetas['vincular'] = 'Vincular ficha y guardar resultado'
    desactivado = not editable or (accion == 'vincular' and (not elegido or not confirmar)) or (accion == 'crear' and not distinto)
    if st.button(etiquetas[accion], type='primary', disabled=desactivado, key=prefijo + 'guardar'):
        try:
            extras = dict(datos_resultado=campos_regata, version_importacion=resultados.version_resultados(revision)) if campos_regata is not None else {}
            guardado = servicio.guardar_en_proveedor(proveedor, participante, accion, campos, p['version'], elegido, distinto, **extras)
        except (servicio.ValidacionError, servicio.ConflictoError) as error:
            st.error(str(error))
        except ERRORES:
            st.error('No se pudo confirmar el guardado. Actualiza la revisión y comprueba el documento antes de reintentar.')
        else:
            if isinstance(guardado, dict) and guardado['resultado_incorporado']:
                _exito('Deportista creado con su resultado deportivo.' if accion == 'crear' else 'Ficha vinculada y resultado del equipo incorporado.', pantalla)
            elif isinstance(guardado, dict) and guardado['pendiente_equipo']:
                _exito('Ficha guardada. El resultado queda pendiente de completar el equipo o corregir sus datos: ' + ' '.join(guardado.get('incidencias', [])), pantalla)
            else:
                _exito({'crear': 'Deportista creado y vinculado a la clasificación.',
                    'vincular': 'Ficha existente vinculada al participante.',
                    'pendiente': 'Datos guardados. El participante continúa pendiente.'}[accion], pantalla)
