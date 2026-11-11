"""Exploración de recorridos entre clases; solo consulta datos existentes."""
import altair as alt
import pandas as pd
import streamlit as st

from app import consulta_informes
from database import transiciones as consultas
from services import transiciones as analisis


CRITERIOS = {'regatas': 'Primera regata registrada', 'unidades': 'Inicio de unidad competitiva'}


def cargar(motor, fecha):
    return analisis.preparar(consultas.cargar_datos(motor, fecha), fecha)


def elegir(etiqueta, opciones, clave, **kwargs):
    if st.session_state.get(clave) not in opciones:
        st.session_state.pop(clave, None)
    return st.selectbox(etiqueta, opciones, key=clave, **kwargs)


def criterio(clave):
    return elegir('Referencia del cambio', list(CRITERIOS), clave,
                  format_func=CRITERIOS.get,
                  help='No mezclamos fechas de unidades con primeras regatas. Las clases sin regatas no entran en el primer criterio.')


def advertencias():
    st.caption('Se estudian primeras incorporaciones a clases distintas, no retornos a una clase anterior. '
               'La primera fecha registrada puede ser posterior al cambio real. Una unidad abierta no demuestra actividad continuada.')
    st.caption('La carga de clasificaciones se limita a los primeros 40 autonómicos, 80 nacionales y españoles en internacionales. '
               'La ausencia de resultados no implica abandono; esta muestra no permite calcular tasas de éxito ni recomendar una clase.')


def persona_de_ficha(contenido, fecha):
    p = {**contenido['ficha'], 'unidades': [], 'resultados': [],
         'mediciones': contenido.get('mediciones', []), 'informes': contenido.get('informes', [])}
    unidades = {}
    for fila in contenido.get('trayectoria', []):
        if fila['fecha_inicio'] > fecha:
            continue
        u = unidades.setdefault(fila['id_unidad'], {**fila, 'miembros': []})
        u['miembros'].append(f"{fila['nombre_miembro']} {fila['apellidos_miembro']}")
    p['unidades'] = list(unidades.values())
    vistos = set()
    for r in contenido.get('resultados', []):
        u = unidades.get(r.get('id_unidad'))
        if (u is None or r['fecha_fin'] > fecha
                or r.get('id_clase') != u.get('id_clase')
                or r['fecha_inicio'] < u['fecha_inicio']
                or (u['fecha_fin'] is not None and r['fecha_fin'] > u['fecha_fin'])):
            continue
        if r['id_competicion'] not in vistos:
            p['resultados'].append(r)
            vistos.add(r['id_competicion'])
    return p


def linea_temporal(persona, fecha):
    filas = []
    ordenadas = sorted(persona['unidades'], key=lambda u: (u['fecha_inicio'], u['id_unidad']))
    for i, u in enumerate(ordenadas):
        if u['fecha_inicio'] > fecha:
            continue
        filas.append({'Equipo': f"{u['clase']} · equipo {i+1}", 'Clase': u['clase'],
                      'Inicio': u['fecha_inicio'], 'Hasta': min(u['fecha_fin'] or fecha, fecha),
                      'Cierre registrado': u['fecha_fin'].isoformat() if u['fecha_fin'] and u['fecha_fin'] <= fecha else 'Sin cierre hasta la consulta',
                      'Miembros': ' · '.join(u.get('miembros', [])), 'id_unidad': u['id_unidad']})
    if not filas:
        return
    marco = pd.DataFrame(filas)
    base = alt.Chart(marco).encode(
        y=alt.Y('Equipo:N', sort=[r['Equipo'] for r in filas], title=None),
        color=alt.Color('Clase:N'),
        tooltip=['Clase:N', alt.Tooltip('Inicio:T', format='%d/%m/%Y'),
                 'Cierre registrado:N', 'Miembros:N'])
    bandas = base.mark_bar(size=15, opacity=0.5).encode(x=alt.X('Inicio:T', title='Fechas registradas'), x2='Hasta:T')
    inicios = base.mark_tick(thickness=2, size=20).encode(x='Inicio:T')
    grafico = bandas + inicios
    por_unidad = {r['id_unidad']: r for r in filas}
    regatas = [{'Equipo': por_unidad[r['id_unidad']]['Equipo'], 'Clase': r['clase'],
                'Fecha': r['fecha_inicio'], 'Regata': r['competicion'],
                'Puesto': r.get('posicion_general'), 'Nivel': r.get('nivel')}
               for r in persona['resultados'] if r.get('id_unidad') in por_unidad]
    if regatas:
        puntos = alt.Chart(pd.DataFrame(regatas)).mark_point(shape='diamond', filled=True, size=70).encode(
            x='Fecha:T', y=alt.Y('Equipo:N', sort=[r['Equipo'] for r in filas]), color='Clase:N',
            tooltip=['Regata:N', 'Clase:N', alt.Tooltip('Fecha:T', format='%d/%m/%Y'), 'Puesto:Q', 'Nivel:N'])
        grafico += puntos
    st.altair_chart(grafico.properties(height=max(140, 42*len(filas))), use_container_width=True)
    st.caption('Las bandas muestran unidades registradas hasta la fecha de consulta; los rombos, regatas finalizadas. '
               'Los solapamientos se conservan. La composición del equipo es la registrada, sin fechas individuales de incorporación.')


def mostrar_individual(contenido, fecha, clave):
    p = persona_de_ficha(contenido, fecha)
    st.subheader('Transiciones entre clases')
    linea_temporal(p, fecha)
    if len({u['clase'] for u in p['unidades']}) < 2:
        st.info('Se necesitan al menos dos clases registradas para estudiar una transición.')
        return
    modo = criterio(clave+'_criterio')
    eventos, ambiguas = analisis.detectar(p, fecha, modo)
    advertencias()
    if ambiguas:
        st.info(f'{ambiguas} etapas con varias clases iniciadas el mismo día: no se asigna una dirección a sus transiciones.')
    if not eventos:
        st.info('No hay transiciones ordenables con esta referencia. Puedes consultar el inicio de las unidades si faltan regatas.')
        return
    indice = elegir('Transición observada', list(range(len(eventos))), clave+'_evento',
                     format_func=lambda i: f"{eventos[i]['origen']} → {eventos[i]['destino']} · {eventos[i]['fecha']:%d/%m/%Y}")
    e = eventos[indice]
    st.write(f"Edad en la referencia: {analisis.edad_texto(p.get('fecha_nacimiento'), e['fecha'])}. "
             f"Año de nacimiento: {p['fecha_nacimiento'].year if p.get('fecha_nacimiento') else 'Sin registrar'}.")
    if e['origen_abierto']:
        st.caption('La unidad de origen seguía abierta en esa fecha; el análisis no la cierra ni supone que se abandonara la clase.')
    st.caption(f"Regatas de la clase de origen desde esa fecha: {e['regatas_origen_posteriores']}.")
    st.markdown('**Mediciones conocidas hasta la referencia**')
    st.dataframe(pd.DataFrame(analisis.contexto(p, e)), hide_index=True, width='stretch')
    st.caption('Último valor conocido de cada indicador; las fechas pueden ser distintas. Se muestra su antigüedad, sin estimaciones.')
    comparar([(p, e)], fecha, clave+'_detalle')


def mostrar(proveedor, fecha, motor, lectura):
    st.title('Transiciones entre clases')
    st.write('Estudia recorridos registrados y compara su evolución tomando el cambio como referencia.')
    advertencias()
    personas = lectura((proveedor, 'transiciones', fecha), cargar, motor, fecha)
    modo = criterio('trans_criterio')
    eventos, ambiguas = [], 0
    for p in personas:
        observados, n = analisis.detectar(p, fecha, modo)
        eventos.extend((p, e) for e in observados)
        ambiguas += n
    if ambiguas:
        st.caption(f'{ambiguas} etapas con varias clases en la misma fecha quedan sin dirección de transición.')
    if not eventos:
        st.info('No hay transiciones con esta referencia hasta la fecha de consulta.')
        return
    clases = sorted({e['origen'] for _, e in eventos})
    origen = elegir('Clase de origen', clases, 'trans_origen')
    destinos = sorted({e['destino'] for _, e in eventos if e['origen'] == origen})
    destino = elegir('Clase de destino', destinos, 'trans_destino')
    recorrido = [(p, e) for p, e in eventos if e['origen'] == origen and e['destino'] == destino]
    a, b = st.columns(2)
    sexo = a.selectbox('Sexo', [None, 'Femenino', 'Masculino'], format_func=lambda x: x or 'Todos', key='trans_sexo')
    anios = sorted({p['fecha_nacimiento'].year for p, _ in recorrido if p.get('fecha_nacimiento')})
    st.session_state['trans_generaciones'] = [a for a in st.session_state.get('trans_generaciones', []) if a in anios]
    generaciones = b.multiselect('Años de nacimiento', anios, key='trans_generaciones')
    a, b = st.columns(2)
    federaciones = sorted({p['federacion'] for p, _ in recorrido if p.get('federacion')})
    if st.session_state.get('trans_federacion') not in [None]+federaciones:
        st.session_state.pop('trans_federacion', None)
    federacion = a.selectbox('Federación actual', [None]+federaciones, format_func=lambda x: x or 'Todas', key='trans_federacion')
    clubes = sorted({p['club'] for p, _ in recorrido if p.get('club') and (not federacion or p['federacion'] == federacion)})
    if st.session_state.get('trans_club') not in [None]+clubes:
        st.session_state.pop('trans_club', None)
    club = b.selectbox('Club actual', [None]+clubes, format_func=lambda x: x or 'Todos', key='trans_club')
    usar_edad = st.checkbox('Filtrar por edad al cambiar', key='trans_usar_edad')
    edades = st.slider('Edad cumplida en la referencia (años)', 0, 100, (10, 25), key='trans_edades')
    filtrados = [(p, e) for p, e in recorrido
                 if (not sexo or p.get('sexo') == sexo)
                 and (not generaciones or (p.get('fecha_nacimiento') and p['fecha_nacimiento'].year in generaciones))
                 and (not federacion or p.get('federacion') == federacion)
                 and (not club or p.get('club') == club)
                 and (not usar_edad or (e['edad_meses'] is not None and edades[0] <= e['edad_meses']//12 <= edades[1]))]
    st.caption('Club y federación corresponden a la ficha actual, no necesariamente a la fecha de la transición.')
    if not filtrados:
        st.info('No hay regatistas con este recorrido y estos filtros.')
        return
    a, b = st.columns(2)
    a.metric('Regatistas con el recorrido registrado', len({p['dni'] for p, _ in filtrados}))
    conocidos = [e['edad_meses'] for _, e in filtrados if e['edad_meses'] is not None]
    b.metric('Con edad conocida al cambiar', len(conocidos))
    nombres = {p['dni']: f"{p['nombre']} {p['apellidos']} · perfil {i+1}" for i, (p, _) in enumerate(filtrados)}
    filas = []
    for p, e in filtrados:
        medidas = analisis.contexto(p, e)
        filas.append({'Regatista': nombres[p['dni']], 'Nacimiento': p['fecha_nacimiento'].year if p.get('fecha_nacimiento') else None,
                      'Referencia': e['fecha'], 'Edad': analisis.edad_texto(p.get('fecha_nacimiento'), e['fecha']),
                      'Edad en años': e['edad'], 'Club actual': p.get('club'),
                      'Unidad de origen abierta': 'Sí' if e['origen_abierto'] else 'No',
                      **{r['Indicador']: r['Valor'] for r in medidas}})
    marco = pd.DataFrame(filas).drop(columns='Edad en años')
    marco['Nacimiento'] = pd.to_numeric(marco['Nacimiento'], errors='coerce').astype('Int64')
    st.dataframe(marco, hide_index=True, width='stretch')
    if conocidos:
        edades_registradas = pd.DataFrame({'Edad cumplida': [m//12 for m in conocidos]})
        distribucion = alt.Chart(edades_registradas).mark_bar().encode(
            x=alt.X('Edad cumplida:O', title='Edad cumplida al incorporarse (años)'),
            y=alt.Y('count():Q', title='Regatistas', axis=alt.Axis(tickMinStep=1)),
            tooltip=['Edad cumplida:O', alt.Tooltip('count():Q', title='Regatistas')])
        st.altair_chart(distribucion.properties(height=200), use_container_width=True)
    indicador = elegir('Medida física al cambiar', list(analisis.MEDIDAS.values()), 'trans_medida')
    puntos = []
    for r, (p, e) in zip(filas, filtrados):
        if r['Edad en años'] is None or r[indicador] is None:
            continue
        medida = next(m for m in analisis.contexto(p, e) if m['Indicador'] == indicador)
        puntos.append({**r, 'Fecha de la medida': medida['Fecha de medición'],
                       'Antigüedad (días)': medida['Antigüedad (días)']})
    if puntos:
        grafico = alt.Chart(pd.DataFrame(puntos)).mark_circle(size=90).encode(
            x=alt.X('Edad en años:Q', title='Edad al cambiar (años y meses completos)', scale=alt.Scale(zero=False)),
            y=alt.Y(indicador+':Q', scale=alt.Scale(zero=False)),
            tooltip=['Regatista:N', 'Edad:N', alt.Tooltip('Referencia:T', format='%d/%m/%Y'),
                     alt.Tooltip(indicador+':Q'), alt.Tooltip('Fecha de la medida:T', format='%d/%m/%Y'), 'Antigüedad (días):Q'])
        st.altair_chart(grafico.properties(height=280), use_container_width=True)
    st.caption(f'{len(puntos)} de {len(filas)} perfiles con edad y esta medida. Valores físicos anteriores o del mismo día; consulta sus fechas en el detalle individual.')
    mapa = {p['dni']: (p, e) for p, e in filtrados}
    st.session_state['trans_seleccion'] = [d for d in st.session_state.get('trans_seleccion', []) if d in mapa]
    elegidos = st.multiselect('Regatistas para comparar (máximo 3)', list(mapa),
                             format_func=nombres.get, max_selections=3, key='trans_seleccion')
    if elegidos:
        seleccion = [mapa[d] for d in elegidos]
        comparar(seleccion, fecha, 'trans_comparar')
        for p, e in seleccion:
            with st.expander('Detalle de la referencia · '+nombres[p['dni']]):
                st.write(f"{e['origen']} → {e['destino']} · {e['fecha']:%d/%m/%Y}")
                st.dataframe(pd.DataFrame(analisis.contexto(p, e)), hide_index=True, width='stretch')
                st.caption(f"Unidad de origen abierta: {'Sí' if e['origen_abierto'] else 'No'}. Regatas de origen posteriores: {e['regatas_origen_posteriores']}.")
    else:
        st.info('Selecciona hasta tres regatistas para alinear sus historiales alrededor de la transición.')


def comparar(seleccion, fecha, clave):
    st.subheader('Antes y después de la referencia')
    meses = elegir('Ventana antes y después (meses)', [6, 12, 24, 36], clave+'_ventana', index=1)
    niveles = sorted({r['nivel'] for p, _ in seleccion for r in p['resultados'] if r.get('nivel')})
    nivel = elegir('Nivel de las regatas mostradas', [None]+niveles, clave+'_nivel', format_func=lambda x: x or 'Todos')
    st.caption('El nivel filtra los resultados mostrados, sin cambiar la fecha de referencia. El tramo posterior llega como máximo a la fecha de consulta.')
    etiquetas = [f"{p['nombre']} {p['apellidos']} · perfil {i+1}" for i, (p, _) in enumerate(seleccion)]
    historiales = [(p, e, analisis.entorno(p, e, fecha, meses, nivel)) for p, e in seleccion]
    comparacion_fisica(historiales, etiquetas, clave)
    resumen, regatas, tecnicos = [], [], []
    for etiqueta, (p, e, h) in zip(etiquetas, historiales):
        resumen.extend({**r, 'Regatista': etiqueta} for r in analisis.resumen_resultados(p, e, h['resultados']))
        for r in h['resultados']:
            regatas.append({'Regatista': etiqueta, 'Regata': r['competicion'], 'Fecha': r['fecha_inicio'],
                            'Meses': r['meses'], 'Días': r['dias'], 'Clase': r['clase'],
                            'Nivel': r.get('nivel') or 'Sin nivel', 'Puesto': r.get('posicion_general')})
        for r in h['informes']:
            for campo, titulo in consulta_informes.ETIQUETAS.items():
                if r.get(campo) is not None:
                    tecnicos.append({'Regatista': etiqueta, 'Fecha': r['fecha'], 'Meses': r['meses'],
                                     'Días': r['dias'], 'Dimensión': titulo, 'Valoración': r[campo],
                                     'Técnico': consulta_informes.tecnico(r)})
        with st.expander('Informes próximos · '+etiqueta):
            st.caption('Informes fechados dentro de la ventana. El modelo no los vincula a una clase; la proximidad temporal no demuestra que evalúen la transición.')
            consulta_informes.mostrar_historial(sorted(h['informes'], key=lambda r: (r['fecha'], r['id_informe']), reverse=True), clave+'_informe_'+p['dni'])
    st.markdown('**Resultados por clase y nivel**')
    if resumen:
        st.dataframe(pd.DataFrame(resumen), hide_index=True, width='stretch')
    else:
        st.info('No hay resultados de origen anteriores o de destino posteriores dentro de esta ventana.')
    if regatas:
        st.dataframe(pd.DataFrame(regatas).drop(columns='Meses'), hide_index=True, width='stretch')
        con_puesto = [r for r in regatas if r['Puesto'] is not None]
        if con_puesto:
            grafico = alt.Chart(pd.DataFrame(con_puesto)).mark_point(filled=True, size=80).encode(
                x=alt.X('Meses:Q', title='Meses desde referencia (aprox.)', axis=alt.Axis(tickCount=7, labelOverlap=True)),
                y=alt.Y('Puesto:Q', scale=alt.Scale(reverse=True, zero=False), axis=alt.Axis(tickMinStep=1)),
                color=alt.Color('Regatista:N', scale=alt.Scale(domain=etiquetas, scheme='tableau10')),
                shape='Clase:N', tooltip=['Regatista:N', 'Regata:N', 'Clase:N', 'Nivel:N',
                    alt.Tooltip('Fecha:T', format='%d/%m/%Y'), 'Días:Q', 'Puesto:Q'])
            st.altair_chart(con_referencia(grafico).properties(height=280), use_container_width=True)
    st.caption('Los puestos se contextualizan por clase y nivel; no equivalen a rendimiento comparable entre flotas. '
               'No se mezclan puntos ni se calculan percentiles: todavía no guardamos el tamaño completo de las flotas. '
               'Sin regatas no se asigna un rendimiento de cero. En dobles, el resultado pertenece al equipo.')
    if tecnicos:
        grafico = alt.Chart(pd.DataFrame(tecnicos)).mark_point(filled=True, size=75).encode(
            x=alt.X('Meses:Q', title='Meses desde referencia (aprox.)', axis=alt.Axis(tickCount=7, labelOverlap=True)),
            y=alt.Y('Valoración:Q', scale=alt.Scale(domain=[1, 5]), axis=alt.Axis(values=[1, 2, 3, 4, 5])),
            color=alt.Color('Regatista:N', scale=alt.Scale(domain=etiquetas, scheme='tableau10')),
            shape='Dimensión:N', tooltip=['Regatista:N', 'Dimensión:N', 'Valoración:Q', 'Técnico:N',
                                         alt.Tooltip('Fecha:T', format='%d/%m/%Y'), 'Días:Q'])
        st.altair_chart(con_referencia(grafico).properties(height=280), use_container_width=True)
        st.caption('Valoraciones individuales de técnicos: no se promedian ni se atribuyen a una clase o al efecto del cambio.')


def con_referencia(grafico):
    cero = alt.Chart(pd.DataFrame({'Meses': [0]})).mark_rule(strokeDash=[4, 4], color='gray').encode(x='Meses:Q')
    return grafico + cero


def comparacion_fisica(historiales, etiquetas, clave):
    filas = [{**r, 'Regatista': etiqueta, 'Edad al medir': analisis.edad_texto(p.get('fecha_nacimiento'), r['fecha'])}
             for etiqueta, (p, _, h) in zip(etiquetas, historiales) for r in h['mediciones']]
    disponibles = [c for c in analisis.MEDIDAS if any(r.get(c) is not None for r in filas)]
    if not disponibles:
        st.info('No hay mediciones dentro de la ventana elegida.')
        return
    campo = elegir('Evolución física alrededor del cambio', disponibles, clave+'_medida', format_func=analisis.MEDIDAS.get)
    puntos = [{'Regatista': r['Regatista'], 'Fecha': r['fecha'], 'Meses': r['meses'], 'Días': r['dias'],
               'Valor': float(r[campo]), 'Registro': r.get('id_registro', 0), 'Edad al medir': r['Edad al medir']}
              for r in filas if r.get(campo) is not None]
    marco = pd.DataFrame(puntos).sort_values(['Regatista', 'Fecha', 'Registro']).drop_duplicates(['Regatista', 'Fecha'], keep='last')
    grafico = alt.Chart(marco).mark_line(point=True).encode(
        x=alt.X('Meses:Q', title='Meses desde referencia (aprox.)', axis=alt.Axis(tickCount=7, labelOverlap=True)),
        y=alt.Y('Valor:Q', title=analisis.MEDIDAS[campo], scale=alt.Scale(zero=False)),
        color=alt.Color('Regatista:N', scale=alt.Scale(domain=etiquetas, scheme='tableau10')),
        order='Días:Q', tooltip=['Regatista:N', alt.Tooltip('Fecha:T', format='%d/%m/%Y'),
                                'Edad al medir:N', 'Días:Q', alt.Tooltip('Valor:Q', title=analisis.MEDIDAS[campo])])
    st.altair_chart(con_referencia(grafico).properties(height=300), use_container_width=True)
    st.caption('Cero marca la referencia de cada deportista. Meses aproximados = días / 30,4375. '
               'Cada punto es una medición real; las líneas unen observaciones, sin rellenar ausencias. '
               'Con una única medición se muestra un punto. Mismo día e indicador: último registro conocido.')
    ausentes = [e for e in etiquetas if e not in set(marco['Regatista'])]
    if ausentes:
        st.caption('Sin esta medida en la ventana: ' + '; '.join(ausentes))
