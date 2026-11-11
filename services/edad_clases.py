"""Criterio de edad de la aplicación: Optimist hasta el año en que cumple 14."""
from datetime import date
from sqlalchemy import Date, text
from services.deportistas import ValidacionError


def limite_edad(clase, nacimiento):
    if clase.strip().casefold() == 'optimist' and nacimiento is not None:
        return date(nacimiento.year + 14, 12, 31)
    return None


def validar_edad(clase, personas, inicio, fin=None):
    limites = [limite_edad(clase, p['fecha_nacimiento']) for p in personas]
    conocidos = [f for f in limites if f is not None]
    limite = min(conocidos) if conocidos else None
    if limite and (inicio > limite or (fin is not None and fin > limite)):
        raise ValidacionError('La edad no es compatible con Optimist: solo se admite hasta el 31 de diciembre del año en que cumple 14. Revisa la clase, el nacimiento o las fechas.')
    return limite


def fin_vencido(limite, hoy=None):
    hoy = hoy or date.today()
    return limite if limite is not None and limite < hoy else None


def _pendientes(conexion, hoy):
    filas = conexion.execute(text('''
        SELECT u.id_unidad, u.fecha_inicio, d.dni, d.fecha_nacimiento
        FROM public.unidad_competitiva u JOIN public.clase c ON c.id_clase=u.id_clase
        LEFT JOIN public.forma_parte fp ON fp.id_unidad=u.id_unidad
        LEFT JOIN public.deportista d ON d.dni=fp.dni_deportista
        WHERE u.fecha_fin IS NULL AND LOWER(TRIM(c.nombre))='optimist'
        ORDER BY u.id_unidad
    ''').columns(fecha_inicio=Date(), fecha_nacimiento=Date())).mappings().all()
    grupos = {}
    for f in filas:
        grupos.setdefault(f['id_unidad'], []).append(f)
    salida = []
    for miembros in grupos.values():
        # No inferir el cierre de una unidad individual con composición anómala.
        if len(miembros) == 1:
            f = miembros[0]
            limite = limite_edad('Optimist', f['fecha_nacimiento'])
            if fin_vencido(limite, hoy):
                salida.append(dict(f, limite=limite))
    return salida


def pendientes_por_edad(engine, hoy=None):
    with engine.connect() as conexion:
        return _pendientes(conexion, hoy or date.today())


def cerrar_vencidas(engine, hoy=None):
    """Cierra solo límites pasados; conserva historia incompatible para revisión."""
    hoy = hoy or date.today()
    cerradas, incidencias = [], []
    with engine.begin() as conexion:
        conexion.execute(text("SELECT id_clase FROM public.clase WHERE LOWER(TRIM(nombre))='optimist' ORDER BY id_clase FOR UPDATE"))
        for candidata in _pendientes(conexion, hoy):
            persona = conexion.execute(text('SELECT fecha_nacimiento FROM public.deportista WHERE dni=:dni FOR UPDATE')
                                       .columns(fecha_nacimiento=Date()), {'dni': candidata['dni']}).mappings().first()
            limite = limite_edad('Optimist', persona['fecha_nacimiento']) if persona else None
            if not fin_vencido(limite, hoy):
                continue
            unidad = conexion.execute(text('SELECT fecha_inicio, fecha_fin FROM public.unidad_competitiva WHERE id_unidad=:id FOR UPDATE')
                                      .columns(fecha_inicio=Date(), fecha_fin=Date()), {'id': candidata['id_unidad']}).mappings().first()
            if unidad is None or unidad['fecha_fin'] is not None:
                continue
            ultima = conexion.execute(text('''SELECT MAX(c.fecha_fin) AS ultima
                FROM public.participa_en p JOIN public.competicion c ON c.id_competicion=p.id_competicion
                WHERE p.id_unidad=:id''').columns(ultima=Date()), {'id': candidata['id_unidad']}).scalar_one()
            if unidad['fecha_inicio'] > limite or (ultima and ultima > limite):
                incidencias.append(f'Unidad {candidata["id_unidad"]}: fechas o resultados posteriores al límite de Optimist. Requiere revisión antes del cierre por edad.')
                continue
            conexion.execute(text('UPDATE public.unidad_competitiva SET fecha_fin=:fin WHERE id_unidad=:id'),
                             {'fin': limite, 'id': candidata['id_unidad']})
            cerradas.append(candidata['id_unidad'])
    return dict(cerradas=cerradas, incidencias=incidencias)


def cerrar_en_proveedor(proveedor):
    from database.database import crear_engine
    motor = crear_engine(proveedor)
    try:
        return cerrar_vencidas(motor)
    finally:
        motor.dispose()
