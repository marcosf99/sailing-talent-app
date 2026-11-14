"""Historiales para análisis, con cuatro lecturas sin multiplicar relaciones."""
from datetime import date

from sqlalchemy import Date, text


def cargar_datos(engine, fecha):
    if type(fecha) is not date:
        raise ValueError('Indica una fecha de consulta válida.')
    consultas = {
        'unidades': '''
            SELECT d.dni, d.nombre, d.apellidos, d.sexo, d.fecha_nacimiento,
                   c.id_club, c.nombre AS club, f.id_federacion,
                   f.nombre AS federacion, u.id_unidad, u.id_clase,
                   cl.nombre AS clase, u.fecha_inicio, u.fecha_fin, fp.rol
            FROM public.deportista d
            JOIN public.forma_parte fp ON fp.dni_deportista=d.dni
            JOIN public.unidad_competitiva u ON u.id_unidad=fp.id_unidad
            JOIN public.clase cl ON cl.id_clase=u.id_clase
            LEFT JOIN public.club c ON c.id_club=d.id_club
            LEFT JOIN public.federacion_autonomica f ON f.id_federacion=c.id_federacion
            WHERE u.fecha_inicio<=:fecha
            ORDER BY d.dni, u.fecha_inicio, u.id_unidad
        ''',
        'resultados': '''
            SELECT fp.dni_deportista AS dni, u.id_unidad, co.id_competicion,
                   co.nombre AS competicion, co.fecha_inicio, co.fecha_fin,
                   co.nivel, co.localidad, co.id_clase, cl.nombre AS clase,
                   p.posicion_general, p.posicion_categoria, p.puntos
            FROM public.forma_parte fp
            JOIN public.unidad_competitiva u ON u.id_unidad=fp.id_unidad
            JOIN public.participa_en p ON p.id_unidad=u.id_unidad
            JOIN public.competicion co ON co.id_competicion=p.id_competicion
            JOIN public.clase cl ON cl.id_clase=co.id_clase
            WHERE co.fecha_fin<=:fecha AND u.fecha_inicio<=co.fecha_inicio
              AND (u.fecha_fin IS NULL OR u.fecha_fin>=co.fecha_fin)
              AND co.id_clase=u.id_clase
            ORDER BY fp.dni_deportista, co.fecha_inicio, co.id_competicion, u.id_unidad
        ''',
        'mediciones': '''
            SELECT r.id_registro, r.dni_deportista AS dni, r.fecha,
                   r.altura, r.peso, r.envergadura, r.porcentaje_graso
            FROM public.registro_antropometrico r WHERE r.fecha<=:fecha
            ORDER BY r.fecha, r.id_registro
        ''',
        'informes': '''
            SELECT i.id_informe, i.dni_deportista AS dni, i.fecha,
                   i.estrategia, i.tactica, i.trimado, i.tecnica,
                   i.fortalezas, i.debilidades, i.recomendaciones,
                   t.nombre AS nombre_tecnico, t.apellidos AS apellidos_tecnico
            FROM public.informe i JOIN public.tecnico t ON t.dni=i.dni_tecnico
            WHERE i.fecha<=:fecha ORDER BY i.fecha, i.id_informe
        ''',
    }
    salida = {}
    with engine.connect() as c:
        for tipo, sql in consultas.items():
            fechas = ({'fecha_inicio': Date(), 'fecha_fin': Date(),
                       **({'fecha_nacimiento': Date()} if tipo == 'unidades' else {})}
                      if tipo in ('unidades', 'resultados') else {'fecha': Date()})
            salida[tipo] = [dict(r) for r in c.execute(
                text(sql).columns(**fechas), {'fecha': fecha}).mappings()]
    return salida
