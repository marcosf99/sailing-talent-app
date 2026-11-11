"""Inserción de mediciones; conserva los registros anteriores."""
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import Date, Numeric, bindparam, text
from sqlalchemy.exc import IntegrityError

from services.deportistas import ValidacionError, ConflictoError


MEDIDAS = ("altura", "peso", "envergadura", "porcentaje_graso")
ETIQUETAS = {"altura": "altura", "peso": "peso", "envergadura": "envergadura",
             "porcentaje_graso": "porcentaje graso"}


def validar(campos):
    dni = campos.get("dni_deportista")
    if not isinstance(dni, str) or not dni.strip() or len(dni.strip()) > 20:
        raise ValidacionError("Selecciona un deportista válido.")
    fecha = campos.get("fecha")
    if type(fecha) is not date or fecha > date.today():
        raise ValidacionError("La fecha de medición es obligatoria y no puede ser futura.")
    datos = {"dni_deportista": dni.strip(), "fecha": fecha}
    for campo in MEDIDAS:
        valor = campos.get(campo)
        if valor is None:
            datos[campo] = None
            continue
        try:
            if isinstance(valor, bool):
                raise InvalidOperation
            numero = Decimal(str(valor))
            if not numero.is_finite():
                raise InvalidOperation
            minimo = Decimal("0") if campo == "porcentaje_graso" else Decimal("0.01")
            maximo = Decimal("100") if campo == "porcentaje_graso" else Decimal("999.99")
            if not minimo <= numero <= maximo:
                raise InvalidOperation
            redondeado = numero.quantize(Decimal("0.01"))
            if redondeado != numero:
                raise InvalidOperation
        except (InvalidOperation, ValueError, TypeError):
            rango = "entre 0 y 100" if campo == "porcentaje_graso" else "mayor que 0 y hasta 999,99"
            raise ValidacionError(f"El valor de {ETIQUETAS[campo]} debe ser {rango}, con hasta dos decimales.") from None
        datos[campo] = redondeado
    if all(datos[campo] is None for campo in MEDIDAS):
        raise ValidacionError("Introduce al menos una medida. Deja vacíos los valores que no conozcas.")
    return datos


def crear_registro(engine, campos):
    datos = validar(campos)
    try:
        with engine.begin() as conexion:
            # Bloquea la ficha mientras se valida/inserta. Dos guardados de esta
            # aplicación para el mismo deportista se serializan en PostgreSQL.
            deportista = conexion.execute(text("""
                SELECT dni, fecha_nacimiento FROM public.deportista
                WHERE dni=:dni_deportista FOR UPDATE
            """).columns(fecha_nacimiento=Date()), datos).mappings().first()
            if deportista is None:
                raise ValidacionError("El deportista ya no existe. Actualiza la búsqueda.")
            nacimiento = deportista["fecha_nacimiento"]
            if nacimiento is not None and datos["fecha"] < nacimiento:
                raise ValidacionError("La medición no puede ser anterior al nacimiento del deportista.")
            condiciones = " AND ".join(
                f"{campo} IS NOT DISTINCT FROM :{campo}" for campo in MEDIDAS
            )
            duplicado = conexion.execute(text("""
                SELECT id_registro FROM public.registro_antropometrico
                WHERE dni_deportista=:dni_deportista AND fecha=:fecha
                  AND """ + condiciones), datos).first()
            if duplicado:
                raise ConflictoError("Ya existe una medición con la misma fecha y los mismos valores. No se ha duplicado.")
            identificador = conexion.execute(text("""
                INSERT INTO public.registro_antropometrico
                    (fecha, altura, peso, envergadura, porcentaje_graso, dni_deportista)
                VALUES (:fecha, :altura, :peso, :envergadura, :porcentaje_graso, :dni_deportista)
                RETURNING id_registro
            """), datos).scalar_one()
    except IntegrityError:
        raise ConflictoError("No se pudo guardar la medición porque los datos relacionados han cambiado. Actualiza la búsqueda.") from None
    return identificador


def guardar_en_proveedor(proveedor, campos):
    from database.database import crear_engine
    motor = crear_engine(proveedor)
    try:
        return crear_registro(motor, campos)
    finally:
        motor.dispose()


def historiales_para_comparar(engine, documentos, fecha_referencia):
    """Una lectura cronológica de hasta tres deportistas hasta la fecha indicada."""
    if not isinstance(documentos, (list, tuple)) or not 1 <= len(documentos) <= 3:
        raise ValidacionError('Selecciona entre uno y tres deportistas para consultar su evolución.')
    if type(fecha_referencia) is not date:
        raise ValidacionError('Indica una fecha de consulta válida.')
    distintos = []
    for dni in documentos:
        if not isinstance(dni, str) or not dni.strip() or len(dni.strip()) > 20:
            raise ValidacionError('Selecciona documentos válidos para consultar la evolución.')
        if dni.strip() not in distintos:
            distintos.append(dni.strip())
    consulta = text('''
        SELECT id_registro, dni_deportista, fecha, altura, peso, envergadura, porcentaje_graso
        FROM public.registro_antropometrico
        WHERE dni_deportista IN :documentos AND fecha<=:fecha
        ORDER BY fecha, id_registro
    ''').bindparams(bindparam('documentos', expanding=True)).columns(
        fecha=Date(), **{campo: Numeric(5, 2) for campo in MEDIDAS})
    salida = {dni: [] for dni in distintos}
    with engine.connect() as conexion:
        for fila in conexion.execute(consulta, {'documentos': distintos, 'fecha': fecha_referencia}).mappings():
            salida[fila['dni_deportista']].append(dict(fila))
    return salida
