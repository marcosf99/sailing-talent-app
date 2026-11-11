"""Filtros exploratorios y comparación de perfiles, sin puntuaciones predictivas."""
import altair as alt
import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError
from services.antropometria import ValidacionError

from app import datos, consulta_informes


INDICADORES = {
    "altura": "Altura (cm)", "peso": "Peso (kg)",
    "envergadura": "Envergadura (cm)", "porcentaje_graso": "Grasa corporal (%)",
}


def nombre(persona):
    return f'{persona["nombre"]} {persona["apellidos"]}'


def edad_en_medicion(nacimiento, fecha):
    """Años y meses completos en la fecha del punto, no en la consulta actual."""
    if nacimiento is None or fecha < nacimiento:
        return 'Edad no disponible'
    meses = (fecha.year - nacimiento.year) * 12 + fecha.month - nacimiento.month
    meses -= fecha.day < nacimiento.day
    anos, meses = divmod(meses, 12)
    etiqueta = f'{anos} ' + ('año' if anos == 1 else 'años')
    if meses:
        etiqueta += f' y {meses} ' + ('mes' if meses == 1 else 'meses')
    return etiqueta


def formatear(valor):
    if valor is None:
        return "—"
    if hasattr(valor, "strftime"):
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, (int, float)) or hasattr(valor, "as_tuple"):
        return f"{valor:g}"
    return str(valor)


def tabla_comparacion(personas):
    campos = {
        "club": "Club", "federacion": "Federación", "sexo": "Sexo", "edad": "Edad (años)",
        "clases_activas": "Clases activas", "fecha_medicion": "Fecha de medición",
        **INDICADORES, "participaciones": "Participaciones", "mejor_puesto": "Mejor puesto general",
    }
    filas = [{"Indicador": etiqueta} for etiqueta in campos.values()]
    for persona in personas:
        etiqueta = f'{nombre(persona)} · {persona["dni"]}'
        for fila, campo in zip(filas, campos):
            fila[etiqueta] = formatear(persona.get(campo))
    return pd.DataFrame(filas)


def mostrar(proveedor, fecha, motor, lectura):
    st.title("Candidatos y comparación")
    st.write("Explora perfiles por clase, edad y medidas físicas y compara hasta tres regatistas.")
    st.caption("Los filtros son criterios del usuario. No calculan una puntuación de talento ni recomiendan una transición de clase.")
    clases = lectura((proveedor, "clases"), datos.cargar_clases, motor)
    with st.form("filtros_candidatos"):
        izquierda, derecha = st.columns(2)
        with izquierda:
            clase = st.selectbox("Clase actual", [None] + [c["nombre"] for c in clases],
                                 format_func=lambda c: c or "Todas", key="cand_clase")
        with derecha:
            sexo = st.selectbox("Sexo", [None, "Femenino", "Masculino"],
                                format_func=lambda s: s or "Todos", key="cand_sexo")
        usar_edad = st.checkbox("Aplicar filtro de edad", key="cand_usar_edad")
        a, b = st.columns(2)
        edad_min = a.number_input("Edad mínima (años)", min_value=0, max_value=120, value=10, step=1, key="cand_edad_min")
        edad_max = b.number_input("Edad máxima (años)", min_value=0, max_value=120, value=30, step=1, key="cand_edad_max")
        usar_altura = st.checkbox("Aplicar altura mínima", key="cand_usar_altura")
        altura = st.number_input("Altura mínima (cm)", min_value=0.0, max_value=300.0, value=150.0, step=0.5, key="cand_altura")
        aplicar = st.form_submit_button("Aplicar filtros", type="primary")
    if aplicar:
        if usar_edad and edad_min > edad_max:
            st.error("La edad mínima no puede superar la edad máxima.")
            return
        st.session_state["filtros_candidatos_aplicados"] = {
            "clase_actual": clase, "sexo": sexo,
            "edad_min": int(edad_min) if usar_edad else None,
            "edad_max": int(edad_max) if usar_edad else None,
            "altura_min": float(altura) if usar_altura else None,
        }
    filtros = st.session_state.get("filtros_candidatos_aplicados", {})
    etiquetas = [
        f'Clase: {filtros["clase_actual"]}' if filtros.get("clase_actual") else "Todas las clases",
        filtros.get("sexo") or "Todos los sexos",
    ]
    if filtros.get("edad_min") is not None:
        etiquetas.append(f'Edad: {filtros["edad_min"]}–{filtros["edad_max"]} años')
    if filtros.get("altura_min") is not None:
        etiquetas.append(f'Altura ≥ {filtros["altura_min"]:g} cm')
    st.caption("Filtros aplicados: " + " · ".join(etiquetas))
    st.caption(f'Fecha de consulta: {fecha.strftime("%d/%m/%Y")}. Las tablas utilizan la última medición disponible; el gráfico antropométrico muestra el historial hasta esa fecha.')
    # La clave incluye proveedor, filtros y fecha para no mezclar datos.
    clave_filtros = tuple(sorted(filtros.items()))
    filas = lectura((proveedor, "candidatos", fecha, clave_filtros), datos.cargar_candidatos, motor, filtros, fecha)
    if len(filas) > 500:
        st.warning("Se muestran los primeros 500 candidatos. Precisa los filtros para encontrar otros perfiles.")
        filas = filas[:500]
    personas = {p["dni"]: p for p in filas}
    # Retirar selecciones que ya no cumplen los filtros antes de crear el widget.
    st.session_state["comparar_seleccion"] = [
        d for d in st.session_state.get("comparar_seleccion", []) if d in personas
    ]
    if not filas:
        st.info("No hay candidatos con estos filtros. Amplía el rango de edad o reduce la altura mínima.")
        return
    st.subheader(f"Candidatos encontrados: {len(filas)}")
    columnas = {
        "regatista": "Regatista", "club": "Club", "sexo": "Sexo", "edad": "Edad (años)",
        "clases_activas": "Clases activas", "fecha_medicion": "Fecha de medición", **INDICADORES,
        "participaciones": "Participaciones",
    }
    marco = pd.DataFrame([{**p, "regatista": nombre(p)} for p in filas]).reindex(columns=list(columnas)).rename(columns=columnas)
    for col in ["Edad (años)", "Participaciones"]:
        marco[col] = pd.to_numeric(marco[col], errors="coerce").astype("Int64")
    for col in INDICADORES.values():
        marco[col] = pd.to_numeric(marco[col], errors="coerce")
    st.dataframe(marco, hide_index=True, width="stretch")
    st.caption("Los datos no registrados no se sustituyen por cero. Al filtrar por altura, se excluyen perfiles sin una altura conocida.")
    seleccion = st.multiselect(
        "Regatistas para comparar (máximo 3)", list(personas), max_selections=3,
        format_func=lambda d: f'{nombre(personas[d])} · {personas[d]["club"] or "Sin club"} · {d}',
        key="comparar_seleccion",
    )
    if not seleccion:
        st.info("Selecciona hasta tres regatistas para comparar sus perfiles.")
        return
    comparados = lectura((proveedor, "comparar", fecha, tuple(seleccion)), datos.comparar, motor, seleccion, fecha)
    if not comparados:
        st.info("Los perfiles seleccionados ya no están disponibles. Pulsa Actualizar datos.")
        return
    st.subheader("Comparación de perfiles")
    st.dataframe(tabla_comparacion(comparados), hide_index=True, width="stretch")
    st.caption("Las mediciones pueden corresponder a fechas diferentes. El número de participaciones y el mejor puesto no son equivalentes a una valoración del nivel deportivo.")
    mostrar_comparacion_fisica(proveedor, fecha, motor, lectura, comparados)
    consulta_informes.mostrar_comparacion(proveedor, fecha, motor, lectura, comparados)


def mostrar_comparacion_fisica(proveedor, fecha, motor, lectura, comparados):
    st.subheader('Evolución antropométrica')
    documentos = tuple(p['dni'] for p in comparados)
    try:
        historiales = lectura((proveedor, 'comparar_evolucion', fecha, documentos),
                              datos.cargar_historiales_comparacion, motor, documentos, fecha)
    except (SQLAlchemyError, KeyError, OSError, ValidacionError):
        st.warning('No se pudo consultar la evolución antropométrica. Revisa la conexión y pulsa Actualizar datos.')
        return
    etiquetas = [f'{nombre(p)} · {p["dni"]}' for p in comparados]
    filas = [{**r, 'Regatista': etiqueta, 'Edad al medir': edad_en_medicion(p.get('fecha_nacimiento'), r['fecha'])}
             for p, etiqueta in zip(comparados, etiquetas)
             for r in historiales.get(p['dni'], []) if r['fecha'] <= fecha]
    disponibles = [campo for campo in INDICADORES if any(r.get(campo) is not None and pd.notna(r[campo]) for r in filas)]
    if not disponibles:
        st.info('No hay mediciones antropométricas disponibles hasta la fecha de consulta para estos regatistas.')
        return
    if st.session_state.get('comparar_indicador') not in disponibles:
        st.session_state.pop('comparar_indicador', None)
    indicador = st.selectbox("Medida para comparar", disponibles,
                             format_func=lambda c: INDICADORES[c], key="comparar_indicador")
    conocidos = [r for r in filas if r.get(indicador) is not None and pd.notna(r[indicador])]
    marco = pd.DataFrame([{'Regatista': r['Regatista'], 'Fecha': r['fecha'], 'Registro': r['id_registro'],
                           'Valor': float(r[indicador]), 'Edad al medir': r['Edad al medir']} for r in conocidos])
    # Igual criterio que la evolución individual: última medición conocida de
    # cada indicador por día, sin perderla por otra medición parcial posterior.
    marco = marco.sort_values(['Regatista', 'Fecha', 'Registro']).drop_duplicates(['Regatista', 'Fecha'], keep='last')
    grafico = alt.Chart(marco).mark_line(point=True).encode(
        x=alt.X('Fecha:T', axis=alt.Axis(format='%d/%m/%Y', tickCount=6, labelOverlap=True)),
        y=alt.Y('Valor:Q', title=INDICADORES[indicador], scale=alt.Scale(zero=False)),
        color=alt.Color('Regatista:N', scale=alt.Scale(domain=etiquetas, scheme='tableau10')),
        order=alt.Order('Fecha:T'),
        tooltip=['Regatista:N', alt.Tooltip('Fecha:T', format='%d/%m/%Y'),
                 alt.Tooltip('Edad al medir:N', title='Edad en la medición'),
                 alt.Tooltip('Valor:Q', title=INDICADORES[indicador], format='.2f')],
    ).properties(height=320)
    st.altair_chart(grafico, use_container_width=True)
    st.caption('Cada color identifica a un regatista. Los puntos son mediciones registradas y las líneas unen sus fechas. Si hay varias mediciones del mismo indicador en un día, se muestra la de mayor identificador; no se promedian ni se rellenan valores ausentes.')
    presentes = set(marco['Regatista'])
    ausentes = [etiqueta for etiqueta in etiquetas if etiqueta not in presentes]
    if ausentes:
        st.caption('Sin registros de esta medida: ' + '; '.join(ausentes) + '.')
    if any(len(grupo) == 1 for _, grupo in marco.groupby('Regatista')):
        st.caption('Con una sola fecha registrada se muestra un punto; hacen falta dos fechas para trazar una evolución.')
