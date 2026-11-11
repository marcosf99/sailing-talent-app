"""SQL parametrizado para importaciones. Recibe Connection; no abre transacciones.

Los nombres de tablas y columnas se restringen a constantes internas. Los servicios
son responsables de validar, bloquear la importación y confirmar o revertir cambios.
Importar este módulo no carga credenciales ni abre conexiones.
"""
from sqlalchemy import JSON, Boolean, Date, DateTime, Numeric, bindparam, text


_CAMPOS = {
    "importacion_clasificacion": (
        "tipo_fuente", "nombre_archivo", "url_origen", "referencia_documento",
        "huella_documento", "nombre_competicion_propuesto", "fecha_inicio_propuesta",
        "fecha_fin_propuesta", "localidad_propuesta", "nivel", "id_clase",
        "tipo_clasificacion", "fecha_actualizacion_fuente", "mapeo_columnas",
        "criterio_inclusion", "observaciones", "id_competicion",
    ),
    "fila_clasificacion_importada": (
        "id_importacion", "numero_fila", "pagina_origen", "datos_originales",
        "numero_vela_original", "codigo_pais_vela", "posicion_general", "puntos",
        "categoria_original", "posicion_categoria", "cumple_criterio",
        "motivo_seleccion", "estado", "incidencias", "observaciones_revision",
    ),
    "participante_importado": (
        "id_fila", "orden_en_tripulacion", "nombre_original", "nombre_propuesto",
        "apellidos_propuestos", "documento_propuesto", "fecha_nacimiento_propuesta",
        "sexo_propuesto", "club_original", "federacion_original",
        "id_club_identificado", "rol_propuesto", "estado", "observaciones_revision",
    ),
    "coincidencia_propuesta": (
        "id_participante_importado", "dni_deportista", "indice_similitud", "motivos",
    ),
    "alias_club": ("texto_alias", "texto_normalizado", "id_club", "contexto_fuente"),
}
_CLAVES = {
    "importacion_clasificacion": "id_importacion",
    "fila_clasificacion_importada": "id_fila",
    "participante_importado": "id_participante_importado",
    "coincidencia_propuesta": "dni_deportista",
    "alias_club": "id_alias",
}
CAMPOS_IMPORTACION = _CAMPOS["importacion_clasificacion"]
CAMPOS_FILA = _CAMPOS["fila_clasificacion_importada"]
_JSON = {"mapeo_columnas", "criterio_inclusion", "datos_originales"}


def insertar(conexion, tabla, datos):
    """Inserción interna con lista cerrada de columnas y RETURNING."""
    permitidos = _CAMPOS[tabla]
    if set(datos) - set(permitidos):
        raise ValueError("La inserción contiene columnas no admitidas.")
    campos = [c for c in permitidos if c in datos]
    sentencia = text(
        "INSERT INTO public." + tabla + " (" + ", ".join(campos) + ") VALUES ("
        + ", ".join(":" + c for c in campos) + ") RETURNING " + _CLAVES[tabla]
    )
    for campo in _JSON.intersection(campos):
        sentencia = sentencia.bindparams(bindparam(campo, type_=JSON(none_as_null=True)))
    for campo in ('puntos', 'indice_similitud'):
        if campo in campos:
            sentencia = sentencia.bindparams(bindparam(campo, type_=Numeric()))
    for campo in ('fecha_inicio_propuesta', 'fecha_fin_propuesta', 'fecha_nacimiento_propuesta'):
        if campo in campos:
            sentencia = sentencia.bindparams(bindparam(campo, type_=Date()))
    if 'fecha_actualizacion_fuente' in campos:
        sentencia = sentencia.bindparams(bindparam('fecha_actualizacion_fuente', type_=DateTime(timezone=True)))
    return conexion.execute(sentencia, datos).scalar_one()


def obtener_importacion(conexion, identificador, bloquear=False):
    sql = """
        SELECT i.*, cl.nombre AS nombre_clase, cl.numero_tripulantes
        FROM public.importacion_clasificacion i
        JOIN public.clase cl ON cl.id_clase=i.id_clase
        WHERE i.id_importacion=:id
    """
    if bloquear:
        sql += " FOR UPDATE OF i"
    sentencia = text(sql).columns(
        mapeo_columnas=JSON(), criterio_inclusion=JSON(),
        fecha_inicio_propuesta=Date(), fecha_fin_propuesta=Date(),
        creado_en=DateTime(timezone=True), actualizado_en=DateTime(timezone=True),
        fecha_actualizacion_fuente=DateTime(timezone=True),
    )
    fila = conexion.execute(sentencia, {"id": identificador}).mappings().first()
    return dict(fila) if fila else None


def listar_importaciones(conexion, limite=50, desplazamiento=0):
    return [dict(r) for r in conexion.execute(text("""
        SELECT i.id_importacion, i.nombre_archivo, i.url_origen, i.estado, i.nivel,
               i.id_clase, cl.nombre AS nombre_clase, i.creado_en, i.actualizado_en,
               (SELECT COUNT(*) FROM public.fila_clasificacion_importada f
                WHERE f.id_importacion=i.id_importacion) AS total_filas
        FROM public.importacion_clasificacion i
        JOIN public.clase cl ON cl.id_clase=i.id_clase
        ORDER BY i.creado_en DESC, i.id_importacion DESC
        LIMIT :limite OFFSET :desplazamiento
    """).columns(creado_en=DateTime(timezone=True), actualizado_en=DateTime(timezone=True)),
        {"limite": limite, "desplazamiento": desplazamiento}).mappings()]


def listar_filas(conexion, identificador):
    return [dict(r) for r in conexion.execute(text("""
        SELECT * FROM public.fila_clasificacion_importada
        WHERE id_importacion=:id ORDER BY numero_fila, id_fila
    """).columns(datos_originales=JSON(), cumple_criterio=Boolean(), puntos=Numeric(10, 2)), {"id": identificador}).mappings()]


def listar_participantes(conexion, identificador):
    return [dict(r) for r in conexion.execute(text("""
        SELECT p.* FROM public.participante_importado p
        JOIN public.fila_clasificacion_importada f ON f.id_fila=p.id_fila
        WHERE f.id_importacion=:id
        ORDER BY f.numero_fila, p.orden_en_tripulacion
    """).columns(fecha_nacimiento_propuesta=Date(), confirmado_en=DateTime(timezone=True)),
        {"id": identificador}).mappings()]


def listar_coincidencias(conexion, identificador):
    return [dict(r) for r in conexion.execute(text("""
        SELECT c.* FROM public.coincidencia_propuesta c
        JOIN public.participante_importado p
          ON p.id_participante_importado=c.id_participante_importado
        JOIN public.fila_clasificacion_importada f ON f.id_fila=p.id_fila
        WHERE f.id_importacion=:id
        ORDER BY c.id_participante_importado, c.indice_similitud DESC NULLS LAST,
                 c.dni_deportista
    """), {"id": identificador}).mappings()]


def contexto_participante(conexion, identificador):
    r = conexion.execute(text("""
        SELECT p.*, f.id_importacion, f.cumple_criterio,
               f.estado AS estado_fila
        FROM public.participante_importado p
        JOIN public.fila_clasificacion_importada f ON f.id_fila=p.id_fila
        WHERE p.id_participante_importado=:id
    """), {"id": identificador}).mappings().first()
    return dict(r) if r else None


def referencia_clase(conexion, identificador):
    r = conexion.execute(text("""
        SELECT id_clase, numero_tripulantes FROM public.clase WHERE id_clase=:id
    """), {"id": identificador}).mappings().first()
    return dict(r) if r else None


def referencia_competicion(conexion, identificador):
    r = conexion.execute(text("""
        SELECT id_clase, nivel, fecha_inicio FROM public.competicion WHERE id_competicion=:id
    """).columns(fecha_inicio=Date()), {"id": identificador}).mappings().first()
    return dict(r) if r else None


def existe_deportista(conexion, dni):
    return conexion.execute(text("SELECT dni FROM public.deportista WHERE dni=:dni"),
                            {"dni": dni}).first() is not None


def existe_club(conexion, identificador):
    return conexion.execute(text("SELECT id_club FROM public.club WHERE id_club=:id"),
                            {"id": identificador}).first() is not None


def marcar_en_revision(conexion, identificador):
    conexion.execute(text("""
        UPDATE public.importacion_clasificacion
        SET estado=CASE WHEN estado='parcialmente_importada'
                       THEN estado ELSE 'en_revision' END
        WHERE id_importacion=:id
    """), {"id": identificador})


def confirmar_identidad(conexion, participante, dni):
    conexion.execute(text("""
        UPDATE public.participante_importado
        SET dni_deportista_confirmado=:dni, confirmado_en=CURRENT_TIMESTAMP,
            estado='vinculado' WHERE id_participante_importado=:id
    """), {"id": participante, "dni": dni})
    # Las propuestas no confirman por sí mismas: solo esta acción explícita lo hace.
    conexion.execute(text("""
        UPDATE public.coincidencia_propuesta
        SET estado_revision='rechazada', revisado_en=CURRENT_TIMESTAMP
        WHERE id_participante_importado=:id AND estado_revision='aceptada'
    """), {"id": participante})
    conexion.execute(text("""
        UPDATE public.coincidencia_propuesta
        SET estado_revision='aceptada', revisado_en=CURRENT_TIMESTAMP
        WHERE id_participante_importado=:id AND dni_deportista=:dni
    """), {"id": participante, "dni": dni})


def actualizar_importacion(conexion, identificador, campos):
    if set(campos) != set(CAMPOS_IMPORTACION):
        raise ValueError("Se requieren los campos completos de la importación.")
    sentencia = text("UPDATE public.importacion_clasificacion SET " + ", ".join(
        campo + '=:' + campo for campo in CAMPOS_IMPORTACION
    ) + " WHERE id_importacion=:id")
    for campo in _JSON.intersection(campos):
        sentencia = sentencia.bindparams(bindparam(campo, type_=JSON(none_as_null=True)))
    for campo in ('fecha_inicio_propuesta', 'fecha_fin_propuesta'):
        sentencia = sentencia.bindparams(bindparam(campo, type_=Date()))
    sentencia = sentencia.bindparams(bindparam('fecha_actualizacion_fuente', type_=DateTime(timezone=True)))
    conexion.execute(sentencia, dict(campos, id=identificador))


def fichas_revision(conexion):
    """Datos mínimos para cotejar nombres y contexto sin extensiones PostgreSQL."""
    return [dict(r) for r in conexion.execute(text("""
        SELECT d.dni, d.nombre, d.apellidos, d.fecha_nacimiento, d.sexo,
               d.id_club, c.nombre AS club, c.id_federacion,
               f.nombre AS federacion
        FROM public.deportista d
        LEFT JOIN public.club c ON c.id_club=d.id_club
        LEFT JOIN public.federacion_autonomica f ON f.id_federacion=c.id_federacion
        ORDER BY d.dni
    """).columns(fecha_nacimiento=Date())).mappings()]


def aliases_revision(conexion):
    # Los alias con contexto requieren elegir ese contexto expresamente; no se
    # aplican como si fueran abreviaturas universales de un club.
    return [dict(r) for r in conexion.execute(text("""
        SELECT texto_normalizado, id_club FROM public.alias_club
        WHERE contexto_fuente IS NULL OR BTRIM(contexto_fuente)=''
    """)).mappings()]


def ficha_por_documento(conexion, dni):
    r = conexion.execute(text("""
        SELECT dni, nombre, apellidos, fecha_nacimiento, sexo, id_club
        FROM public.deportista WHERE UPPER(dni)=:dni
    """).columns(fecha_nacimiento=Date()), {'dni': dni.upper()}).mappings().first()
    return dict(r) if r else None


def insertar_ficha_revision(conexion, campos):
    conexion.execute(text("""
        INSERT INTO public.deportista
          (dni,nombre,apellidos,fecha_nacimiento,sexo,id_club)
        VALUES (:dni,:nombre,:apellidos,:fecha_nacimiento,:sexo,:id_club)
    """).bindparams(bindparam('fecha_nacimiento', type_=Date())), campos)


def actualizar_revision(conexion, participante, campos, estado):
    # Campos cerrados: el texto de la fuente nunca se sobrescribe.
    permitidos = ('nombre_propuesto', 'apellidos_propuestos', 'documento_propuesto',
                  'fecha_nacimiento_propuesta', 'sexo_propuesto', 'id_club_identificado',
                  'rol_propuesto', 'observaciones_revision')
    if set(campos) != set(permitidos):
        raise ValueError('Campos de revisión incompletos o desconocidos.')
    sentencia = text('UPDATE public.participante_importado SET ' + ', '.join(
        c + '=:' + c for c in permitidos
    ) + ', estado=:estado WHERE id_participante_importado=:id').bindparams(
        bindparam('fecha_nacimiento_propuesta', type_=Date()))
    conexion.execute(sentencia, dict(campos, id=participante, estado=estado))


def guardar_sugerencia(conexion, participante, dni, indice, motivos):
    conexion.execute(text("""
        INSERT INTO public.coincidencia_propuesta
          (id_participante_importado,dni_deportista,indice_similitud,motivos)
        VALUES (:id,:dni,:indice,:motivos)
        ON CONFLICT (id_participante_importado,dni_deportista) DO UPDATE
        SET indice_similitud=excluded.indice_similitud, motivos=excluded.motivos
        WHERE coincidencia_propuesta.estado_revision='pendiente'
    """).bindparams(bindparam('indice', type_=Numeric())),
        {'id': participante, 'dni': dni, 'indice': indice, 'motivos': motivos})


def fila_revision(conexion, identificador):
    r = conexion.execute(text('SELECT * FROM public.fila_clasificacion_importada WHERE id_fila=:id'),
                         {'id': identificador}).mappings().first()
    return dict(r) if r else None


def miembros_revision(conexion, identificador):
    return [dict(r) for r in conexion.execute(text("""
        SELECT * FROM public.participante_importado WHERE id_fila=:id
        ORDER BY orden_en_tripulacion
    """), {'id': identificador}).mappings()]


def estado_fila_revision(conexion, identificador, estado, incidencias):
    conexion.execute(text("""
        UPDATE public.fila_clasificacion_importada
        SET estado=:estado,incidencias=:incidencias WHERE id_fila=:id
    """), {'id': identificador, 'estado': estado, 'incidencias': incidencias})


def rechazar_otras_sugerencias(conexion, participante, dni_confirmado):
    conexion.execute(text("""
        UPDATE public.coincidencia_propuesta
        SET estado_revision='rechazada', revisado_en=CURRENT_TIMESTAMP
        WHERE id_participante_importado=:id AND dni_deportista<>:dni
    """), {'id': participante, 'dni': dni_confirmado})
