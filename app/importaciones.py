"""Carga de PDF, selección de columnas y guardado de borradores revisables."""
from pathlib import Path
import hashlib
import json

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from app import datos
from services import extraccion_clasificaciones as extractor
from services import importaciones as servicio
from services import documentos_importacion as documentos


def _celda(valor):
    return '' if valor is None or pd.isna(valor) else str(valor).strip()


def _marco_edicion(filas, extraccion, mapeo, tripulantes):
    originales = {f['numero_fila']: f for f in extraccion['filas']}
    salida = []
    for f in filas:
        fila = {'Fila': f['numero_fila'], 'Página': f['pagina_origen'],
                'Posición general': str(f['posicion_general']) if f['posicion_general'] else '',
                'Vela': f['numero_vela_original'] or '',
                'Puntos': str(f['puntos']) if f['puntos'] is not None else '',
                'Categoría': f['categoria_original'] or '',
                'Texto participantes': originales[f['numero_fila']]['celdas'].get(mapeo.get('participantes'), '')}
        for i in range(1, tripulantes + 1):
            p = f['participantes'][i - 1] if len(f['participantes']) >= i else {}
            fila[f'Nombre {i}'] = p.get('nombre_original') or ''
            fila[f'Club {i}'] = p.get('club_original') or ''
        salida.append(fila)
    return pd.DataFrame(salida)


def _filas_editadas(marco, originales, tripulantes):
    if len(marco) != len(originales):
        raise servicio.ValidacionError('La revisión debe conservar todas las filas del documento.')
    resultado = []
    for base, editada in zip(originales, marco.to_dict('records')):
        if int(editada['Fila']) != base['numero_fila']:
            raise servicio.ValidacionError('No se puede cambiar el orden de las filas originales.')
        miembros = []
        for i in range(1, tripulantes + 1):
            nombre = _celda(editada[f'Nombre {i}'])
            club = _celda(editada[f'Club {i}'])
            if nombre:
                miembros.append({'nombre_original': nombre, 'club_original': club or None})
            elif club:
                raise servicio.ValidacionError(f'Fila {base["numero_fila"]}: falta el nombre del miembro {i}.')
        resultado.append({**base,
                          'posicion_general': extractor.convertir_posicion(_celda(editada['Posición general'])),
                          'puntos': extractor.convertir_puntos(_celda(editada['Puntos'])),
                          'numero_vela_original': _celda(editada['Vela']) or None,
                          'categoria_original': _celda(editada['Categoría']) or None,
                          'participantes': miembros})
    return resultado


def _clase_canonica(nombre):
    texto = extractor._normalizar(nombre).replace(' ', '')
    return 'optimist' if texto == 'opt' else texto


def mostrar(proveedor, motor, lectura):
    st.title('Importar clasificaciones')
    st.write('Carga un PDF, elige las columnas y revisa la clasificación antes de guardar un borrador.')
    st.caption('Se admiten PDF con texto seleccionable, hasta 20 MB y 50 páginas. Para un enlace de regata, descarga primero su PDF.')
    if st.checkbox('Ver borradores guardados', key='importacion_ver_borradores'):
        try:
            borradores = servicio.listar_borradores(motor)
            if borradores:
                st.dataframe(pd.DataFrame(borradores).rename(columns={
                    'id_importacion': 'Borrador', 'nombre_archivo': 'Archivo', 'nombre_clase': 'Clase',
                    'estado': 'Estado', 'nivel': 'Nivel', 'creado_en': 'Creado', 'total_filas': 'Filas',
                })[['Borrador', 'Archivo', 'Clase', 'Nivel', 'Estado', 'Creado', 'Filas']],
                    hide_index=True, width='stretch')
            else:
                st.info('Todavía no hay borradores guardados.')
        except (SQLAlchemyError, KeyError, OSError, ValueError):
            st.error('No se pudo consultar el listado de borradores.')
    archivo = st.file_uploader('Clasificación en PDF', type=['pdf'], key='importacion_archivo')
    if archivo is None:
        return
    contenido = archivo.getvalue()
    huella = hashlib.sha256(contenido).hexdigest()
    if st.button('Analizar PDF', type='primary', key='importacion_analizar'):
        for clave in list(st.session_state):
            if clave.startswith('importacion_') and clave not in ('importacion_archivo', 'importacion_analizar', 'importacion_ver_borradores'):
                del st.session_state[clave]
        st.session_state.pop('importacion_resultado', None)
        st.session_state.pop('importacion_guardada', None)
        try:
            with st.spinner('Leyendo las páginas de la clasificación…'):
                st.session_state['importacion_resultado'] = extractor.extraer_pdf(contenido)
        except servicio.ValidacionError as error:
            st.error(str(error))
            return
    resultado = st.session_state.get('importacion_resultado')
    if resultado is None or resultado['huella'] != huella:
        st.info('Pulsa Analizar PDF para preparar la vista previa de este archivo.')
        return
    guardada = st.session_state.get('importacion_guardada')
    bloqueada = bool(guardada and guardada['huella'] == huella)
    if bloqueada:
        st.success(f'Borrador {guardada["id"]} guardado en {guardada["proveedor"]}. Queda pendiente de revisión antes de crear resultados definitivos.')
    for aviso in resultado['avisos']:
        st.warning(aviso)
    st.caption(f'{len(resultado["filas"])} filas detectadas en {len(resultado["paginas"])} páginas. Comprueba el recuento con el original.')
    if resultado['clase_detectada']:
        st.info(f'Clase indicada en el documento: {resultado["clase_detectada"]}.')
    if st.checkbox('Mostrar página original', key='importacion_ver_pdf'):
        pagina = st.selectbox('Página del PDF', [p['pagina'] for p in resultado['paginas']], key='importacion_pagina')
        clave = f'importacion_imagen_{huella}_{pagina}'
        if clave not in st.session_state:
            for vieja in list(st.session_state):
                if vieja.startswith('importacion_imagen_'):
                    del st.session_state[vieja]
            try:
                st.session_state[clave] = extractor.renderizar_pagina(contenido, pagina)
            except servicio.ValidacionError as error:
                st.error(str(error))
        if clave in st.session_state:
            st.image(st.session_state[clave], caption=f'Página original {pagina}', width='stretch')
    etiquetas = {c['id']: f'{i + 1} · {c["nombre"]}' for i, c in enumerate(resultado['columnas'])}
    with st.expander('Tabla extraída del PDF', expanded=True):
        st.dataframe(pd.DataFrame([{'Página': f['pagina_origen'], **{etiquetas[c]: valor for c, valor in f['celdas'].items()}}
                                   for f in resultado['filas']]), hide_index=True, width='stretch')
    st.subheader('Columnas de la clasificación')
    st.caption('Si hay dos columnas Pos, elige la general. Si aparecen TOTAL y NET, confirma qué puntuación debe guardarse.')
    sugeridas = extractor.sugerir_mapeo(resultado['columnas'])
    mapeo = {}
    for campo, etiqueta in (
        ('posicion_general', 'Posición general *'), ('puntos', 'Puntos *'),
        ('numero_vela_original', 'Número de vela'), ('participantes', 'Nombre o tripulación'),
        ('categoria_original', 'Categoría'),
    ):
        opciones = [''] + list(etiquetas)
        elegida = st.selectbox(etiqueta, opciones, index=opciones.index(sugeridas.get(campo) or ''),
                               format_func=lambda c: etiquetas[c] if c else 'Sin seleccionar',
                               key='importacion_mapa_' + campo, disabled=bloqueada)
        mapeo[campo] = elegida or None
    try:
        clases = lectura((proveedor, 'clases'), datos.cargar_clases, motor)
    except (SQLAlchemyError, KeyError, OSError, ValueError):
        st.error('No se pudo cargar el catálogo de clases. Revisa la conexión con la base seleccionada.')
        return
    por_clase = {c['id_clase']: c for c in clases}
    nivel = st.selectbox('Nivel de la competición *', [None] + list(servicio.NIVELES),
                         format_func=lambda n: 'Selecciona un nivel' if n is None else ('Autonómico' if n == 'Autonomico' else n),
                         key='importacion_nivel', disabled=bloqueada)
    clase = st.selectbox('Clase de la competición *', [None] + list(por_clase),
                         format_func=lambda c: 'Selecciona una clase' if c is None else por_clase[c]['nombre'],
                         key='importacion_clase', disabled=bloqueada)
    tripulantes = int(por_clase[clase]['numero_tripulantes']) if clase is not None else int(st.number_input(
        'Tripulantes por embarcación para la vista previa', min_value=1, max_value=10, value=1,
        key='importacion_tripulantes', disabled=bloqueada))
    if tripulantes > 10:
        st.error('La vista previa admite hasta diez miembros por embarcación.')
        return
    discrepancia = bool(clase is not None and resultado['clase_detectada']
                        and _clase_canonica(por_clase[clase]['nombre']) != _clase_canonica(resultado['clase_detectada']))
    if discrepancia:
        st.warning('La clase seleccionada no coincide con la indicada en el PDF. Elige la clase correcta; si falta en el catálogo, debe darse de alta antes de guardar.')
    opciones_nombres = ['manual'] + (['nombre_club'] if tripulantes == 1 else [])
    modo = st.selectbox('Tratamiento de los nombres', opciones_nombres,
                        format_func=lambda v: {'manual': 'Revisar y escribir cada miembro en la tabla',
                                               'nombre_club': 'Individual: primera línea = nombre; siguientes líneas = club'}[v],
                        key=f'importacion_nombres_{tripulantes}', disabled=bloqueada)
    if nivel is None:
        st.info('Selecciona el nivel para aplicar el criterio de incorporación.')
        return
    if nivel == 'Internacional' and mapeo.get('numero_vela_original') is None:
        st.error('Para una competición internacional debes seleccionar la columna del número de vela.')
        return
    try:
        filas = extractor.mapear_filas(resultado, mapeo, modo)
    except servicio.ValidacionError as error:
        st.error(str(error))
        return
    st.subheader('Revisión de filas y participantes')
    st.caption('Escribe cada miembro en su propia columna. Los nombres originales permanecen en Texto participantes. Las filas incompletas se conservarán pendientes de corrección.')
    version = hashlib.sha256(json.dumps([mapeo, modo, tripulantes], sort_keys=True).encode()).hexdigest()[:12]
    marco = st.data_editor(_marco_edicion(filas, resultado, mapeo, tripulantes),
                           disabled=True if bloqueada else ['Fila', 'Página', 'Texto participantes'], num_rows='fixed',
                           hide_index=True, width='stretch', key=f'importacion_editor_{huella}_{version}')
    try:
        editadas = _filas_editadas(marco, filas, tripulantes)
        preparadas = servicio.preparar_filas(editadas, nivel, tripulantes)
    except servicio.ValidacionError as error:
        st.error(str(error))
        return
    seleccionadas = sum(p['fila']['cumple_criterio'] is True for p in preparadas)
    excluidas = sum(p['fila']['cumple_criterio'] is False for p in preparadas)
    pendientes = sum(p['fila']['cumple_criterio'] is None for p in preparadas)
    columnas = st.columns(3)
    for columna, etiqueta, valor in zip(columnas, ['Seleccionadas', 'Fuera de criterio', 'Criterio sin resolver'],
                                        [seleccionadas, excluidas, pendientes]):
        columna.metric(etiqueta, valor)
    st.dataframe(pd.DataFrame([{'Fila': p['fila']['numero_fila'],
                                'Estado': {'pendiente': 'Pendiente de identidad', 'excluida': 'Fuera de criterio',
                                           'requiere_correccion': 'Requiere corrección'}[p['fila']['estado']],
                                'Criterio': p['fila']['motivo_seleccion'],
                                'Datos por revisar': p['fila']['incidencias'] or ''} for p in preparadas]),
                 hide_index=True, width='stretch')
    st.subheader('Guardar borrador')
    nombre = st.text_input('Nombre de la competición', key='importacion_nombre', disabled=bloqueada)
    a, b = st.columns(2)
    inicio = a.date_input('Fecha de inicio (opcional por ahora)', value=None, key='importacion_inicio', disabled=bloqueada)
    fin = b.date_input('Fecha de fin (opcional por ahora)', value=None, key='importacion_fin', disabled=bloqueada)
    localidad = st.text_input('Localidad', key='importacion_localidad', disabled=bloqueada)
    tipo = st.selectbox('Estado de la clasificación', ['sin_confirmar', 'provisional', 'definitiva'],
                        format_func=lambda v: {'sin_confirmar': 'Sin confirmar', 'provisional': 'Provisional',
                                               'definitiva': 'Definitiva'}[v], key='importacion_tipo', disabled=bloqueada)
    revision = hashlib.sha256(json.dumps([version, nivel, clase]).encode()).hexdigest()[:12]
    revisada = st.checkbox('He revisado el número de filas, las columnas y la clase seleccionada.', key='importacion_revisada_' + huella + '_' + revision, disabled=bloqueada)
    etiqueta = 'Supabase' if proveedor == 'supabase' else 'Google Cloud SQL'
    if not bloqueada:
        st.info(f'El borrador se guardará en {etiqueta}. El PDF original se conservará localmente en este equipo.')
    if st.button('Guardar borrador para revisar', type='primary', disabled=bloqueada or not revisada or clase is None or discrepancia,
                 key='importacion_guardar'):
        campos = {'nombre_archivo': Path(archivo.name).name, 'id_clase': clase, 'nivel': nivel,
                  'nombre_competicion_propuesto': nombre, 'fecha_inicio_propuesta': inicio,
                  'fecha_fin_propuesta': fin, 'localidad_propuesta': localidad,
                  'tipo_clasificacion': tipo, 'mapeo_columnas': mapeo}
        try:
            with st.spinner('Guardando la fuente y el borrador…'):
                identificador = documentos.guardar_en_proveedor(proveedor, contenido, campos, editadas)
        except (servicio.ValidacionError, servicio.ConflictoError) as error:
            st.error(str(error))
            return
        except (SQLAlchemyError, KeyError, OSError):
            st.error('No se pudo confirmar el guardado. Comprueba los borradores guardados antes de reintentar.')
            return
        st.session_state['importacion_guardada'] = {'id': identificador, 'proveedor': etiqueta, 'huella': huella}
        st.session_state['lecturas'] = {}
        st.rerun()
