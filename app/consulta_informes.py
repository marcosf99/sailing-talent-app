"""Detalle y comparación de informes técnicos, sin operaciones de escritura."""
import altair as alt
import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from services import informes as servicio


ETIQUETAS = {'estrategia': 'Estrategia', 'tactica': 'Táctica', 'trimado': 'Trimado', 'tecnica': 'Técnica'}


def tecnico(informe):
    return f'{informe["nombre_tecnico"]} {informe["apellidos_tecnico"]}'.strip()


def _seleccionar(historial, etiqueta, clave):
    por_id = {r['id_informe']: r for r in historial}
    if st.session_state.get(clave) not in por_id:
        st.session_state.pop(clave, None)
    identificador = st.selectbox(etiqueta, list(por_id), key=clave,
        format_func=lambda i: f'{por_id[i]["fecha"].strftime("%d/%m/%Y")} · {tecnico(por_id[i])} · Informe {i}')
    return por_id[identificador]


def mostrar_historial(historial, clave):
    st.subheader('Informes técnicos')
    if not historial:
        st.info('No hay informes técnicos registrados hasta la fecha de consulta.')
        return
    st.caption(f'{len(historial)} informes hasta la fecha de consulta. Valoraciones de 1 a 5; los datos sin valorar se mantienen vacíos.')
    marco = pd.DataFrame([{'Informe': r['id_informe'], 'Fecha': r['fecha'], 'Técnico': tecnico(r),
                           **{titulo: r[campo] for campo, titulo in ETIQUETAS.items()}} for r in historial])
    for titulo in ETIQUETAS.values():
        marco[titulo] = pd.to_numeric(marco[titulo], errors='coerce').astype('Int64')
    st.dataframe(marco, hide_index=True, width='stretch')
    informe = _seleccionar(historial, 'Informe técnico para consultar', clave)
    st.write(f'Informe del {informe["fecha"].strftime("%d/%m/%Y")} · Técnico: {tecnico(informe)}')
    if informe.get('titulacion_tecnico'):
        st.caption('Titulación: ' + informe['titulacion_tecnico'])
    for columna, (campo, titulo) in zip(st.columns(4), ETIQUETAS.items()):
        valor = informe[campo]
        columna.metric(titulo, f'{valor}/5' if valor is not None else 'Sin valorar')
    for campo, titulo in (('fortalezas', 'Fortalezas'), ('debilidades', 'Debilidades'), ('recomendaciones', 'Recomendaciones')):
        st.markdown(f'**{titulo}**')
        st.text(informe[campo] or 'Sin registrar')


def mostrar_comparacion(proveedor, fecha, motor, lectura, personas):
    st.subheader('Comparación de informes técnicos')
    st.caption('Se selecciona inicialmente el último informe de cada deportista hasta la fecha de consulta. Puedes elegir otro para comparar fechas o técnicos similares. Las valoraciones son observaciones del técnico, no una puntuación global de talento.')
    documentos = tuple(p['dni'] for p in personas)
    try:
        historiales = lectura((proveedor, 'comparar_informes', fecha, documentos),
                              servicio.informes_para_comparar, motor, documentos, fecha)
    except (SQLAlchemyError, KeyError, OSError, servicio.ValidacionError):
        st.warning('No se pudieron consultar los informes técnicos. Revisa la conexión y pulsa Actualizar datos.')
        return
    resumen, barras = [], []
    con_valoraciones = 0
    for persona in personas:
        dni = persona['dni']
        nombre = f'{persona["nombre"]} {persona["apellidos"]}'
        etiqueta = f'{nombre} · {dni}'
        historial = historiales.get(dni, [])
        informe = None
        if historial:
            clave = f'comparar_informe_{proveedor}_{dni}_{fecha.isoformat()}'
            informe = _seleccionar(historial, 'Informe técnico de ' + nombre, clave)
        else:
            st.caption(f'{nombre}: sin informes hasta la fecha de consulta.')
        resumen.append({'Regatista': etiqueta, 'Fecha del informe': informe['fecha'] if informe else None,
                        'Técnico': tecnico(informe) if informe else 'Sin informe',
                        **{titulo: informe[campo] if informe else None for campo, titulo in ETIQUETAS.items()}})
        if informe:
            valores = [(campo, titulo) for campo, titulo in ETIQUETAS.items() if informe[campo] is not None]
            con_valoraciones += bool(valores)
            for campo, titulo in valores:
                barras.append({'Regatista': etiqueta, 'Dimensión': titulo, 'Valoración': informe[campo],
                               'Fecha': informe['fecha'].strftime('%d/%m/%Y'), 'Técnico': tecnico(informe)})
    marco = pd.DataFrame(resumen)
    for titulo in ETIQUETAS.values():
        marco[titulo] = pd.to_numeric(marco[titulo], errors='coerce').astype('Int64')
    st.dataframe(marco, hide_index=True, width='stretch')
    if con_valoraciones < 2:
        st.info('Para mostrar el gráfico se necesitan valoraciones registradas en al menos dos candidatos.')
        return
    grafico = alt.Chart(pd.DataFrame(barras)).mark_bar().encode(
        x=alt.X('Dimensión:N', sort=list(ETIQUETAS.values()), axis=alt.Axis(labelAngle=0)),
        xOffset=alt.XOffset('Regatista:N', sort=[r['Regatista'] for r in resumen]),
        y=alt.Y('Valoración:Q', scale=alt.Scale(domain=[0, 5]), axis=alt.Axis(values=[1, 2, 3, 4, 5]), title='Valoración (1–5)'),
        color=alt.Color('Regatista:N', sort=[r['Regatista'] for r in resumen]),
        tooltip=['Regatista:N', 'Dimensión:N', 'Valoración:Q', 'Fecha:N', 'Técnico:N'],
    ).properties(height=320)
    st.altair_chart(grafico, use_container_width=True)
    st.caption('Se muestran únicamente los valores registrados, sin sustituir ausencias por cero ni promediar informes de técnicos o fechas diferentes.')
