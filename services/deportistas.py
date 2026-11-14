"""Altas y cambios de ficha: SQL parametrizado y transacciones atómicas."""
from datetime import date
import secrets

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


CAMPOS = ("nombre", "apellidos", "fecha_nacimiento", "sexo", "id_club")


class ValidacionError(ValueError):
    """Datos no válidos; el mensaje se puede mostrar al usuario."""


class ConflictoError(ValueError):
    """Documento duplicado o ficha modificada por otra persona."""


def validar(campos):
    datos = {}
    for campo, maximo in (("dni", 20), ("nombre", 100), ("apellidos", 150)):
        valor = campos.get(campo)
        if not isinstance(valor, str) or not valor.strip():
            raise ValidacionError(f"El campo {campo} es obligatorio.")
        valor = valor.strip()
        if campo == "dni":
            valor = valor.upper()
        if len(valor) > maximo:
            raise ValidacionError(f"El campo {campo} admite hasta {maximo} caracteres.")
        datos[campo] = valor
    nacimiento = campos.get("fecha_nacimiento")
    if nacimiento is not None and (type(nacimiento) is not date or nacimiento > date.today()):
        raise ValidacionError("La fecha de nacimiento debe ser una fecha válida y no futura.")
    sexo = campos.get("sexo")
    if sexo not in (None, "Femenino", "Masculino"):
        raise ValidacionError("Selecciona un sexo válido o Sin registrar.")
    club = campos.get("id_club")
    if club is not None and (type(club) is not int or club <= 0):
        raise ValidacionError("Selecciona un club válido o Sin club.")
    datos.update(fecha_nacimiento=nacimiento, sexo=sexo, id_club=club)
    return datos


def _comprobar_club(conexion, club):
    if club is not None and conexion.execute(text(
        "SELECT id_club FROM public.club WHERE id_club = :club"
    ), {"club": club}).first() is None:
        raise ValidacionError("El club seleccionado ya no existe. Actualiza los datos.")


def documento_para_alta(conexion, documento):
    """Usa un ID reconocible como provisional cuando aún no hay documento."""
    if documento is not None and (not isinstance(documento, str) or documento.strip()):
        return documento
    for _ in range(10):
        provisional = 'TEMP-' + secrets.token_hex(6).upper()
        if not conexion.execute(text('SELECT dni FROM public.deportista WHERE UPPER(dni)=:dni'), {'dni': provisional}).first():
            return provisional
    raise ConflictoError('No se pudo asignar un identificador provisional único. Reintenta el alta.')


def datos_pendientes(engine):
    """Fichas con documento provisional o sin nacimiento, sin cargar historias."""
    with engine.connect() as c:
        filas = c.execute(text('''SELECT d.dni,d.nombre,d.apellidos,d.fecha_nacimiento,d.id_club,
            cl.nombre AS club,cl.id_federacion,f.nombre AS federacion
            FROM public.deportista d LEFT JOIN public.club cl ON cl.id_club=d.id_club
            LEFT JOIN public.federacion_autonomica f ON f.id_federacion=cl.id_federacion
            WHERE d.fecha_nacimiento IS NULL OR UPPER(d.dni) LIKE 'TEMP-%'
               OR UPPER(d.dni) LIKE 'TEST-%' OR UPPER(d.dni) LIKE 'STDEMO%'
               OR UPPER(d.dni) LIKE 'PRUEBA%'
            ORDER BY f.nombre,cl.nombre,d.apellidos,d.nombre,d.dni''')).mappings()
        return [dict(r, sin_dni=r['dni'].upper().startswith(('TEMP-','TEST-','STDEMO','PRUEBA')),
                     sin_nacimiento=r['fecha_nacimiento'] is None) for r in filas]


def crear_deportista(engine, campos):
    try:
        with engine.begin() as conexion:
            datos = validar({**campos, 'dni': documento_para_alta(conexion, campos.get('dni'))})
            _comprobar_club(conexion, datos["id_club"])
            existente = conexion.execute(text(
                "SELECT dni FROM public.deportista WHERE UPPER(dni) = :dni"
            ), {"dni": datos["dni"]}).first()
            if existente:
                raise ConflictoError("Ya existe un deportista con ese documento. Utiliza Editar ficha.")
            conexion.execute(text("""
                INSERT INTO public.deportista
                    (dni, nombre, apellidos, fecha_nacimiento, sexo, id_club)
                VALUES (:dni, :nombre, :apellidos, :fecha_nacimiento, :sexo, :id_club)
            """), datos)
    except IntegrityError:
        raise ConflictoError("No se pudo guardar: el documento ya existe o el club ha cambiado. Actualiza los datos.") from None
    return datos["dni"]


def actualizar_deportista(engine, campos, original):
    datos = validar(campos)
    parametros = {**datos, "dni_original": original["dni"]}
    for campo in CAMPOS:
        parametros["antes_" + campo] = original[campo]
    # Comparación optimista de TODOS los campos de la ficha. El UPDATE es atómico:
    # si otro usuario guardó cambios tras abrir el formulario, no se sobrescriben.
    condiciones = " AND ".join(
        f"{campo} IS NOT DISTINCT FROM :antes_{campo}" for campo in CAMPOS
    )
    try:
        with engine.begin() as conexion:
            _comprobar_club(conexion, datos["id_club"])
            duplicado = conexion.execute(text('SELECT dni FROM public.deportista WHERE UPPER(dni)=:dni AND dni<>:original'),
                {'dni': datos['dni'], 'original': original['dni']}).first()
            if duplicado:
                raise ConflictoError('Ese documento ya pertenece a otra ficha. No se han fusionado ni modificado sus datos.')
            resultado = conexion.execute(text("""
                UPDATE public.deportista
                SET dni=:dni, nombre=:nombre, apellidos=:apellidos,
                    fecha_nacimiento=:fecha_nacimiento, sexo=:sexo, id_club=:id_club
                WHERE dni=:dni_original AND """ + condiciones), parametros)
            if resultado.rowcount != 1:
                raise ConflictoError("La ficha cambió o fue eliminada desde que la abriste. Recarga la ficha antes de guardar.")
    except IntegrityError:
        raise ConflictoError("No se pudo guardar: los datos relacionados han cambiado. Recarga la ficha.") from None
    # Las referencias del modelo usan ON UPDATE CASCADE: conservan la misma ficha.
    return datos['dni']


def guardar_en_proveedor(proveedor, campos, original=None):
    # Se crea un motor de escritura SOLO al guardar, separado de los motores de
    # solo lectura de la interfaz. No escribe en el otro proveedor.
    from database.database import crear_engine
    motor = crear_engine(proveedor)
    try:
        if original is None:
            return crear_deportista(motor, campos)
        return actualizar_deportista(motor, campos, original)
    finally:
        motor.dispose()
