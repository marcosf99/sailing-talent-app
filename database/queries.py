"""Consultas de lectura para Sailing Talent (PostgreSQL y SQLAlchemy 2).

Basadas en sailing-talent.html y sql/create_tables.sql. Todas reciben un
Engine explícito: no cargan credenciales ni abren conexiones al importarse.
Devuelven listas de diccionarios; obtener_ficha_deportista devuelve dict o None.
Fechas y valores NUMERIC conservan los tipos date y Decimal del controlador.
No calculan puntuaciones de talento ni recomendaciones automáticas de clase.
"""

from datetime import date
from math import isfinite
from typing import Optional, Sequence

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Engine


__all__ = [
    "listar_federaciones", "listar_clubes", "listar_clases",
    "buscar_deportistas", "obtener_ficha_deportista",
    "consultar_historial_antropometrico", "consultar_resultados_deportista",
    "consultar_trayectoria_deportista", "buscar_candidatos",
    "comparar_deportistas",
]


def _leer(engine, sql, parametros=None):
    sentencia = text(sql) if isinstance(sql, str) else sql
    with engine.connect() as conexion:
        return [dict(fila) for fila in conexion.execute(
            sentencia, parametros or {}
        ).mappings()]


def _fecha(valor):
    if valor is None:
        return date.today()
    if type(valor) is not date:
        raise ValueError("fecha_referencia debe ser datetime.date o None.")
    return valor


def _paginacion(limite, desplazamiento):
    if type(limite) is not int or not 1 <= limite <= 10000:
        raise ValueError("limite debe ser un entero entre 1 y 10000.")
    if type(desplazamiento) is not int or desplazamiento < 0:
        raise ValueError("desplazamiento debe ser un entero no negativo.")
    return {"limite": limite, "desplazamiento": desplazamiento}


def _patron(valor):
    # Buscar texto literal: % y _ introducidos por el usuario no son comodines.
    valor = valor.strip().replace("!", "!!").replace("%", "!%").replace("_", "!_")
    return "%" + valor + "%"


# Una fila por deportista. Se agregan por separado las mediciones, clases y
# participaciones para evitar multiplicar los resultados al combinar historiales.
_PERFILES = """
WITH mediciones AS (
    SELECT r.*, ROW_NUMBER() OVER (
        PARTITION BY r.dni_deportista
        ORDER BY r.fecha DESC, r.id_registro DESC
    ) AS orden
    FROM public.registro_antropometrico r
    WHERE r.fecha <= :fecha_referencia
), clases_activas AS (
    SELECT fp.dni_deportista,
           STRING_AGG(DISTINCT cl.nombre, ', ' ORDER BY cl.nombre) AS clases_activas
    FROM public.forma_parte fp
    JOIN public.unidad_competitiva u ON u.id_unidad = fp.id_unidad
    JOIN public.clase cl ON cl.id_clase = u.id_clase
    WHERE u.fecha_inicio <= :fecha_referencia
      AND (u.fecha_fin IS NULL OR u.fecha_fin >= :fecha_referencia)
    GROUP BY fp.dni_deportista
), resultados AS (
    SELECT fp.dni_deportista, COUNT(*) AS participaciones,
           MIN(p.posicion_general) AS mejor_puesto
    FROM public.forma_parte fp
    JOIN public.participa_en p ON p.id_unidad = fp.id_unidad
    JOIN public.competicion co ON co.id_competicion = p.id_competicion
    WHERE co.fecha_inicio <= :fecha_referencia
    GROUP BY fp.dni_deportista
), perfiles AS (
    SELECT d.dni, d.nombre, d.apellidos, d.fecha_nacimiento, d.sexo,
           CAST(EXTRACT(YEAR FROM AGE(CAST(:fecha_referencia AS DATE), d.fecha_nacimiento)) AS INTEGER) AS edad,
           d.id_club, c.nombre AS club, f.id_federacion,
           f.nombre AS federacion, ca.clases_activas,
           m.id_registro, m.fecha AS fecha_medicion, m.altura, m.peso,
           m.envergadura, m.porcentaje_graso,
           COALESCE(r.participaciones, 0) AS participaciones, r.mejor_puesto
    FROM public.deportista d
    LEFT JOIN public.club c ON c.id_club = d.id_club
    LEFT JOIN public.federacion_autonomica f ON f.id_federacion = c.id_federacion
    LEFT JOIN mediciones m ON m.dni_deportista = d.dni AND m.orden = 1
    LEFT JOIN clases_activas ca ON ca.dni_deportista = d.dni
    LEFT JOIN resultados r ON r.dni_deportista = d.dni
)
"""


def listar_federaciones(engine: Engine):
    """1. Catálogo completo de federaciones, ordenado por nombre."""
    return _leer(engine, """
        SELECT id_federacion, nombre, comunidad_autonoma, director_tecnico,
               direccion, telefono, correo_electronico
        FROM public.federacion_autonomica ORDER BY nombre, id_federacion
    """)


def listar_clubes(engine: Engine, id_federacion: Optional[int] = None):
    """2. Clubes con su federación; permite filtrar por id_federacion."""
    sql = """
        SELECT c.id_club, c.nombre, c.director_deportivo, c.telefono,
               c.localidad, c.provincia, c.id_federacion,
               f.nombre AS federacion, f.comunidad_autonoma
        FROM public.club c
        JOIN public.federacion_autonomica f ON f.id_federacion = c.id_federacion
    """
    parametros = {}
    if id_federacion is not None:
        sql += " WHERE c.id_federacion = :id_federacion"
        parametros["id_federacion"] = id_federacion
    return _leer(engine, sql + " ORDER BY f.nombre, c.nombre, c.id_club", parametros)


def listar_clases(engine: Engine, es_olimpica: Optional[bool] = None):
    """3. Clases, tripulación y condición olímpica; filtro booleano opcional."""
    sql = "SELECT id_clase, nombre, numero_tripulantes, es_olimpica FROM public.clase"
    parametros = {}
    if es_olimpica is not None:
        if type(es_olimpica) is not bool:
            raise ValueError("es_olimpica debe ser True, False o None.")
        sql += " WHERE es_olimpica = :es_olimpica"
        parametros["es_olimpica"] = es_olimpica
    return _leer(engine, sql + " ORDER BY nombre, id_clase", parametros)


def buscar_deportistas(engine: Engine, busqueda: str = "", *,
                       id_club: Optional[int] = None, limite: int = 100,
                       desplazamiento: int = 0):
    """4. Búsqueda por nombre completo o club, conservando deportistas sin club.

    La búsqueda ignora mayúsculas; no elimina tildes. Devuelve una página.
    """
    parametros = _paginacion(limite, desplazamiento)
    condiciones = ["""(LOWER(d.nombre || ' ' || d.apellidos) LIKE LOWER(:busqueda) ESCAPE '!'
        OR LOWER(COALESCE(c.nombre, '')) LIKE LOWER(:busqueda) ESCAPE '!')"""]
    parametros["busqueda"] = _patron(busqueda)
    if id_club is not None:
        condiciones.append("d.id_club = :id_club")
        parametros["id_club"] = id_club
    return _leer(engine, """
        SELECT d.dni, d.nombre, d.apellidos, d.fecha_nacimiento, d.sexo,
               d.id_club, c.nombre AS club
        FROM public.deportista d
        LEFT JOIN public.club c ON c.id_club = d.id_club
        WHERE """ + " AND ".join(condiciones) + """
        ORDER BY d.apellidos, d.nombre, d.dni
        LIMIT :limite OFFSET :desplazamiento
    """, parametros)


def obtener_ficha_deportista(engine: Engine, dni: str, *, fecha_referencia=None):
    """5. Ficha, edad, última medición, clases activas y resumen deportivo.

    Devuelve None si el DNI no existe. Sin mediciones, sus valores son None;
    sin resultados, participaciones es 0 y mejor_puesto es None.
    """
    filas = _leer(engine, _PERFILES + "SELECT * FROM perfiles WHERE dni = :dni",
                  {"dni": dni, "fecha_referencia": _fecha(fecha_referencia)})
    return filas[0] if filas else None


def consultar_historial_antropometrico(engine: Engine, dni: str):
    """6. Todas las mediciones, en orden cronológico para representar evolución."""
    return _leer(engine, """
        SELECT id_registro, dni_deportista, fecha, altura, peso,
               envergadura, porcentaje_graso
        FROM public.registro_antropometrico
        WHERE dni_deportista = :dni
        ORDER BY fecha, id_registro
    """, {"dni": dni})


def consultar_resultados_deportista(engine: Engine, dni: str, *,
                                   id_clase: Optional[int] = None,
                                   fecha_referencia=None):
    """7. Resultados de sus unidades, del más reciente al más antiguo.

    Una fila por unidad y competición, hasta la fecha de referencia. El esquema
    no fecha la pertenencia de cada miembro: se atribuyen los resultados de
    todas las unidades a las que pertenece, como en el prototipo.
    """
    sql = """
        SELECT co.id_competicion, co.nombre AS competicion, co.fecha_inicio,
               co.fecha_fin, co.localidad, co.nivel,
               cl.id_clase, cl.nombre AS clase, u.id_unidad, fp.rol,
               p.posicion_general, p.posicion_categoria, p.puntos
        FROM public.forma_parte fp
        JOIN public.unidad_competitiva u ON u.id_unidad = fp.id_unidad
        JOIN public.participa_en p ON p.id_unidad = u.id_unidad
        JOIN public.competicion co ON co.id_competicion = p.id_competicion
        JOIN public.clase cl ON cl.id_clase = co.id_clase
        WHERE fp.dni_deportista = :dni AND co.fecha_inicio <= :fecha_referencia
    """
    parametros = {"dni": dni, "fecha_referencia": _fecha(fecha_referencia)}
    if id_clase is not None:
        sql += " AND co.id_clase = :id_clase"
        parametros["id_clase"] = id_clase
    return _leer(engine, sql + """
        ORDER BY co.fecha_inicio DESC, co.id_competicion DESC, u.id_unidad
    """, parametros)


def consultar_trayectoria_deportista(engine: Engine, dni: str, *, fecha_referencia=None):
    """8. Clases y unidades históricas con todos los miembros del equipo.

    Una fila por miembro (incluido el deportista consultado). Agrupar por
    id_unidad para presentar equipos. Los intervalos de actividad son inclusivos.
    """
    return _leer(engine, """
        SELECT u.id_unidad, cl.id_clase, cl.nombre AS clase,
               u.fecha_inicio, u.fecha_fin,
               (u.fecha_inicio <= :fecha_referencia AND
                (u.fecha_fin IS NULL OR u.fecha_fin >= :fecha_referencia)) AS activa,
               miembro.dni AS dni_miembro, miembro.nombre AS nombre_miembro,
               miembro.apellidos AS apellidos_miembro, equipo.rol
        FROM public.forma_parte propia
        JOIN public.unidad_competitiva u ON u.id_unidad = propia.id_unidad
        JOIN public.clase cl ON cl.id_clase = u.id_clase
        JOIN public.forma_parte equipo ON equipo.id_unidad = u.id_unidad
        JOIN public.deportista miembro ON miembro.dni = equipo.dni_deportista
        WHERE propia.dni_deportista = :dni
        ORDER BY u.fecha_inicio DESC, u.id_unidad, miembro.apellidos, miembro.dni
    """, {"dni": dni, "fecha_referencia": _fecha(fecha_referencia)})


def buscar_candidatos(engine: Engine, *, clase_actual: Optional[str] = None,
                      sexo: Optional[str] = None, edad_min: Optional[int] = None,
                      edad_max: Optional[int] = None, altura_min=None,
                      fecha_referencia=None, limite: int = 100,
                      desplazamiento: int = 0):
    """9. Filtros exploratorios del prototipo; sin puntuación ni clase destino.

    Se usa la última medición no futura (desempate por id_registro). Un valor
    desconocido no supera un filtro de edad/altura. Sin ese filtro se conserva.
    La clase actual debe corresponder a una unidad activa en fecha_referencia.
    """
    if sexo not in (None, "Femenino", "Masculino"):
        raise ValueError("sexo debe ser Femenino, Masculino o None.")
    for valor in (edad_min, edad_max):
        if valor is not None and (type(valor) is not int or valor < 0):
            raise ValueError("Las edades deben ser enteros no negativos.")
    if edad_min is not None and edad_max is not None and edad_min > edad_max:
        raise ValueError("edad_min no puede ser mayor que edad_max.")
    if altura_min is not None:
        try:
            valida = not isinstance(altura_min, (bool, str)) and isfinite(altura_min) and altura_min >= 0
        except (TypeError, ValueError, OverflowError):
            valida = False
        if not valida:
            raise ValueError("altura_min debe ser un número finito no negativo.")
    parametros = _paginacion(limite, desplazamiento)
    parametros["fecha_referencia"] = _fecha(fecha_referencia)
    condiciones = []
    # Solo estos fragmentos constantes se añaden al SQL; los valores se enlazan.
    for nombre, valor, expresion in (
        ("sexo", sexo, "p.sexo = :sexo"),
        ("edad_min", edad_min, "p.edad >= :edad_min"),
        ("edad_max", edad_max, "p.edad <= :edad_max"),
        ("altura_min", altura_min, "p.altura >= :altura_min"),
    ):
        if valor is not None:
            condiciones.append(expresion)
            parametros[nombre] = valor
    if clase_actual:
        condiciones.append("""EXISTS (
            SELECT 1 FROM public.forma_parte fp
            JOIN public.unidad_competitiva u ON u.id_unidad = fp.id_unidad
            JOIN public.clase cl ON cl.id_clase = u.id_clase
            WHERE fp.dni_deportista = p.dni AND cl.nombre = :clase_actual
              AND u.fecha_inicio <= :fecha_referencia
              AND (u.fecha_fin IS NULL OR u.fecha_fin >= :fecha_referencia)
        )""")
        parametros["clase_actual"] = clase_actual
    sql = _PERFILES + "SELECT p.* FROM perfiles p"
    if condiciones:
        sql += " WHERE " + " AND ".join(condiciones)
    return _leer(engine, sql + """
        ORDER BY p.apellidos, p.nombre, p.dni
        LIMIT :limite OFFSET :desplazamiento
    """, parametros)


def comparar_deportistas(engine: Engine, dnis: Sequence[str], *, fecha_referencia=None):
    """10. Perfiles comparables de hasta tres DNI distintos, en el orden recibido.

    Incluye edad, clases activas, última medición y participaciones. Los DNI
    inexistentes se omiten; una selección vacía devuelve []. No puntúa perfiles.
    """
    if isinstance(dnis, (str, bytes)):
        raise ValueError("dnis debe ser una lista o tupla de documentos.")
    documentos = list(dict.fromkeys(dnis))
    if any(not isinstance(dni, str) or not dni.strip() for dni in documentos):
        raise ValueError("Cada DNI debe ser un texto no vacío.")
    if len(documentos) > 3:
        raise ValueError("Solo se pueden comparar hasta tres deportistas.")
    if not documentos:
        return []
    sentencia = text(_PERFILES + "SELECT * FROM perfiles WHERE dni IN :dnis").bindparams(
        bindparam("dnis", expanding=True)
    )
    filas = _leer(engine, sentencia, {
        "dnis": documentos, "fecha_referencia": _fecha(fecha_referencia),
    })
    posiciones = {dni: i for i, dni in enumerate(documentos)}
    return sorted(filas, key=lambda fila: posiciones[fila["dni"]])


