"""Búsqueda de deportista, historial y formulario de nueva medición."""
from datetime import date

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from app import datos
from database import queries
from services import antropometria


def cargar_historial(motor, dni):
    return queries.consultar_historial_antropometrico(motor, dni)


def mostrar(proveedor, motor, lectura):
    st.title("Registros antropométricos")
    st.write("Añade una medición al historial de un regatista.")
    etiqueta = "Supabase" if proveedor == "supabase" else "Google Cloud SQL"
    st.info(f"La nueva medición se guardará únicamente en {etiqueta}.")
    st.caption("Cada guardado añade un registro; no sustituye mediciones anteriores. La fecha de consulta lateral no determina la fecha de la nueva medición.")
    mensaje = st.session_state.pop("antropo_guardado", None)
    if mensaje:
        st.success(mensaje)
    with st.form("antropo_busqueda"):
        texto = st.text_input("Buscar por nombre, apellidos o club", key="antropo_texto")
        buscar = st.form_submit_button("Buscar regatista")
    if buscar:
        st.session_state["antropo_busqueda_aplicada"] = texto.strip()
        st.session_state.pop("antropo_documento", None)
    busqueda = st.session_state.get("antropo_busqueda_aplicada", "")
    personas = lectura((proveedor, "buscar", (busqueda, None)), datos.buscar, motor, busqueda, None)
    if not personas:
        st.info("No se han encontrado deportistas. Cambia la búsqueda o crea primero su ficha.")
        return
    if len(personas) > 500:
        st.warning("Se muestran los primeros 500 resultados. Precisa la búsqueda.")
        personas = personas[:500]
    mapa = {p["dni"]: p for p in personas}
    if st.session_state.get("antropo_documento") not in mapa:
        st.session_state.pop("antropo_documento", None)
    dni = st.selectbox("Deportista", list(mapa), key="antropo_documento",
                       format_func=lambda d: f'{mapa[d]["nombre"]} {mapa[d]["apellidos"]} · {mapa[d]["club"] or "Sin club"} · {d}')
    p = mapa[dni]
    nacimiento = p.get("fecha_nacimiento")
    st.caption(f'Deportista seleccionado: {p["nombre"]} {p["apellidos"]} · Año de nacimiento: {nacimiento.year if nacimiento else "Sin registrar"}')
    historial = lectura((proveedor, "historial_completo", dni), cargar_historial, motor, dni)
    with st.expander(f"Historial registrado ({len(historial)} mediciones)", expanded=True):
        if historial:
            columnas = {"fecha": "Fecha", "altura": "Altura (cm)", "peso": "Peso (kg)",
                        "envergadura": "Envergadura (cm)", "porcentaje_graso": "Grasa corporal (%)"}
            marco = pd.DataFrame(historial).reindex(columns=list(columnas)).rename(columns=columnas)
            for col in list(columnas.values())[1:]:
                marco[col] = pd.to_numeric(marco[col], errors="coerce")
            st.dataframe(marco, hide_index=True, width="stretch")
        else:
            st.info("Este deportista todavía no tiene mediciones registradas.")
    st.subheader("Nueva medición")
    version = st.session_state.get("antropo_version", 0)
    clave = f"{proveedor}_{dni}_{version}"
    with st.form("antropo_formulario_" + clave):
        fecha = st.date_input("Fecha de medición", value=date.today(),
                              min_value=min(date(1900, 1, 1), nacimiento) if nacimiento else date(1900, 1, 1),
                              max_value=date.today(), format="DD/MM/YYYY")
        st.caption("Introduce al menos una medida. Los campos vacíos se guardan como datos no registrados.")
        a, b = st.columns(2)
        altura = a.number_input("Altura (cm)", value=None, min_value=0.01, max_value=999.99, step=0.01, format="%.2f", placeholder="Sin registrar")
        peso = b.number_input("Peso (kg)", value=None, min_value=0.01, max_value=999.99, step=0.01, format="%.2f", placeholder="Sin registrar")
        a, b = st.columns(2)
        envergadura = a.number_input("Envergadura (cm)", value=None, min_value=0.01, max_value=999.99, step=0.01, format="%.2f", placeholder="Sin registrar")
        grasa = b.number_input("Grasa corporal (%)", value=None, min_value=0.0, max_value=100.0, step=0.01, format="%.2f", placeholder="Sin registrar")
        st.caption("Puede haber mediciones distintas el mismo día. La ficha utiliza la última registrada cuando coinciden las fechas.")
        guardar = st.form_submit_button("Guardar medición", type="primary")
    if not guardar:
        return
    campos = dict(dni_deportista=dni, fecha=fecha, altura=altura, peso=peso,
                  envergadura=envergadura, porcentaje_graso=grasa)
    try:
        with st.spinner("Guardando medición…"):
            antropometria.guardar_en_proveedor(proveedor, campos)
    except (antropometria.ValidacionError, antropometria.ConflictoError) as error:
        st.error(str(error))
        return
    except (SQLAlchemyError, KeyError, OSError):
        st.error("No se pudo confirmar el guardado. Revisa la conexión y actualiza el historial antes de reintentar.")
        return
    st.session_state["lecturas"] = {}
    st.session_state["antropo_version"] = version + 1
    st.session_state["antropo_guardado"] = f"Medición de {p['nombre']} {p['apellidos']} guardada en {etiqueta}."
    st.rerun()
