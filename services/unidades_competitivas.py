"""Creación y finalización de equipos, con historial y transacciones."""
from datetime import date

from sqlalchemy import Date, bindparam, text
from sqlalchemy.exc import IntegrityError

from services.deportistas import ValidacionError, ConflictoError


def _fecha(valor, etiqueta):
    if type(valor) is not date or valor > date.today():
        raise ValidacionError(f"La fecha de {etiqueta} debe ser válida y no futura.")
    return valor


def _documento(valor):
    if not isinstance(valor, str) or not valor.strip() or len(valor.strip()) > 20:
        raise ValidacionError("Selecciona un deportista válido para cada puesto.")
    return valor.strip()


def crear_unidad(engine, campos):
    clase = campos.get("id_clase")
    if type(clase) is not int or clase <= 0:
        raise ValidacionError("Selecciona una clase válida.")
    inicio = _fecha(campos.get("fecha_inicio"), "inicio")
    patron = _documento(campos.get("patron"))
    tripulante = campos.get("tripulante")
    tripulante = _documento(tripulante) if tripulante is not None else None
    if patron == tripulante:
        raise ValidacionError("Patrón y tripulante deben ser personas distintas.")
    miembros = [patron] + ([tripulante] if tripulante else [])
    try:
        with engine.begin() as conexion:
            fila = conexion.execute(text("""
                SELECT nombre, numero_tripulantes FROM public.clase
                WHERE id_clase=:clase FOR SHARE
            """), {"clase": clase}).mappings().first()
            if fila is None:
                raise ValidacionError("La clase seleccionada ya no existe.")
            if fila["numero_tripulantes"] not in (1, 2):
                raise ValidacionError("Esta pantalla admite clases de uno o dos tripulantes.")
            if fila["numero_tripulantes"] != len(miembros):
                raise ValidacionError(f'La clase {fila["nombre"]} necesita exactamente {fila["numero_tripulantes"]} tripulantes.')
            # Orden estable de bloqueo para evitar equipos simultáneos del mismo
            # deportista cuando dos usuarios guardan desde esta aplicación.
            consulta = text("""
                SELECT dni, fecha_nacimiento FROM public.deportista
                WHERE dni IN :documentos ORDER BY dni FOR UPDATE
            """).bindparams(bindparam("documentos", expanding=True)).columns(fecha_nacimiento=Date())
            personas = conexion.execute(consulta, {"documentos": sorted(miembros)}).mappings().all()
            if len(personas) != len(miembros):
                raise ValidacionError("Algún deportista ya no existe. Actualiza la búsqueda.")
            for persona in personas:
                if persona["fecha_nacimiento"] and inicio < persona["fecha_nacimiento"]:
                    raise ValidacionError("La unidad no puede comenzar antes del nacimiento de sus miembros.")
            # La nueva unidad no tiene fecha final: cualquier unidad de la misma
            # clase que termine después del inicio produce solapamiento.
            consulta = text("""
                SELECT fp.dni_deportista, u.id_unidad
                FROM public.forma_parte fp
                JOIN public.unidad_competitiva u ON u.id_unidad=fp.id_unidad
                WHERE fp.dni_deportista IN :documentos AND u.id_clase=:clase
                  AND (u.fecha_fin IS NULL OR u.fecha_fin>=:inicio)
            """).bindparams(bindparam("documentos", expanding=True))
            conflicto = conexion.execute(consulta, {"documentos": miembros, "clase": clase, "inicio": inicio}).first()
            if conflicto:
                raise ConflictoError("Algún miembro ya pertenece a una unidad de esta clase con fechas solapadas. Finaliza la anterior o revisa la fecha de inicio.")
            identificador = conexion.execute(text("""
                INSERT INTO public.unidad_competitiva (fecha_inicio, fecha_fin, id_clase)
                VALUES (:inicio, NULL, :clase) RETURNING id_unidad
            """), {"inicio": inicio, "clase": clase}).scalar_one()
            pertenencias = [{"dni": patron, "unidad": identificador, "rol": "Patron"}]
            if tripulante:
                pertenencias.append({"dni": tripulante, "unidad": identificador, "rol": "Tripulante"})
            conexion.execute(text("""
                INSERT INTO public.forma_parte (dni_deportista,id_unidad,rol)
                VALUES (:dni,:unidad,:rol)
            """), pertenencias)
    except IntegrityError:
        raise ConflictoError("No se pudo crear el equipo: los datos relacionados han cambiado. Actualiza los datos.") from None
    return identificador


def finalizar_unidad(engine, identificador, fecha_fin):
    if type(identificador) is not int or identificador <= 0:
        raise ValidacionError("Selecciona una unidad válida.")
    fecha_fin = _fecha(fecha_fin, "finalización")
    with engine.begin() as conexion:
        unidad = conexion.execute(text("""
            SELECT fecha_inicio, fecha_fin FROM public.unidad_competitiva
            WHERE id_unidad=:unidad FOR UPDATE
        """).columns(fecha_inicio=Date(), fecha_fin=Date()), {"unidad": identificador}).mappings().first()
        if unidad is None:
            raise ConflictoError("La unidad ya no existe. Actualiza los datos.")
        if unidad["fecha_fin"] is not None:
            raise ConflictoError("La unidad ya está finalizada. Se conserva su fecha de finalización.")
        if fecha_fin < unidad["fecha_inicio"]:
            raise ValidacionError("La fecha de finalización no puede ser anterior al inicio.")
        ultima = conexion.execute(text("""
            SELECT MAX(c.fecha_fin) AS ultima FROM public.participa_en p
            JOIN public.competicion c ON c.id_competicion=p.id_competicion
            WHERE p.id_unidad=:unidad
        """).columns(ultima=Date()), {"unidad": identificador}).scalar_one()
        if ultima and fecha_fin < ultima:
            raise ValidacionError("La unidad tiene resultados en una competición posterior a esa fecha. Finaliza como mínimo el último día de esa regata.")
        conexion.execute(text("""
            UPDATE public.unidad_competitiva SET fecha_fin=:fin
            WHERE id_unidad=:unidad
        """), {"fin": fecha_fin, "unidad": identificador})
    return identificador


def listar_unidades(engine, id_clase=None):
    parametros = {}
    filtro = ""
    if id_clase is not None:
        filtro = "WHERE id_clase=:clase"
        parametros["clase"] = id_clase
    consulta = text("""
        WITH seleccion AS (
            SELECT id_unidad, fecha_inicio, fecha_fin, id_clase
            FROM public.unidad_competitiva """ + filtro + """
            ORDER BY fecha_inicio DESC, id_unidad DESC LIMIT 501
        )
        SELECT u.id_unidad, u.fecha_inicio, u.fecha_fin, c.nombre AS clase,
               fp.dni_deportista, fp.rol, d.nombre, d.apellidos
        FROM seleccion u JOIN public.clase c ON c.id_clase=u.id_clase
        LEFT JOIN public.forma_parte fp ON fp.id_unidad=u.id_unidad
        LEFT JOIN public.deportista d ON d.dni=fp.dni_deportista
        ORDER BY u.fecha_inicio DESC, u.id_unidad DESC, fp.rol, fp.dni_deportista
    """).columns(fecha_inicio=Date(), fecha_fin=Date())
    with engine.connect() as conexion:
        filas = conexion.execute(consulta, parametros).mappings().all()
    unidades = {}
    for fila in filas:
        clave = fila["id_unidad"]
        if clave not in unidades:
            unidades[clave] = {k: fila[k] for k in ("id_unidad", "fecha_inicio", "fecha_fin", "clase")}
            unidades[clave]["miembros"] = []
        if fila["dni_deportista"]:
            rol = "Patrón" if fila["rol"] == "Patron" else "Tripulante" if fila["rol"] == "Tripulante" else "Sin rol"
            unidades[clave]["miembros"].append(f'{fila["nombre"]} {fila["apellidos"]} ({rol})')
    return list(unidades.values())


def guardar_en_proveedor(proveedor, operacion, campos):
    from database.database import crear_engine
    motor = crear_engine(proveedor)
    try:
        if operacion == "crear":
            return crear_unidad(motor, campos)
        if operacion == "finalizar":
            return finalizar_unidad(motor, campos.get("id_unidad"), campos.get("fecha_fin"))
        raise ValidacionError("Operación no válida.")
    finally:
        motor.dispose()
