"""Creación de informes técnicos según el modelo PostgreSQL existente."""
from datetime import date

from sqlalchemy import Date, text
from sqlalchemy.exc import IntegrityError

from services.deportistas import ValidacionError, ConflictoError


VALORACIONES = ("estrategia", "tactica", "trimado", "tecnica")
TEXTOS = ("fortalezas", "debilidades", "recomendaciones")


def validar(campos):
    datos = {}
    for campo in ("dni_deportista", "dni_tecnico"):
        valor = campos.get(campo)
        if not isinstance(valor, str) or not valor.strip() or len(valor.strip()) > 20:
            raise ValidacionError("Selecciona un deportista y un técnico válidos.")
        datos[campo] = valor.strip()
    fecha = campos.get("fecha")
    if type(fecha) is not date or fecha > date.today():
        raise ValidacionError("La fecha del informe es obligatoria y no puede ser futura.")
    datos["fecha"] = fecha
    for campo in VALORACIONES:
        valor = campos.get(campo)
        if valor is not None and (type(valor) is not int or not 1 <= valor <= 5):
            raise ValidacionError("Las valoraciones deben ser enteros entre 1 y 5, o quedar sin valorar.")
        datos[campo] = valor
    for campo in TEXTOS:
        valor = campos.get(campo)
        if valor is not None and not isinstance(valor, str):
            raise ValidacionError("Fortalezas, debilidades y recomendaciones deben ser texto.")
        datos[campo] = valor.strip() or None if valor is not None else None
    return datos


def crear_informe(engine, campos):
    datos = validar(campos)
    try:
        with engine.begin() as conexion:
            deportista = conexion.execute(text("""
                SELECT dni, fecha_nacimiento FROM public.deportista
                WHERE dni=:dni_deportista FOR UPDATE
            """).columns(fecha_nacimiento=Date()), datos).mappings().first()
            if deportista is None:
                raise ValidacionError("El deportista ya no existe. Actualiza la búsqueda.")
            if deportista["fecha_nacimiento"] and datos["fecha"] < deportista["fecha_nacimiento"]:
                raise ValidacionError("El informe no puede ser anterior al nacimiento del deportista.")
            tecnico = conexion.execute(text("""
                SELECT dni FROM public.tecnico WHERE dni=:dni_tecnico FOR KEY SHARE
            """), datos).first()
            if tecnico is None:
                raise ValidacionError("El técnico seleccionado ya no existe. Actualiza los datos.")
            condiciones = " AND ".join(
                f"{campo} IS NOT DISTINCT FROM :{campo}" for campo in VALORACIONES + TEXTOS
            )
            duplicado = conexion.execute(text("""
                SELECT id_informe FROM public.informe
                WHERE dni_deportista=:dni_deportista AND dni_tecnico=:dni_tecnico
                  AND fecha=:fecha AND """ + condiciones), datos).first()
            if duplicado:
                raise ConflictoError("Ya existe un informe idéntico para este deportista, técnico y fecha. No se ha duplicado.")
            identificador = conexion.execute(text("""
                INSERT INTO public.informe (
                    fecha, estrategia, tactica, trimado, tecnica,
                    fortalezas, debilidades, recomendaciones, dni_deportista, dni_tecnico
                ) VALUES (
                    :fecha, :estrategia, :tactica, :trimado, :tecnica,
                    :fortalezas, :debilidades, :recomendaciones, :dni_deportista, :dni_tecnico
                ) RETURNING id_informe
            """), datos).scalar_one()
    except IntegrityError:
        raise ConflictoError("No se pudo guardar porque los datos relacionados han cambiado. Actualiza los datos.") from None
    return identificador


def listar_tecnicos(engine):
    with engine.connect() as conexion:
        return [dict(r) for r in conexion.execute(text("""
            SELECT dni, nombre, apellidos, titulacion FROM public.tecnico
            ORDER BY apellidos, nombre, dni
        """)).mappings()]


def listar_informes(engine, dni):
    with engine.connect() as conexion:
        return [dict(r) for r in conexion.execute(text("""
            SELECT i.id_informe, i.fecha, i.estrategia, i.tactica, i.trimado, i.tecnica,
                   i.fortalezas, i.debilidades, i.recomendaciones, i.dni_deportista,
                   i.dni_tecnico, t.nombre AS nombre_tecnico, t.apellidos AS apellidos_tecnico
            FROM public.informe i JOIN public.tecnico t ON t.dni=i.dni_tecnico
            WHERE i.dni_deportista=:dni
            ORDER BY i.fecha DESC, i.id_informe DESC
        """).columns(fecha=Date()), {"dni": dni}).mappings()]


def guardar_en_proveedor(proveedor, campos):
    from database.database import crear_engine
    motor = crear_engine(proveedor)
    try:
        return crear_informe(motor, campos)
    finally:
        motor.dispose()
