"""Filtros exploratorios y comparación de perfiles, sin puntuaciones predictivas."""
import pandas as pd
import streamlit as st

from app import datos


INDICADORES = {
    "altura": "Altura (cm)", "peso": "Peso (kg)",
    "envergadura": "Envergadura (cm)", "porcentaje_graso": "Grasa corporal (%)",
}


def nombre(persona):
    return f'{persona["nombre"]} {persona["apellidos"]}'


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
    st.caption(f'Fecha de consulta: {fecha.strftime("%d/%m/%Y")}. Se utiliza la última medición disponible hasta esa fecha.')
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
    disponibles = [campo for campo in INDICADORES if any(p.get(campo) is not None for p in comparados)]
    if len(comparados) < 2 or not disponibles:
        st.caption("El gráfico se muestra al seleccionar al menos dos perfiles con valores para comparar.")
        return
    indicador = st.selectbox("Medida para comparar", disponibles,
                             format_func=lambda c: INDICADORES[c], key="comparar_indicador")
    conocidos = [p for p in comparados if p.get(indicador) is not None]
    if len(conocidos) < 2:
        st.info("Esta medida necesita valores conocidos en al menos dos perfiles para representar el gráfico.")
        return
    grafico = pd.DataFrame([{
        "Regatista": f'{nombre(p)} · {p["dni"]}', INDICADORES[indicador]: float(p[indicador]),
    } for p in conocidos])
    st.bar_chart(grafico, x="Regatista", y=INDICADORES[indicador],
                 x_label="Regatista", y_label=INDICADORES[indicador])
    if len(conocidos) < len(comparados):
        st.caption("Se omiten del gráfico los perfiles sin esta medida; permanecen en la tabla de comparación.")
