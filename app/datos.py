"""Lecturas para la interfaz; reutiliza las consultas probadas, sin escribir datos."""
from sqlalchemy import event

from database.database import crear_engine
from database import queries
from services import informes, antropometria


def crear_motor_lectura(proveedor):
    motor = crear_engine(proveedor)

    @event.listens_for(motor, "begin")
    def solo_lectura(conexion):
        conexion.exec_driver_sql("SET TRANSACTION READ ONLY")

    return motor


def cargar_clubes(motor):
    return queries.listar_clubes(motor)


def buscar(motor, texto, id_club):
    # Una fila adicional permite detectar si hay que precisar la búsqueda.
    return queries.buscar_deportistas(motor, texto, id_club=id_club, limite=501)


def cargar_ficha(motor, dni, fecha):
    ficha = queries.obtener_ficha_deportista(motor, dni, fecha_referencia=fecha)
    if ficha is None:
        return None
    return {
        "ficha": ficha,
        "mediciones": [r for r in queries.consultar_historial_antropometrico(motor, dni)
                       if r["fecha"] <= fecha],
        "resultados": queries.consultar_resultados_deportista(
            motor, dni, fecha_referencia=fecha
        ),
        "trayectoria": queries.consultar_trayectoria_deportista(
            motor, dni, fecha_referencia=fecha
        ),
        "informes": informes.listar_informes(motor, dni, fecha_referencia=fecha),
    }


def agrupar_equipos(filas, fecha):
    """Agrupa las filas por miembro sin mostrar IDs internos al usuario."""
    equipos = {}
    for fila in filas:
        clave = fila["id_unidad"]
        if clave not in equipos:
            estado = ("Prevista" if fila["fecha_inicio"] > fecha
                      else "Activa" if fila["activa"] else "Finalizada")
            equipos[clave] = {
                "Clase": fila["clase"], "Inicio": fila["fecha_inicio"],
                "Fin": fila["fecha_fin"], "Estado": estado, "Miembros": [],
            }
        rol = {"Patron": "Patrón", "Tripulante": "Tripulante"}.get(fila["rol"], "Sin rol")
        equipos[clave]["Miembros"].append(
            f'{fila["nombre_miembro"]} {fila["apellidos_miembro"]} ({rol})'
        )
    return [{**equipo, "Miembros": " · ".join(equipo["Miembros"])}
            for equipo in equipos.values()]


def cargar_clases(motor):
    return queries.listar_clases(motor)


def cargar_candidatos(motor, filtros, fecha):
    return queries.buscar_candidatos(
        motor, fecha_referencia=fecha, limite=501, **filtros
    )


def comparar(motor, documentos, fecha):
    return queries.comparar_deportistas(motor, documentos, fecha_referencia=fecha)


def cargar_historiales_comparacion(motor, documentos, fecha):
    return antropometria.historiales_para_comparar(motor, documentos, fecha)


def cargar_federaciones(motor):
    return queries.listar_federaciones(motor)
