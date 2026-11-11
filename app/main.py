"""Inicio: python -m streamlit run app/main.py [-- --db-provider supabase]."""
import argparse
from datetime import date
from pathlib import Path
import os
import sys
from time import monotonic

# Streamlit ejecuta app/main.py; añadir la raíz permite importar app y database.
RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from app import datos, candidatos, gestion_deportistas, antropometria, unidades_competitivas, informes, importaciones, revision_participantes
from services import edad_clases
from app import consulta_informes


st.set_page_config(page_title="Sailing Talent", page_icon="⛵", layout="wide")


@st.cache_resource(show_spinner=False)
def motor(proveedor):
    # Se comparte el pool de conexiones, nunca una sesión SQLAlchemy.
    return datos.crear_motor_lectura(proveedor)


def lectura(clave, funcion, *argumentos):
    # Datos personales únicamente en la sesión del navegador; caducidad 60 s.
    cache = st.session_state.setdefault("lecturas", {})
    ahora = monotonic()
    for antigua in list(cache):
        if ahora - cache[antigua][0] >= 60:
            del cache[antigua]
    if clave not in cache:
        if len(cache) >= 40:
            cache.clear()
        cache[clave] = (ahora, funcion(*argumentos))
    return cache[clave][1]


def revisar_cierres_por_edad(proveedor):
    """Comprobar el día real, independientemente de la fecha histórica de consulta."""
    clave = 'edad_revisada_' + proveedor
    avisos = 'edad_incidencias_' + proveedor
    if st.session_state.get(clave) != date.today():
        try:
            pendientes = edad_clases.pendientes_por_edad(motor(proveedor))
            if pendientes:
                resultado = edad_clases.cerrar_en_proveedor(proveedor)
                st.session_state[avisos] = resultado['incidencias']
                if resultado['cerradas']:
                    st.session_state['lecturas'] = {}
            else:
                st.session_state[avisos] = []
            st.session_state[clave] = date.today()
        except (SQLAlchemyError, KeyError, OSError):
            st.warning('No se pudieron comprobar los cierres por edad de Optimist. Revisa la conexión.')
            return
    for aviso in st.session_state.get(avisos, []):
        st.warning(aviso)


def valor(numero, sufijo=""):
    return "—" if numero is None else f"{numero:g}{sufijo}"


def tabla(filas, columnas):
    marco = pd.DataFrame(filas).reindex(columns=list(columnas)).rename(columns=columnas)
    for col in marco:
        if col in ("Puesto general", "Puesto categoría"):
            marco[col] = pd.to_numeric(marco[col], errors="coerce").astype("Int64")
        elif col in ("Puntos", "Altura (cm)", "Peso (kg)", "Envergadura (cm)", "Grasa corporal (%)"):
            marco[col] = pd.to_numeric(marco[col], errors="coerce")
    st.dataframe(marco, hide_index=True, width="stretch")
    return marco


def evolucion(filas):
    st.subheader("Evolución física")
    if not filas:
        st.info("No hay mediciones registradas hasta la fecha de consulta.")
        return
    columnas = {
        "fecha": "Fecha", "altura": "Altura (cm)", "peso": "Peso (kg)",
        "envergadura": "Envergadura (cm)", "porcentaje_graso": "Grasa corporal (%)",
    }
    marco = tabla(filas, columnas)
    disponibles = [col for col in list(columnas.values())[1:] if marco[col].notna().any()]
    if not disponibles:
        st.info("Las mediciones registradas no contienen valores para representar.")
        return
    indicador = st.selectbox("Indicador", disponibles, key="indicador")
    serie = marco[["Fecha", indicador]].dropna().drop_duplicates("Fecha", keep="last")
    if len(serie) < 2:
        st.caption("Se necesitan dos fechas con valores para mostrar la evolución.")
        return
    st.line_chart(serie, x="Fecha", y=indicador, x_label="Fecha", y_label=indicador)
    st.caption("Valores registrados; si hay varias mediciones en un día, se muestra la última.")


def configuracion():
    argumentos = argparse.ArgumentParser(add_help=False)
    argumentos.add_argument("--db-provider", choices=["supabase", "cloudsql"])
    args, _ = argumentos.parse_known_args()
    inicial = args.db_provider or os.getenv("DB_PROVIDER", "supabase").strip().lower()
    opciones = ["supabase", "cloudsql"]
    if inicial not in opciones:
        inicial = "supabase"

    with st.sidebar:
        st.header("Sailing Talent")
        proveedor = st.selectbox(
            "Base de datos", opciones, index=opciones.index(inicial),
            format_func=lambda p: "Supabase" if p == "supabase" else "Google Cloud SQL",
            key="proveedor",
        )
        fecha = st.date_input(
            "Fecha de consulta", value=date.today(), min_value=date(1900, 1, 1),
            max_value=date.today(), help="Edad, mediciones y resultados se consultan hasta esta fecha.",
        )
        if st.button("Actualizar datos", width="stretch"):
            st.session_state["lecturas"] = {}
            st.session_state.pop('edad_revisada_' + proveedor, None)
        st.caption("Consultas y gestión deportiva.")
        if proveedor == "cloudsql":
            st.caption("Mantén Cloud SQL Auth Proxy abierto en el puerto configurado.")

    # Evita conservar selecciones y registros de otro proveedor.
    if st.session_state.get("proveedor_anterior") != proveedor:
        st.session_state["lecturas"] = {}
        for clave in ("regatista", "club", "indicador", "criterios", "filtros_candidatos_aplicados",
                      "comparar_seleccion", "comparar_indicador", "cand_clase", "cand_sexo",
                      "cand_usar_edad", "cand_edad_min", "cand_edad_max", "cand_usar_altura", "cand_altura"):
            st.session_state.pop(clave, None)
        for clave in list(st.session_state):
            if clave.startswith(("gestion_", "antropo_", "unidades_", "informes_", "importacion_", "revision_", "consulta_informe_", "comparar_informe_")):
                st.session_state.pop(clave, None)
        st.session_state["proveedor_anterior"] = proveedor

    if st.session_state.get("fecha_anterior") != fecha:
        st.session_state.pop("comparar_seleccion", None)
        st.session_state["fecha_anterior"] = fecha
    return proveedor, fecha


def pagina_consulta():
    st.title("Sailing Talent")
    st.write("Consulta de regatistas y seguimiento de su trayectoria deportiva.")
    st.caption("Primera versión de consulta · Datos de prueba ficticios")

    proveedor, fecha = PROVEEDOR, FECHA

    try:
        conexion = motor(proveedor)
        with st.spinner("Consultando clubes…"):
            clubes = lectura((proveedor, "clubes"), datos.cargar_clubes, conexion)
    except (SQLAlchemyError, KeyError, ValueError, OSError):
        st.error("No se pudo conectar con la base seleccionada. Revisa su configuración en .env y la conexión a Internet.")
        if proveedor == "cloudsql":
            st.info("Comprueba que el proxy esté abierto. Si tu red lo bloquea, utiliza la conexión móvil que funcionó en las pruebas.")
        st.stop()

    etiquetas_club = {c["id_club"]: f'{c["nombre"]} · {c["federacion"]}' for c in clubes}
    with st.form("buscar_regatistas"):
        izquierda, derecha = st.columns(2)
        with izquierda:
            texto = st.text_input("Nombre, apellidos o club", placeholder="Ej.: Alba o Portosín")
        with derecha:
            club = st.selectbox(
                "Club", [None] + list(etiquetas_club),
                format_func=lambda c: "Todos los clubes" if c is None else etiquetas_club[c], key="club",
            )
        buscar = st.form_submit_button("Buscar", type="primary")
    if buscar:
        st.session_state["criterios"] = (texto.strip(), club)
        st.session_state.pop("regatista", None)
    criterios = st.session_state.get("criterios", ("", None))

    try:
        with st.spinner("Buscando regatistas…"):
            filas = lectura((proveedor, "buscar", criterios), datos.buscar, conexion, *criterios)
        if not filas:
            st.info("No se han encontrado regatistas. Prueba con otro nombre o club.")
            return
        if len(filas) > 500:
            st.warning("Se muestran los primeros 500 resultados. Precisa la búsqueda para encontrar otros regatistas.")
            filas = filas[:500]
        st.caption(f"{len(filas)} regatistas encontrados")
        personas = {f["dni"]: f for f in filas}
        if st.session_state.get("regatista") not in personas:
            st.session_state.pop("regatista", None)
        dni = st.selectbox(
            "Regatista", list(personas), key="regatista",
            format_func=lambda d: f'{personas[d]["nombre"]} {personas[d]["apellidos"]} · {personas[d]["club"] or "Sin club"} · {d}',
        )
        with st.spinner("Cargando ficha…"):
            contenido = lectura((proveedor, "ficha", dni, fecha), datos.cargar_ficha, conexion, dni, fecha)
        if contenido is None:
            st.info("La ficha ya no está disponible. Pulsa Actualizar datos.")
            return
    except (SQLAlchemyError, KeyError, ValueError, OSError):
        st.error("No se pudo completar la consulta. Prueba con Actualizar datos y comprueba la conexión.")
        return

    p = contenido["ficha"]
    st.subheader(f'{p["nombre"]} {p["apellidos"]}')
    st.write(f'{p["club"] or "Sin club"} · {p["federacion"] or "Sin federación"}')
    nacimiento = p.get("fecha_nacimiento")
    anio_nacimiento = str(nacimiento.year) if nacimiento is not None else "Sin registrar"
    st.caption(f'{p["sexo"] or "Sexo no registrado"} · Edad: {valor(p["edad"], " años")} · Año de nacimiento: {anio_nacimiento} · Clase activa: {p["clases_activas"] or "Sin unidad activa"}')
    a, b, c = st.columns(3)
    a.metric("Participaciones", p["participaciones"])
    b.metric("Mejor puesto general", valor(p["mejor_puesto"], "º"))
    c.metric("Última altura", valor(p["altura"], " cm"))
    if p["fecha_medicion"]:
        st.caption(f'Última medición: {p["fecha_medicion"].strftime("%d/%m/%Y")}')
    st.caption(f'Información consultada hasta el {fecha.strftime("%d/%m/%Y")}.')

    resultados, fisico, equipos, informes_tecnicos = st.tabs(["Resultados deportivos", "Evolución física", "Trayectoria y equipos", "Informes técnicos"])
    with resultados:
        st.subheader("Resultados deportivos")
        if contenido["resultados"]:
            tabla(contenido["resultados"], {
                "competicion": "Competición", "fecha_inicio": "Inicio", "fecha_fin": "Fin",
                "clase": "Clase", "nivel": "Nivel", "localidad": "Localidad",
                "posicion_general": "Puesto general", "posicion_categoria": "Puesto categoría", "puntos": "Puntos",
            })
            st.caption("En clases dobles, el resultado corresponde al equipo y se comparte entre sus miembros.")
        else:
            st.info("No hay resultados deportivos hasta la fecha de consulta.")
    with fisico:
        evolucion(contenido["mediciones"])
    with equipos:
        st.subheader("Trayectoria por clases y equipos")
        historial = datos.agrupar_equipos(contenido["trayectoria"], fecha)
        if historial:
            st.dataframe(pd.DataFrame(historial), hide_index=True, width="stretch")
        else:
            st.info("El regatista no tiene unidades competitivas registradas.")
    with informes_tecnicos:
        consulta_informes.mostrar_historial(contenido.get('informes', []),
            f'consulta_informe_{proveedor}_{dni}_{fecha.isoformat()}')


def pagina_candidatos():
    try:
        candidatos.mostrar(PROVEEDOR, FECHA, motor(PROVEEDOR), lectura)
    except (SQLAlchemyError, KeyError, ValueError, OSError):
        st.error("No se pudo completar la consulta de candidatos. Revisa la conexión y pulsa Actualizar datos.")
        if PROVEEDOR == "cloudsql":
            st.info("Comprueba que Cloud SQL Auth Proxy siga abierto.")


def pagina_gestion():
    try:
        gestion_deportistas.mostrar(PROVEEDOR, motor(PROVEEDOR), lectura)
    except (SQLAlchemyError, KeyError, ValueError, OSError):
        st.error("No se pudo cargar la gestión de deportistas. Revisa la conexión y pulsa Actualizar datos.")
        if PROVEEDOR == "cloudsql":
            st.info("Comprueba que Cloud SQL Auth Proxy siga abierto.")


def pagina_antropometria():
    try:
        antropometria.mostrar(PROVEEDOR, motor(PROVEEDOR), lectura)
    except (SQLAlchemyError, KeyError, ValueError, OSError):
        st.error("No se pudo cargar el registro de mediciones. Revisa la conexión y pulsa Actualizar datos.")
        if PROVEEDOR == "cloudsql":
            st.info("Comprueba que Cloud SQL Auth Proxy siga abierto.")


def pagina_unidades():
    try:
        unidades_competitivas.mostrar(PROVEEDOR, motor(PROVEEDOR), lectura)
    except (SQLAlchemyError, KeyError, ValueError, OSError):
        st.error("No se pudieron cargar las unidades competitivas. Revisa la conexión y pulsa Actualizar datos.")
        if PROVEEDOR == "cloudsql":
            st.info("Comprueba que Cloud SQL Auth Proxy siga abierto.")


def pagina_informes():
    try:
        informes.mostrar(PROVEEDOR, motor(PROVEEDOR), lectura)
    except (SQLAlchemyError, KeyError, ValueError, OSError):
        st.error("No se pudo cargar la creación de informes. Revisa la conexión y pulsa Actualizar datos.")
        if PROVEEDOR == "cloudsql":
            st.info("Comprueba que Cloud SQL Auth Proxy siga abierto.")


def pagina_importaciones():
    try:
        importaciones.mostrar(PROVEEDOR, motor(PROVEEDOR), lectura)
    except (SQLAlchemyError, KeyError, ValueError, OSError):
        st.error("No se pudo abrir la importación de clasificaciones. Revisa la conexión y la configuración de la base seleccionada.")


def pagina_revision():
    try:
        revision_participantes.mostrar(PROVEEDOR, motor(PROVEEDOR), lectura)
    except (SQLAlchemyError, KeyError, ValueError, OSError):
        st.error("No se pudo abrir la revisión de participantes. Comprueba la conexión y actualiza los datos.")


PROVEEDOR, FECHA = configuracion()
revisar_cierres_por_edad(PROVEEDOR)
st.navigation([
    st.Page(pagina_consulta, title="Consulta de regatistas", default=True),
    st.Page(pagina_candidatos, title="Candidatos y comparación", url_path="candidatos"),
    st.Page(pagina_gestion, title="Gestión de deportistas", url_path="gestion-deportistas"),
    st.Page(pagina_antropometria, title="Registros antropométricos", url_path="registros-antropometricos"),
    st.Page(pagina_unidades, title="Unidades competitivas", url_path="unidades-competitivas"),
    st.Page(pagina_informes, title="Informes técnicos", url_path="informes-tecnicos"),
    st.Page(pagina_importaciones, title="Importar clasificaciones", url_path="importar-clasificaciones"),
    st.Page(pagina_revision, title="Revisión de participantes", url_path="revision-participantes"),
]).run()
