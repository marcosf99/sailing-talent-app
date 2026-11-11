"""Creación y consulta de informes técnicos por deportista."""
from datetime import date

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from app import datos
from services import informes as servicio


ETIQUETAS = {"estrategia": "Estrategia", "tactica": "Táctica", "trimado": "Trimado", "tecnica": "Técnica"}


def mostrar(proveedor, motor, lectura):
    st.title("Informes técnicos")
    st.write("Registra una valoración del deportista y las observaciones del equipo técnico.")
    etiqueta = "Supabase" if proveedor == "supabase" else "Google Cloud SQL"
    st.info(f"El informe se guardará únicamente en {etiqueta}.")
    st.caption("Fecha, deportista y técnico son obligatorios. Las valoraciones y los textos son opcionales. El identificador del informe se genera al guardar.")
    mensaje = st.session_state.pop("informes_guardado", None)
    if mensaje:
        st.success(mensaje)
    tecnicos = lectura((proveedor, "tecnicos"), servicio.listar_tecnicos, motor)
    if not tecnicos:
        st.warning("No hay técnicos registrados. Registra un técnico en la base antes de crear informes.")
        return
    with st.form("informes_busqueda"):
        texto = st.text_input("Buscar deportista por nombre, apellidos o club", key="informes_texto")
        buscar = st.form_submit_button("Buscar deportista")
    if buscar:
        st.session_state["informes_busqueda_aplicada"] = texto.strip()
        st.session_state.pop("informes_deportista", None)
    busqueda = st.session_state.get("informes_busqueda_aplicada", "")
    personas = lectura((proveedor, "buscar", (busqueda, None)), datos.buscar, motor, busqueda, None)
    if not personas:
        st.info("No se han encontrado deportistas. Cambia la búsqueda o crea primero su ficha.")
        return
    if len(personas) > 500:
        st.warning("Se muestran los primeros 500 deportistas. Precisa la búsqueda.")
        personas = personas[:500]
    mapa = {p["dni"]: p for p in personas}
    if st.session_state.get("informes_deportista") not in mapa:
        st.session_state.pop("informes_deportista", None)
    dni = st.selectbox("Deportista", list(mapa), key="informes_deportista",
                       format_func=lambda d: f'{mapa[d]["nombre"]} {mapa[d]["apellidos"]} · {mapa[d]["club"] or "Sin club"} · {d}')
    p = mapa[dni]
    nacimiento = p.get("fecha_nacimiento")
    st.caption(f'Año de nacimiento: {nacimiento.year if nacimiento else "Sin registrar"}')
    historial = lectura((proveedor, "informes", dni), servicio.listar_informes, motor, dni)
    with st.expander(f"Informes registrados ({len(historial)})", expanded=False):
        if not historial:
            st.info("Este deportista todavía no tiene informes.")
        else:
            filas = [{"Informe": r["id_informe"], "Fecha": r["fecha"],
                      "Técnico": f'{r["nombre_tecnico"]} {r["apellidos_tecnico"]}',
                      **{et: r[c] for c, et in ETIQUETAS.items()}} for r in historial]
            marco = pd.DataFrame(filas)
            for col in ETIQUETAS.values():
                marco[col] = pd.to_numeric(marco[col], errors="coerce").astype("Int64")
            st.dataframe(marco, hide_index=True, width="stretch")
            por_id = {r["id_informe"]: r for r in historial}
            elegido = st.selectbox("Informe para consultar", list(por_id),
                                    format_func=lambda i: f'{por_id[i]["fecha"].strftime("%d/%m/%Y")} · {por_id[i]["nombre_tecnico"]} {por_id[i]["apellidos_tecnico"]} · Informe {i}',
                                    key="informes_ver_" + dni)
            for campo, etiqueta_texto in (("fortalezas", "Fortalezas"), ("debilidades", "Debilidades"), ("recomendaciones", "Recomendaciones")):
                st.markdown(f"**{etiqueta_texto}**")
                st.text(por_id[elegido][campo] or "Sin registrar")
    st.subheader("Nuevo informe")
    version = st.session_state.get("informes_version", 0)
    mapa_tecnicos = {t["dni"]: t for t in tecnicos}
    with st.form(f"informes_alta_{proveedor}_{dni}_{version}"):
        fecha = st.date_input("Fecha del informe *", value=date.today(),
                              min_value=min(date(1900, 1, 1), nacimiento) if nacimiento else date(1900, 1, 1),
                              max_value=date.today(), format="DD/MM/YYYY")
        tecnico = st.selectbox("Técnico *", [None] + list(mapa_tecnicos),
                               format_func=lambda d: "Selecciona un técnico" if d is None else f'{mapa_tecnicos[d]["nombre"]} {mapa_tecnicos[d]["apellidos"]} · {mapa_tecnicos[d]["titulacion"] or "Sin titulación registrada"} · {d}')
        st.caption("Valoraciones de 1 a 5. Sin valorar se guarda como dato no registrado.")
        columnas = st.columns(2)
        valoraciones = {}
        for i, (campo, titulo) in enumerate(ETIQUETAS.items()):
            valoraciones[campo] = columnas[i % 2].selectbox(titulo, [None, 1, 2, 3, 4, 5],
                                                         format_func=lambda n: "Sin valorar" if n is None else str(n))
        fortalezas = st.text_area("Fortalezas")
        debilidades = st.text_area("Debilidades")
        recomendaciones = st.text_area("Recomendaciones")
        guardar = st.form_submit_button("Guardar informe", type="primary")
    if not guardar:
        return
    campos = {"fecha": fecha, "dni_deportista": dni, "dni_tecnico": tecnico,
              **valoraciones, "fortalezas": fortalezas, "debilidades": debilidades,
              "recomendaciones": recomendaciones}
    try:
        with st.spinner("Guardando informe…"):
            identificador = servicio.guardar_en_proveedor(proveedor, campos)
    except (servicio.ValidacionError, servicio.ConflictoError) as error:
        st.error(str(error))
        return
    except (SQLAlchemyError, KeyError, OSError):
        st.error("No se pudo confirmar el guardado. Actualiza el historial antes de reintentar.")
        return
    st.session_state["lecturas"] = {}
    st.session_state["informes_version"] = version + 1
    st.session_state["informes_guardado"] = f"Informe {identificador} guardado en {etiqueta}."
    st.rerun()
