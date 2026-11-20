"""Exploración descriptiva del historial; no estima talento ni éxito futuro."""
from datetime import date
from sqlalchemy import Date, text
from database import queries


def listar_regatistas(engine, busqueda='', id_club=None, fecha=None, *,
                     clase=None, nacimiento='Todos', anio_min=None, anio_max=None,
                     nivel=None, limite=501):
    fecha = queries._fecha(fecha)
    parametros = dict(busqueda=queries._patron(busqueda), fecha=fecha,
                      **queries._paginacion(limite,0))
    condiciones = ["""(LOWER(d.nombre || ' ' || d.apellidos) LIKE LOWER(:busqueda) ESCAPE '!'
        OR LOWER(COALESCE(c.nombre,'')) LIKE LOWER(:busqueda) ESCAPE '!')"""]
    if id_club is not None:
        if type(id_club) is not int or id_club <= 0:
            raise ValueError('Selecciona un club válido.')
        condiciones.append('d.id_club=:club'); parametros['club']=id_club
    if clase:
        condiciones.append("""EXISTS (SELECT 1 FROM public.forma_parte fpc
            JOIN public.unidad_competitiva uc ON uc.id_unidad=fpc.id_unidad
            JOIN public.clase cc ON cc.id_clase=uc.id_clase
            WHERE fpc.dni_deportista=d.dni AND cc.nombre=:clase
              AND uc.fecha_inicio<=:fecha AND (uc.fecha_fin IS NULL OR uc.fecha_fin>=:fecha))""")
        parametros['clase']=clase
    if nacimiento not in ('Todos','Pendiente','Conocido'):
        raise ValueError('Selecciona un filtro de nacimiento válido.')
    if nacimiento!='Todos':
        condiciones.append('d.fecha_nacimiento IS '+('NULL' if nacimiento=='Pendiente' else 'NOT NULL'))
    for anio in (anio_min,anio_max):
        if anio is not None and (type(anio) is not int or not 1900<=anio<=fecha.year):
            raise ValueError('Indica años de nacimiento válidos para la fecha consultada.')
    if anio_min is not None and anio_max is not None and anio_min>anio_max:
        raise ValueError('El año mínimo no puede superar al máximo.')
    if anio_min is not None:
        condiciones.append('d.fecha_nacimiento>=:desde');parametros['desde']=date(anio_min,1,1)
    if anio_max is not None:
        condiciones.append('d.fecha_nacimiento<=:hasta');parametros['hasta']=date(anio_max,12,31)
    if nivel:
        if nivel not in ('Autonomico','Nacional','Internacional'):
            raise ValueError('Selecciona un nivel válido.')
        condiciones.append('EXISTS (SELECT 1 FROM resultados rn WHERE rn.dni_deportista=d.dni AND rn.nivel=:nivel)')
        parametros['nivel']=nivel
    sql = """
        WITH resultados AS (
            SELECT fp.dni_deportista, co.id_competicion, co.nivel, co.fecha_inicio,
                   MIN(p.posicion_general) AS puesto
            FROM public.forma_parte fp
            JOIN public.participa_en p ON p.id_unidad=fp.id_unidad
            JOIN public.competicion co ON co.id_competicion=p.id_competicion
            WHERE co.fecha_inicio<=:fecha
            GROUP BY fp.dni_deportista, co.id_competicion, co.nivel, co.fecha_inicio
        ), resumen AS (
            SELECT dni_deportista, COUNT(*) AS participaciones,
                SUM(CASE WHEN nivel='Nacional' THEN 1 ELSE 0 END) AS nacionales,
                SUM(CASE WHEN nivel='Internacional' THEN 1 ELSE 0 END) AS internacionales,
                MIN(CASE WHEN nivel='Nacional' THEN puesto END) AS mejor_nacional,
                MIN(CASE WHEN nivel='Internacional' THEN puesto END) AS mejor_internacional,
                MAX(fecha_inicio) AS ultima_regata
            FROM resultados GROUP BY dni_deportista
        ), clases AS (
            SELECT fp.dni_deportista,
                STRING_AGG(DISTINCT cl.nombre, ', ' ORDER BY cl.nombre) AS clases_activas
            FROM public.forma_parte fp
            JOIN public.unidad_competitiva u ON u.id_unidad=fp.id_unidad
            JOIN public.clase cl ON cl.id_clase=u.id_clase
            WHERE u.fecha_inicio<=:fecha AND (u.fecha_fin IS NULL OR u.fecha_fin>=:fecha)
            GROUP BY fp.dni_deportista
        )
        SELECT d.dni,d.nombre,d.apellidos,d.fecha_nacimiento,d.sexo,d.id_club,
            c.nombre AS club,c.id_federacion,f.nombre AS federacion,cl.clases_activas,
            COALESCE(r.participaciones,0) AS participaciones,
            COALESCE(r.nacionales,0) AS nacionales,COALESCE(r.internacionales,0) AS internacionales,
            r.mejor_nacional,r.mejor_internacional,r.ultima_regata
        FROM public.deportista d
        LEFT JOIN public.club c ON c.id_club=d.id_club
        LEFT JOIN public.federacion_autonomica f ON f.id_federacion=c.id_federacion
        LEFT JOIN resumen r ON r.dni_deportista=d.dni
        LEFT JOIN clases cl ON cl.dni_deportista=d.dni
        WHERE """+' AND '.join(condiciones)+"""
        ORDER BY d.apellidos,d.nombre,d.dni LIMIT :limite OFFSET :desplazamiento
    """
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(sql).columns(
            fecha_nacimiento=Date(),ultima_regata=Date()),parametros).mappings()]


def resumen_deportivo(resultados, fecha):
    """Una competición por clase y temporada, separando niveles y sin sumar puntos."""
    eventos={}
    for r in resultados:
        if r['fecha_inicio']>fecha:
            continue
        clave=(r.get('id_competicion') or (r['competicion'],r['fecha_inicio'],r['clase']))
        anterior=eventos.get(clave)
        if anterior is None or (r.get('posicion_general') is not None and
                (anterior.get('posicion_general') is None or r['posicion_general']<anterior['posicion_general'])):
            eventos[clave]=r
    grupos={}
    for r in eventos.values():
        clave=(r['fecha_inicio'].year,r['clase'],r.get('nivel') or 'Sin nivel')
        g=grupos.setdefault(clave,dict(temporada=clave[0],clase=clave[1],nivel=clave[2],
            regatas=0,mejor_puesto=None,podios=0,ultima_regata=r['fecha_inicio']))
        g['regatas']+=1
        puesto=r.get('posicion_general')
        if puesto is not None:
            g['mejor_puesto']=puesto if g['mejor_puesto'] is None else min(g['mejor_puesto'],puesto)
            g['podios']+=puesto<=3
        g['ultima_regata']=max(g['ultima_regata'],r['fecha_inicio'])
    return sorted(grupos.values(),key=lambda g:(-g['temporada'],g['clase'],g['nivel']))
