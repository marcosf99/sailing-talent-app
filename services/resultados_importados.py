"""Incorporación explícita y atómica de resultados con identidades revisadas."""
from datetime import date
import hashlib
import json

from sqlalchemy import Date, Numeric, bindparam, text
from sqlalchemy.exc import IntegrityError

from database import importaciones as datos
from services import importaciones as base
from services.revision_participantes import version_participante
from services.deportistas import ValidacionError, ConflictoError
from services.edad_clases import validar_edad, fin_vencido


def version_resultados(revision):
    """Incluye metadatos, posiciones, puntos e identidades vistos por el usuario."""
    imp = revision['importacion']
    metadatos = {k: imp.get(k) for k in (
        'id_importacion', 'estado', 'actualizado_en', 'id_competicion', 'id_clase',
        'numero_tripulantes', 'nivel', 'tipo_clasificacion', 'nombre_competicion_propuesto',
        'fecha_inicio_propuesta', 'fecha_fin_propuesta', 'localidad_propuesta')}
    filas = [{k: f.get(k) for k in ('id_fila', 'estado', 'cumple_criterio', 'posicion_general',
                                   'posicion_categoria', 'puntos', 'id_unidad_confirmada',
                                   'id_competicion_confirmada')} for f in revision['filas']]
    personas = [(p['id_fila'], p['orden_en_tripulacion'], version_participante(p))
                for p in revision['participantes']]
    contenido = json.dumps([metadatos, filas, personas], sort_keys=True, default=str)
    return hashlib.sha256(contenido.encode()).hexdigest()


def miembros_fila(revision, fila):
    return [p for p in revision['participantes'] if p['id_fila'] == fila['id_fila']]


def incidencias(revision, fila):
    """No basta el estado cacheado: comprobar de nuevo datos y tripulación."""
    n = revision['importacion']['numero_tripulantes']
    miembros = miembros_fila(revision, fila)
    errores = []
    if fila['cumple_criterio'] is not True or fila['estado'] == 'excluida':
        errores.append('Fuera del criterio de selección.')
    if fila['posicion_general'] is None or fila['puntos'] is None:
        errores.append('Falta puesto o puntuación.')
    documentos = [p['dni_deportista_confirmado'] for p in miembros]
    if (n not in (1, 2) or len(miembros) != n or not all(documentos)
            or len(set(documentos)) != n
            or any(p['estado'] not in ('vinculado', 'nuevo_confirmado') for p in miembros)):
        errores.append('Faltan identidades confirmadas o hay miembros incorrectos.')
    if n == 2 and sorted(p['rol_propuesto'] or '' for p in miembros) != ['Patron', 'Tripulante']:
        errores.append('Confirma un patrón y un tripulante.')
    return errores


def filas_preparadas(revision):
    return [f for f in revision['filas'] if f['estado'] != 'importada' and not incidencias(revision, f)]


def _metadatos(campos):
    permitidos = {'nombre', 'fecha_inicio', 'fecha_fin', 'localidad', 'tipo_clasificacion'}
    if not isinstance(campos, dict) or set(campos) - permitidos:
        raise ValidacionError('Los datos de competición contienen campos no admitidos.')
    salida = dict(nombre=base._texto(campos.get('nombre'), 'nombre de la competición', 200, True),
                  localidad=base._texto(campos.get('localidad'), 'localidad', 100))
    for campo in ('fecha_inicio', 'fecha_fin'):
        valor = campos.get(campo)
        if type(valor) is not date or valor > date.today():
            raise ValidacionError('Confirma las fechas de la regata, que no pueden ser futuras.')
        salida[campo] = valor
    if salida['fecha_fin'] < salida['fecha_inicio']:
        raise ValidacionError('La fecha final no puede ser anterior al inicio.')
    salida['tipo_clasificacion'] = campos.get('tipo_clasificacion')
    if salida['tipo_clasificacion'] not in ('provisional', 'definitiva'):
        raise ValidacionError('Confirma si la clasificación es provisional o definitiva.')
    return salida


def _competicion(conexion, imp, campos):
    # La clase serializa importaciones del mismo evento, incluso antes de que
    # exista una fila de competición que bloquear. El DDL no tiene clave natural.
    clase = conexion.execute(text('SELECT id_clase FROM public.clase WHERE id_clase=:id FOR UPDATE'),
                             {'id': imp['id_clase']}).first()
    if clase is None:
        raise ConflictoError('La clase ya no existe.')
    if imp['id_competicion']:
        existentes = conexion.execute(text('SELECT * FROM public.competicion WHERE id_competicion=:id FOR UPDATE')
                                     .columns(fecha_inicio=Date(), fecha_fin=Date()),
                                     {'id': imp['id_competicion']}).mappings().all()
    else:
        existentes = conexion.execute(text('''
            SELECT * FROM public.competicion
            WHERE LOWER(BTRIM(nombre))=LOWER(BTRIM(:nombre)) AND id_clase=:clase
              AND fecha_inicio=:fecha_inicio AND fecha_fin=:fecha_fin
            ORDER BY id_competicion FOR UPDATE
        ''').columns(fecha_inicio=Date(), fecha_fin=Date()),
            {**campos, 'clase': imp['id_clase']}).mappings().all()
    if len(existentes) > 1:
        raise ConflictoError('Hay varias competiciones con ese nombre, clase y fechas. Revisa los duplicados antes de incorporar.')
    if existentes:
        co = existentes[0]
        if (co['id_clase'] != imp['id_clase'] or co['nivel'] != imp['nivel']
                or any(co[k] != campos[k] for k in ('fecha_inicio', 'fecha_fin', 'localidad'))
                or co['nombre'].strip().casefold() != campos['nombre'].casefold()):
            raise ConflictoError('La competición existente tiene otros datos. No se modificó: revisa nombre, nivel, localidad y fechas.')
        return co['id_competicion']
    if imp['id_competicion']:
        raise ConflictoError('La competición asociada ya no existe.')
    return conexion.execute(text('''
        INSERT INTO public.competicion(nombre, fecha_inicio, fecha_fin, localidad, nivel, id_clase)
        VALUES (:nombre, :fecha_inicio, :fecha_fin, :localidad, :nivel, :clase)
        RETURNING id_competicion
    '''), {**campos, 'nivel': imp['nivel'], 'clase': imp['id_clase']}).scalar_one()


def _anticipar_unidad(conexion, unidad, roles, clase, inicio, fin):
    """Amplía hacia atrás el mismo equipo, sin unir etapas ni cambiar su cierre."""
    u = conexion.execute(text('SELECT * FROM public.unidad_competitiva WHERE id_unidad=:id FOR UPDATE')
                         .columns(fecha_inicio=Date(), fecha_fin=Date()), {'id': unidad}).mappings().first()
    actuales = {r['dni_deportista']: r['rol'] for r in conexion.execute(text(
        'SELECT dni_deportista, rol FROM public.forma_parte WHERE id_unidad=:id'), {'id': unidad}).mappings()}
    if u is None or actuales != roles or (u['fecha_fin'] is not None and u['fecha_fin'] < fin):
        raise ConflictoError('La unidad posterior tiene otros miembros, roles o un cierre incompatible. Revisa sus equipos.')
    conflicto = conexion.execute(text('''SELECT DISTINCT u.id_unidad FROM public.unidad_competitiva u
        JOIN public.forma_parte fp ON fp.id_unidad=u.id_unidad
        WHERE u.id_clase=:clase AND fp.dni_deportista IN :dnis AND u.id_unidad<>:id
          AND u.fecha_inicio<=:anterior AND (u.fecha_fin IS NULL OR u.fecha_fin>=:inicio)
    ''').bindparams(bindparam('dnis', expanding=True)),
        {'clase': clase, 'dnis': sorted(roles), 'id': unidad, 'anterior': u['fecha_inicio'], 'inicio': inicio}).first()
    if conflicto:
        raise ConflictoError('Adelantar el inicio solaparía otra etapa de esta clase. Revisa sus equipos antes de incorporar.')
    if inicio < u['fecha_inicio']:
        conexion.execute(text('UPDATE public.unidad_competitiva SET fecha_inicio=:inicio WHERE id_unidad=:id'),
                         {'inicio': inicio, 'id': unidad})
    return unidad


def _unidad(conexion, imp, campos, miembros, *, personas=None):
    roles = {p['dni_deportista_confirmado']: ('Patron' if imp['numero_tripulantes'] == 1 else p['rol_propuesto'])
             for p in miembros}
    consulta = text('''SELECT dni, fecha_nacimiento FROM public.deportista
                       WHERE dni IN :dnis ORDER BY dni FOR UPDATE''').bindparams(bindparam('dnis', expanding=True)).columns(fecha_nacimiento=Date())
    if personas is None:
        personas = conexion.execute(consulta, {'dnis': sorted(roles)}).mappings().all()
    if len(personas) != len(roles):
        raise ConflictoError('Algún deportista confirmado ya no existe.')
    if any(p['fecha_nacimiento'] and p['fecha_nacimiento'] > campos['fecha_inicio'] for p in personas):
        raise ValidacionError('Un deportista nació después de la regata. Revisa las identidades y las fechas.')
    limite = validar_edad(imp['nombre_clase'], personas, campos['fecha_inicio'], campos['fecha_fin'])
    consulta = text('''
        SELECT DISTINCT u.id_unidad, u.fecha_inicio, u.fecha_fin
        FROM public.unidad_competitiva u JOIN public.forma_parte fp ON fp.id_unidad=u.id_unidad
        WHERE u.id_clase=:clase AND fp.dni_deportista IN :dnis
          AND u.fecha_inicio<=:fin AND (u.fecha_fin IS NULL OR u.fecha_fin>=:inicio)
        ORDER BY u.id_unidad
    ''').bindparams(bindparam('dnis', expanding=True)).columns(fecha_inicio=Date(), fecha_fin=Date())
    unidades = conexion.execute(consulta, {'dnis': sorted(roles), 'clase': imp['id_clase'],
                                          'inicio': campos['fecha_inicio'], 'fin': campos['fecha_fin']}).mappings().all()
    if unidades:
        if len(unidades) == 1:
            # Coordinarse con la finalización de unidades: volver a leer sus
            # fechas después de obtener el mismo bloqueo que usa esa operación.
            u = conexion.execute(text('''SELECT id_unidad, fecha_inicio, fecha_fin
                FROM public.unidad_competitiva WHERE id_unidad=:id FOR UPDATE
            ''').columns(fecha_inicio=Date(), fecha_fin=Date()),
                {'id': unidades[0]['id_unidad']}).mappings().first()
            if u is None:
                raise ConflictoError('El equipo cambió durante la incorporación. Actualiza los datos.')
            actuales = {r['dni_deportista']: r['rol'] for r in conexion.execute(text(
                'SELECT dni_deportista, rol FROM public.forma_parte WHERE id_unidad=:id'), {'id': u['id_unidad']}).mappings()}
            if (actuales == roles and u['fecha_inicio'] <= campos['fecha_inicio']
                    and (u['fecha_fin'] is None or u['fecha_fin'] >= campos['fecha_fin'])):
                return u['id_unidad']
            if actuales == roles and u['fecha_inicio'] > campos['fecha_inicio']:
                return _anticipar_unidad(conexion, u['id_unidad'], roles, imp['id_clase'],
                                         campos['fecha_inicio'], campos['fecha_fin'])
        raise ConflictoError('Un deportista tiene una unidad de esta clase con fechas o miembros incompatibles. Revisa sus equipos antes de incorporar.')
    # Buscar primero la etapa posterior más cercana: se puede adelantar su
    # inicio si conserva miembros, roles y cierre y no cruza otra etapa.
    filtro_limite = ' AND u.fecha_inicio<=:limite' if limite else ''
    futura = conexion.execute(text('''
        SELECT DISTINCT u.id_unidad, u.fecha_inicio FROM public.unidad_competitiva u
        JOIN public.forma_parte fp ON fp.id_unidad=u.id_unidad
        WHERE u.id_clase=:clase AND fp.dni_deportista IN :dnis
          AND u.fecha_inicio>:fin
    ''' + filtro_limite + ' ORDER BY u.fecha_inicio, u.id_unidad').bindparams(bindparam('dnis', expanding=True)),
        {'clase': imp['id_clase'], 'dnis': sorted(roles), 'fin': campos['fecha_fin'], 'limite': limite}).first()
    if futura:
        return _anticipar_unidad(conexion, futura.id_unidad, roles, imp['id_clase'],
                                 campos['fecha_inicio'], campos['fecha_fin'])
    unidad = conexion.execute(text('''
        INSERT INTO public.unidad_competitiva(fecha_inicio,fecha_fin,id_clase)
        VALUES (:inicio,:fin,:clase) RETURNING id_unidad
    '''), {'inicio': campos['fecha_inicio'], 'fin': fin_vencido(limite), 'clase': imp['id_clase']}).scalar_one()
    # Abierta hasta cierre manual o edad ya vencida. Nunca programar una fecha
    # final futura: el usuario puede terminar la unidad antes de ese límite.
    conexion.execute(text('INSERT INTO public.forma_parte(dni_deportista,id_unidad,rol) VALUES (:dni,:unidad,:rol)'),
                     [{'dni': d, 'unidad': unidad, 'rol': r} for d, r in roles.items()])
    return unidad


def incorporar_en_conexion(conexion, identificador, filas, campos, version):
    """Inserta competición, unidades y resultados juntos, sin recrear atletas."""
    base._entero(identificador, 'id_importacion')
    if not isinstance(filas, list) or not filas or any(type(i) is not int or i <= 0 for i in filas) or len(set(filas)) != len(filas):
        raise ValidacionError('Selecciona filas distintas para incorporar.')
    campos = _metadatos(campos)
    imp = datos.obtener_importacion(conexion, identificador, bloquear=True)
    if imp is None or imp['estado'] not in (*base._EDITABLES, 'completada'):
        raise ConflictoError('Este borrador no admite incorporar resultados.')
    revision = dict(importacion=imp, filas=datos.listar_filas(conexion, identificador),
                    participantes=datos.listar_participantes(conexion, identificador))
    if not isinstance(version, str) or version != version_resultados(revision):
        raise ConflictoError('El borrador cambió desde que lo abriste. Actualiza y revisa de nuevo los resultados.')
    por_id = {f['id_fila']: f for f in revision['filas']}
    if any(i not in por_id for i in filas):
        raise ValidacionError('Una fila seleccionada no pertenece a este borrador.')
    seleccionadas = [por_id[i] for i in filas if por_id[i]['estado'] != 'importada']
    if not seleccionadas:
        return 0
    if imp['estado'] == 'completada':
        raise ConflictoError('El borrador ya está completado.')
    if imp['nivel'] not in ('Autonomico', 'Nacional', 'Internacional') or not imp['criterio_inclusion']:
        raise ValidacionError('Falta confirmar el nivel o el criterio de selección de la importación.')
    puestos, documentos = set(), set()
    for f in seleccionadas:
        problemas = incidencias(revision, f)
        if problemas:
            raise ValidacionError(f'Puesto {f["posicion_general"]}: ' + ' '.join(problemas))
        if f['posicion_general'] in puestos:
            raise ConflictoError('Hay dos filas con el mismo puesto general. Revisa la clasificación antes de incorporar.')
        puestos.add(f['posicion_general'])
        miembros = miembros_fila(revision, f)
        dnis = {p['dni_deportista_confirmado'] for p in miembros}
        if documentos.intersection(dnis):
            raise ConflictoError('Un deportista está confirmado en varias embarcaciones de la misma regata.')
        documentos.update(dnis)
    co = _competicion(conexion, imp, campos)
    # El bloqueo de la competición serializa otros lotes de resultados.
    conexion.execute(text('SELECT id_competicion FROM public.competicion WHERE id_competicion=:id FOR UPDATE'), {'id': co})
    conexion.execute(text('''UPDATE public.importacion_clasificacion SET id_competicion=:co,
        nombre_competicion_propuesto=:nombre, fecha_inicio_propuesta=:fecha_inicio,
        fecha_fin_propuesta=:fecha_fin, localidad_propuesta=:localidad,
        tipo_clasificacion=:tipo_clasificacion WHERE id_importacion=:id'''), {**campos, 'co': co, 'id': identificador})
    personas = {p['dni']:dict(p) for p in conexion.execute(text('''SELECT dni,fecha_nacimiento
        FROM public.deportista WHERE dni IN :dnis ORDER BY dni FOR UPDATE''')
        .bindparams(bindparam('dnis',expanding=True)).columns(fecha_nacimiento=Date()),
        {'dnis':sorted(documentos)}).mappings()}
    anteriores = list(conexion.execute(text('SELECT * FROM public.participa_en WHERE id_competicion=:co')
        .columns(puntos=Numeric(10,2)),{'co':co}).mappings())
    participantes_previos = {p[0] for p in conexion.execute(text('''SELECT fp.dni_deportista
        FROM public.participa_en p JOIN public.forma_parte fp ON fp.id_unidad=p.id_unidad
        WHERE p.id_competicion=:co'''),{'co':co})}
    for f in seleccionadas:
        miembros = miembros_fila(revision, f)
        dnis = [p['dni_deportista_confirmado'] for p in miembros]
        unidad = _unidad(conexion, imp, campos, miembros,personas=[personas[d] for d in dnis if d in personas])
        previos = [p for p in anteriores if p['id_unidad']==unidad or p['posicion_general']==f['posicion_general']]
        if previos:
            igual = (len(previos) == 1 and previos[0]['id_unidad'] == unidad
                     and all(previos[0][k] == f[k] for k in ('posicion_general', 'posicion_categoria', 'puntos')))
            if not igual:
                raise ConflictoError('Ya existe otro resultado para ese puesto o equipo. No se sobrescribió: revisa la clasificación.')
        else:
            if participantes_previos.intersection(dnis):
                raise ConflictoError('Un deportista ya tiene un resultado con otro equipo en esta regata.')
            conexion.execute(text('''INSERT INTO public.participa_en
                (id_unidad,id_competicion,posicion_general,posicion_categoria,puntos)
                VALUES (:unidad,:co,:posicion_general,:posicion_categoria,:puntos)
            ''').bindparams(bindparam('puntos', type_=Numeric(10, 2))), {**f, 'unidad': unidad, 'co': co})
        conexion.execute(text('''UPDATE public.fila_clasificacion_importada
            SET estado='importada', id_unidad_confirmada=:unidad,
                id_competicion_confirmada=:co, incidencias=NULL WHERE id_fila=:id
        '''), {'unidad': unidad, 'co': co, 'id': f['id_fila']})
    pendientes = conexion.execute(text('''SELECT COUNT(*) FROM public.fila_clasificacion_importada
        WHERE id_importacion=:id AND estado NOT IN ('importada','excluida')
          AND (cumple_criterio IS TRUE OR cumple_criterio IS NULL)'''), {'id': identificador}).scalar_one()
    conexion.execute(text('UPDATE public.importacion_clasificacion SET estado=:estado WHERE id_importacion=:id'),
                     {'id': identificador, 'estado': 'parcialmente_importada' if pendientes else 'completada'})
    return len(seleccionadas)


def incorporar(engine, identificador, filas, campos, version):
    try:
        with engine.begin() as conexion:
            return incorporar_en_conexion(conexion, identificador, filas, campos, version)
    except IntegrityError:
        raise ConflictoError('No se incorporó ningún resultado del lote: hay referencias o datos incompatibles. Actualiza y revisa la clasificación.') from None


def guardar_con_resultado(engine, participante, accion, campos, version,
                         dni_existente, confirmar_nuevo_distinto, datos_resultado, version_importacion):
    """Una transacción para el alta y su resultado; dobles esperan a ambos miembros."""
    from services.revision_participantes import guardar_revision_en_conexion
    if accion not in ('crear', 'vincular'):
        raise ValidacionError('El guardado conjunto requiere crear o vincular una identidad.')
    try:
        with engine.begin() as conexion:
            p = base._bloquear_participante(conexion, participante)
            def contenido():
                return dict(importacion=datos.obtener_importacion(conexion, p['id_importacion']),
                            filas=datos.listar_filas(conexion, p['id_importacion']),
                            participantes=datos.listar_participantes(conexion, p['id_importacion']))
            antes = contenido()
            if not isinstance(version_importacion, str) or version_resultados(antes) != version_importacion:
                raise ConflictoError('La clasificación cambió desde que la abriste. Actualiza antes de crear o vincular.')
            fila_antes = next(f for f in antes['filas'] if f['id_fila'] == p['id_fila'])
            conjunta = accion == 'crear' or any(m['estado'] == 'nuevo_confirmado'
                and m['id_participante_importado'] != participante for m in miembros_fila(antes, fila_antes))
            if conjunta:
                metadatos = _metadatos(datos_resultado)
                # Mismo orden de bloqueo que la incorporación por lotes.
                conexion.execute(text('SELECT id_clase FROM public.clase WHERE id_clase=:id FOR UPDATE'),
                                 {'id': antes['importacion']['id_clase']})
                if antes['importacion']['id_competicion']:
                    _competicion(conexion, antes['importacion'], metadatos)
                # La validación del nacimiento debe utilizar las fechas corregidas
                # en este formulario, no las propuestas anteriores del borrador.
                conexion.execute(text('''UPDATE public.importacion_clasificacion SET
                    nombre_competicion_propuesto=:nombre, fecha_inicio_propuesta=:fecha_inicio,
                    fecha_fin_propuesta=:fecha_fin, localidad_propuesta=:localidad,
                    tipo_clasificacion=:tipo_clasificacion WHERE id_importacion=:id
                '''), {**metadatos, 'id': p['id_importacion']})
            dni = guardar_revision_en_conexion(conexion, participante, accion, campos, version,
                                               dni_existente, confirmar_nuevo_distinto)
            actual = contenido()
            fila = next(f for f in actual['filas'] if f['id_fila'] == p['id_fila'])
            nuevos = any(m['estado'] == 'nuevo_confirmado' for m in miembros_fila(actual, fila))
            if not nuevos or not conjunta:
                # Fichas ya existentes mantienen la revisión separada de resultados.
                return dict(dni=dni, resultado_incorporado=False, pendiente_equipo=False)
            problemas = incidencias(actual, fila)
            if problemas:
                return dict(dni=dni, resultado_incorporado=False, pendiente_equipo=True,
                            incidencias=problemas)
            incorporar_en_conexion(conexion, p['id_importacion'], [p['id_fila']], metadatos,
                                   version_resultados(actual))
            return dict(dni=dni, resultado_incorporado=True, pendiente_equipo=False)
    except IntegrityError:
        raise ConflictoError('No se guardó el alta ni su resultado: hay datos duplicados o referencias incompatibles. Revisa la clasificación antes de reintentar.') from None


def incorporar_en_proveedor(proveedor, identificador, filas, campos, version):
    from database.database import crear_engine
    motor = crear_engine(proveedor)
    try:
        return incorporar(motor, identificador, filas, campos, version)
    finally:
        motor.dispose()
