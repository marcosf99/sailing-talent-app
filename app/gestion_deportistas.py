"""Formularios de alta y edición. Solo envían cambios al pulsar Guardar."""
from datetime import date

import streamlit as st
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import datos
from services import deportistas


ERRORES_CONEXION = (SQLAlchemyError, KeyError, OSError)


def cargar_original(motor, dni):
    with motor.connect() as conexion:
        fila = conexion.execute(text("""
            SELECT dni, nombre, apellidos, fecha_nacimiento, sexo, id_club
            FROM public.deportista WHERE dni=:dni
        """), {"dni": dni}).mappings().first()
        return dict(fila) if fila else None


def mostrar(proveedor, motor, lectura):
    st.title("Gestión de deportistas")
    st.write("Añade regatistas o actualiza sus datos personales y su club.")
    etiqueta_proveedor = "Supabase" if proveedor == "supabase" else "Google Cloud SQL"
    st.info(f"Los cambios se guardarán únicamente en {etiqueta_proveedor}. La otra base no se sincroniza automáticamente.")
    st.caption("Si aún no conoces el DNI, deja el documento vacío: se asignará un identificador provisional TEMP-. Después puedes sustituirlo por el DNI en Editar ficha, conservando el historial.")
    mensaje = st.session_state.pop("gestion_guardado", None)
    if mensaje:
        st.success(mensaje)
    clubes = lectura((proveedor, "clubes"), datos.cargar_clubes, motor)
    federaciones = lectura((proveedor, "federaciones"), datos.cargar_federaciones, motor)
    nombres_federacion = {f["id_federacion"]: f["nombre"] for f in federaciones}
    nombres_club = {c["id_club"]: f'{c["nombre"]} · {c["federacion"]}' for c in clubes}
    modo = st.radio("Operación", ["Añadir deportista", "Editar ficha"], horizontal=True, key="gestion_modo")
    original = None
    if modo == "Editar ficha":
        with st.form("gestion_busqueda"):
            busqueda = st.text_input("Buscar ficha por nombre o club", key="gestion_texto")
            enviado = st.form_submit_button("Buscar ficha")
        if enviado:
            st.session_state["gestion_busqueda_aplicada"] = busqueda.strip()
            st.session_state.pop("gestion_documento", None)
            st.session_state.pop("gestion_original", None)
        texto = st.session_state.get("gestion_busqueda_aplicada", "")
        personas = lectura((proveedor, "buscar", (texto, None)), datos.buscar, motor, texto, None)
        if not personas:
            st.info("No se han encontrado fichas. Cambia la búsqueda o añade un deportista.")
            return
        if len(personas) > 500:
            st.warning("Se muestran las primeras 500 fichas. Precisa la búsqueda.")
            personas = personas[:500]
        mapa = {p["dni"]: p for p in personas}
        if st.session_state.get("gestion_documento") not in mapa:
            st.session_state.pop("gestion_documento", None)
        dni = st.selectbox("Ficha que deseas editar", list(mapa), key="gestion_documento",
                           format_func=lambda d: f'{mapa[d]["nombre"]} {mapa[d]["apellidos"]} · {d}')
        clave_original = (proveedor, dni)
        if st.button("Recargar ficha"):
            st.session_state.pop("gestion_original", None)
            st.session_state["gestion_version"] = st.session_state.get("gestion_version", 0) + 1
        guardado = st.session_state.get("gestion_original")
        if guardado is None or guardado[0] != clave_original:
            original = cargar_original(motor, dni)
            if original is None:
                st.warning("Esta ficha ya no existe. Actualiza los datos.")
                return
            st.session_state["gestion_original"] = (clave_original, original)
        else:
            original = guardado[1]
    base = original or {"dni": "", "nombre": "", "apellidos": "", "fecha_nacimiento": None, "sexo": None, "id_club": None}
    if base["id_club"] is not None and base["id_club"] not in nombres_club:
        st.error("El club de esta ficha no está disponible. Actualiza los datos antes de editarla.")
        return
    version = st.session_state.get("gestion_version", 0)
    clave = f'{proveedor}_{base["dni"] or "nuevo"}_{version}'
    # Widgets normales: cambiar de federación actualiza los clubes al instante
    # y conserva el resto del borrador. La escritura sigue ligada al botón.
    with st.container(border=True):
        a, b = st.columns(2)
        documento = a.text_input("DNI / documento", value=base["dni"], max_chars=20, key="gestion_dni_" + clave,
                                 help="Opcional al crear: vacío genera un identificador provisional. Al editar, conserva el identificador o escribe el DNI conocido.")
        nombre = b.text_input("Nombre *", value=base["nombre"], max_chars=100, key="gestion_nombre_" + clave)
        apellidos = st.text_input("Apellidos *", value=base["apellidos"], max_chars=150, key="gestion_apellidos_" + clave)
        a, b = st.columns(2)
        nacimiento = a.date_input("Fecha de nacimiento (opcional)", value=base["fecha_nacimiento"],
                                 min_value=date(1900, 1, 1), max_value=date.today(), format="DD/MM/YYYY", key="gestion_nacimiento_" + clave)
        sexos = [None, "Femenino", "Masculino"]
        sexo = b.selectbox("Sexo", sexos, index=sexos.index(base["sexo"]), format_func=lambda s: s or "Sin registrar", key="gestion_sexo_" + clave)
        federacion_original = next(
            (c["id_federacion"] for c in clubes if c["id_club"] == base["id_club"]), None
        )
        opciones_federacion = [None] + list(nombres_federacion)
        federacion = st.selectbox(
            "Federación autonómica", opciones_federacion,
            index=opciones_federacion.index(federacion_original),
            format_func=lambda f: "Todas las federaciones" if f is None else nombres_federacion[f],
            key="gestion_federacion_" + clave,
        )
        filtrados = [c for c in clubes if federacion is None or c["id_federacion"] == federacion]
        opciones = [None] + [c["id_club"] for c in filtrados]
        club_inicial = base["id_club"] if base["id_club"] in opciones else None
        club = st.selectbox(
            "Club", opciones, index=opciones.index(club_inicial),
            format_func=lambda c: "Sin club" if c is None else nombres_club[c],
            key="gestion_club_" + clave,
        )
        if federacion is not None and not filtrados:
            st.info("No hay clubes registrados en esta federación.")
        st.caption("Si eliges Sin club, el deportista no quedará vinculado a ninguna federación.")
        st.caption("* Campos obligatorios. Comprueba los datos antes de guardar.")
        guardar = st.button("Guardar cambios" if original else "Crear deportista", type="primary", key="gestion_guardar_" + clave)
    if not guardar:
        return
    campos = dict(dni=documento, nombre=nombre, apellidos=apellidos,
                  fecha_nacimiento=nacimiento, sexo=sexo, id_club=club)
    try:
        with st.spinner("Guardando ficha…"):
            resultado = deportistas.guardar_en_proveedor(proveedor, campos, original)
    except (deportistas.ValidacionError, deportistas.ConflictoError) as error:
        st.error(str(error))
        return
    except ERRORES_CONEXION:
        st.error("No se pudo confirmar el guardado. Comprueba la conexión y busca el documento antes de reintentar; evita crear una ficha duplicada.")
        return
    st.session_state["lecturas"] = {}
    st.session_state.pop("gestion_original", None)
    st.session_state["gestion_version"] = version + 1
    st.session_state["gestion_guardado"] = f"Ficha {resultado} guardada en {etiqueta_proveedor}."
    st.rerun()
