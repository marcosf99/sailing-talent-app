"""Creación y finalización de unidades, sin eliminar su historial."""
from datetime import date

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from app import datos
from services import unidades_competitivas as servicio


def _guardar(proveedor, operacion, campos):
    try:
        with st.spinner("Guardando unidad…"):
            identificador = servicio.guardar_en_proveedor(proveedor, operacion, campos)
    except (servicio.ValidacionError, servicio.ConflictoError) as error:
        st.error(str(error))
        return
    except (SQLAlchemyError, KeyError, OSError):
        st.error("No se pudo confirmar el guardado. Actualiza la lista de unidades antes de reintentar.")
        return
    st.session_state["lecturas"] = {}
    st.session_state["unidades_version"] = st.session_state.get("unidades_version", 0) + 1
    accion = "creada" if operacion == "crear" else "finalizada"
    st.session_state["unidades_guardado"] = f"Unidad {identificador} {accion} correctamente."
    st.rerun()


def mostrar(proveedor, motor, lectura):
    st.title("Unidades competitivas")
    st.write("Crea equipos y finaliza su actividad conservando la trayectoria y los resultados.")
    etiqueta = "Supabase" if proveedor == "supabase" else "Google Cloud SQL"
    st.info(f"Los cambios se guardarán únicamente en {etiqueta}.")
    st.caption("Un regatista no puede pertenecer a dos unidades de la misma clase con fechas solapadas. Las fechas de inicio y fin se consideran incluidas.")
    st.caption("Las unidades permanecen abiertas hasta su cierre manual. Optimist es la excepción: al superar el año en que cumple 14, el cierre por edad se aplica al abrir la aplicación. Sin nacimiento registrado no se calcula el cierre.")
    mensaje = st.session_state.pop("unidades_guardado", None)
    if mensaje:
        st.success(mensaje)
    clases = lectura((proveedor, "clases"), datos.cargar_clases, motor)
    if not clases:
        st.info("Primero registra las clases en la base de datos.")
        return
    mapa = {c["id_clase"]: c for c in clases}
    clase = st.selectbox("Filtrar listado por clase", list(mapa), format_func=lambda c: mapa[c]["nombre"], key="unidades_filtro_clase")
    unidades = lectura((proveedor, "unidades", clase), servicio.listar_unidades, motor, clase)
    if len(unidades) > 500:
        st.warning("Se muestran las primeras 500 unidades de esta clase.")
        unidades = unidades[:500]
    st.subheader("Unidades registradas")
    if unidades:
        filas = [{"Unidad": u["id_unidad"], "Clase": u["clase"], "Inicio": u["fecha_inicio"],
                  "Fin": u["fecha_fin"], "Estado": "Finalizada" if u["fecha_fin"] else "Abierta",
                  "Miembros": " · ".join(u["miembros"])} for u in unidades]
        st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch")
    else:
        st.info("No hay unidades registradas en esta clase.")
    operacion = st.radio("Operación", ["Crear unidad", "Finalizar unidad"], horizontal=True, key="unidades_operacion")
    version = st.session_state.get("unidades_version", 0)
    if operacion == "Finalizar unidad":
        abiertas = {u["id_unidad"]: u for u in unidades if u["fecha_fin"] is None}
        if not abiertas:
            st.info("No hay unidades abiertas en esta clase para finalizar.")
            return
        identificador = st.selectbox("Unidad que deseas finalizar", list(abiertas),
                                    format_func=lambda u: f'{u} · {" · ".join(abiertas[u]["miembros"])}', key="unidades_finalizar")
        with st.form(f"unidades_cierre_{proveedor}_{clase}_{identificador}_{version}"):
            fecha = st.date_input("Fecha de finalización", value=date.today(), min_value=min(date(1900, 1, 1), abiertas[identificador]["fecha_inicio"]), max_value=date.today(), format="DD/MM/YYYY")
            st.caption("La fecha no puede ser anterior al inicio ni al último día de una competición con resultados de esta unidad. No se borrará ningún dato histórico.")
            cerrar = st.form_submit_button("Finalizar unidad", type="primary")
        if cerrar:
            _guardar(proveedor, "finalizar", {"id_unidad": identificador, "fecha_fin": fecha})
        return
    with st.form("unidades_busqueda"):
        texto = st.text_input("Buscar miembros por nombre o club", key="unidades_texto")
        buscar = st.form_submit_button("Buscar miembros")
    if buscar:
        st.session_state["unidades_busqueda_aplicada"] = texto.strip()
    texto = st.session_state.get("unidades_busqueda_aplicada", "")
    personas = lectura((proveedor, "buscar", (texto, None)), datos.buscar, motor, texto, None)
    if not personas:
        st.info("No se han encontrado regatistas. Cambia la búsqueda o crea sus fichas.")
        return
    if len(personas) > 500:
        st.warning("Se muestran los primeros 500 regatistas. Precisa la búsqueda por nombre o club.")
        personas = personas[:500]
    miembros = {p["dni"]: p for p in personas}
    def etiqueta_miembro(d):
        if d is None:
            return "Selecciona un regatista"
        p = miembros[d]
        return f'{p["nombre"]} {p["apellidos"]} · {p["club"] or "Sin club"} · {d}'
    st.subheader("Nueva unidad competitiva")
    clave = f"{proveedor}_{version}"
    # La clase de creación es independiente del filtro del listado. Estos
    # widgets actualizan los puestos sin perder la fecha ni el patrón elegido.
    with st.container(border=True):
        clase_nueva = st.selectbox(
            "Clase de la nueva unidad", list(mapa),
            format_func=lambda c: mapa[c]["nombre"], key="unidades_clase_nueva_" + clave,
        )
        tripulantes = mapa[clase_nueva]["numero_tripulantes"]
        if tripulantes not in (1, 2):
            st.info("Esta pantalla admite clases individuales y dobles.")
            return
        st.caption(f'Clase {mapa[clase_nueva]["nombre"]}: {tripulantes} tripulante(s).')
        inicio = st.date_input("Fecha de inicio", value=date.today(), min_value=date(1900, 1, 1), max_value=date.today(), format="DD/MM/YYYY", key="unidades_inicio_" + clave)
        patron = st.selectbox("Patrón", [None] + list(miembros), format_func=etiqueta_miembro, key="unidades_patron_" + clave)
        tripulante = None
        if tripulantes == 2:
            tripulante = st.selectbox("Tripulante", [None] + list(miembros), format_func=etiqueta_miembro, key="unidades_tripulante_" + clave)
        crear = st.button("Crear unidad", type="primary", key="unidades_crear_" + clave)
    if crear:
        _guardar(proveedor, "crear", {"id_clase": clase_nueva, "fecha_inicio": inicio, "patron": patron, "tripulante": tripulante})
