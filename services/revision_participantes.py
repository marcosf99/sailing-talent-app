"""Revisión humana de identidades. Sin dependencias de interfaz ni credenciales."""
from datetime import date
from decimal import Decimal
from difflib import SequenceMatcher
import hashlib
import json
import re
import unicodedata

from sqlalchemy.exc import IntegrityError

from database import importaciones as datos
from services import importaciones as base
from services import deportistas
from services.deportistas import ValidacionError, ConflictoError


_VERSION = ('id_participante_importado', 'estado', 'dni_deportista_confirmado', 'confirmado_en',
            'nombre_propuesto', 'apellidos_propuestos', 'documento_propuesto',
            'fecha_nacimiento_propuesta', 'sexo_propuesto', 'id_club_identificado',
            'rol_propuesto', 'observaciones_revision')
_CAMPOS = {'dni', 'nombre', 'apellidos', 'fecha_nacimiento', 'sexo', 'id_club',
           'rol_propuesto', 'observaciones_revision'}


def normalizar(valor):
    texto = ''.join(c for c in unicodedata.normalize('NFKD', valor or '')
                    if not unicodedata.combining(c))
    return ' '.join(re.sub(r'[\W_]+', ' ', texto.casefold()).split())


def version_participante(participante):
    """Compara también los campos pendientes; evita sobrescribir otra revisión."""
    valores = [None if participante.get(c) is None else str(participante[c]) for c in _VERSION]
    return hashlib.sha256(json.dumps(valores, ensure_ascii=False).encode()).hexdigest()


def _similitud_nombre(origen, nombre):
    a, b = normalizar(origen), normalizar(nombre)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    # Comparar palabras sin depender del orden o de que haya dos apellidos.
    ta = [t for t in a.split() if t not in ('de', 'del', 'la', 'las', 'los', 'y')]
    tb = [t for t in b.split() if t not in ('de', 'del', 'la', 'las', 'los', 'y')]
    if not ta or not tb:
        return 0.0
    libres = list(tb)
    coincidencias = 0.0
    for token in ta:
        if not libres:
            break
        mejor = max(libres, key=lambda t: SequenceMatcher(None, token, t).ratio())
        parecido = SequenceMatcher(None, token, mejor).ratio()
        if parecido >= .8:
            coincidencias += parecido
            libres.remove(mejor)
    return .7 * coincidencias / len(ta) + .3 * SequenceMatcher(None, a, b).ratio()


def _club_normalizado(nombre):
    texto = normalizar(nombre)
    compacto = ''.join(t for t in texto.split() if t not in ('de', 'del', 'la'))
    for corto, largo in [('mrcyb', 'monterealclubyatesbaiona'), ('cvf', 'clubvelafluvial'),
                         ('rcn', 'realclubnautico'), ('cnd', 'clubnauticodeportivo'),
                         ('cn', 'clubnautico'), ('cm', 'clubmaritimo')]:
        if compacto.startswith(corto):
            compacto = largo + compacto[len(corto):]
            break
    return compacto


def _candidatos(conexion, participante, consulta='', limite=10, *, fichas=None, aliases=None):
    origen = ' '.join(filter(None, [participante.get('nombre_propuesto'), participante.get('apellidos_propuestos')])) or participante['nombre_original']
    documento = (participante.get('documento_propuesto') or '').upper()
    nombre_club = participante.get('club_original') or ''
    id_club = participante.get('id_club_identificado')
    aliases = {a['id_club'] for a in (datos.aliases_revision(conexion) if aliases is None else aliases)
               if a['texto_normalizado'] == normalizar(nombre_club)}
    consulta_normal = normalizar(consulta)
    salida = []
    for ficha in (datos.fichas_revision(conexion) if fichas is None else fichas):
        completo = ficha['nombre'] + ' ' + ficha['apellidos']
        nombre = max(_similitud_nombre(origen, completo), _similitud_nombre(participante['nombre_original'], completo))
        mismo_documento = bool(documento and ficha['dni'].upper() == documento)
        if consulta:
            buscable = normalizar(completo + ' ' + ficha['dni'])
            if not all(t in buscable for t in consulta_normal.split()):
                continue
        elif nombre < .6 and not mismo_documento:
            continue
        motivos = []
        if mismo_documento:
            motivos.append('Coincide el documento propuesto')
        if nombre >= .999:
            motivos.append('Coincide el nombre completo, ignorando acentos y puntuación')
        elif nombre >= .6:
            motivos.append('Nombre o apellidos similares; puede faltar un apellido')
        club = 0.0
        if id_club is not None and id_club == ficha['id_club']:
            club = 1.0
            motivos.append('Coincide el club identificado en la revisión')
        elif id_club is None and ficha['id_club'] is not None and ficha['id_club'] in aliases:
            club = 1.0
            motivos.append('Coincide un alias confirmado del club')
        elif id_club is None and nombre_club and ficha['club']:
            club = SequenceMatcher(None, _club_normalizado(nombre_club), _club_normalizado(ficha['club'])).ratio()
            if club >= .85:
                motivos.append('El texto del club es similar')
            else:
                club = 0.0
        federacion = normalizar(participante.get('federacion_original'))
        misma_fed = bool(federacion and federacion == normalizar(ficha['federacion']))
        if misma_fed:
            motivos.append('Coincide la federación indicada en la fuente')
        puntuacion = 1.0 if mismo_documento else min(.99999, .88 * nombre + .1 * club + .02 * misma_fed)
        salida.append({**ficha, 'indice_similitud': Decimal(str(round(puntuacion, 5))),
                       'motivos': '; '.join(motivos) or 'Resultado de la búsqueda manual'})
    return sorted(salida, key=lambda r: (-r['indice_similitud'], r['apellidos'], r['nombre'], r['dni']))[:limite]


def buscar_coincidencias(engine, participante, consulta='', limite=10):
    base._entero(participante, 'id_participante_importado')
    consulta = base._texto(consulta, 'consulta', 200) or ''
    if type(limite) is not int or not 1 <= limite <= 100:
        raise ValidacionError('El límite debe estar entre 1 y 100.')
    with engine.connect() as conexion:
        p = datos.contexto_participante(conexion, participante)
        if p is None:
            raise ValidacionError('El participante no existe.')
        return _candidatos(conexion, p, consulta, limite)


def cargar_revision(engine, identificador):
    borrador = base.obtener_borrador(engine, identificador)
    if borrador is None:
        raise ValidacionError('El borrador no existe.')
    seleccionadas = {f['id_fila']: f for f in borrador['filas'] if f['cumple_criterio'] is True and f['estado'] != 'excluida'}
    participantes = [{**p, 'fila': seleccionadas[p['id_fila']], 'version': version_participante(p)}
                     for p in borrador['participantes'] if p['id_fila'] in seleccionadas]
    return {**borrador, 'seleccionadas': list(seleccionadas.values()), 'participantes_revision': participantes}


def _validar_campos(campos, completo=False):
    if not isinstance(campos, dict) or set(campos) - _CAMPOS:
        raise ValidacionError('La revisión contiene campos no admitidos.')
    if completo:
        ficha = deportistas.validar(campos)
    else:
        ficha = {k: base._texto(campos.get(k), k, n) for k, n in
                 [('dni', 20), ('nombre', 100), ('apellidos', 150)]}
        if ficha['dni']:
            ficha['dni'] = ficha['dni'].upper()
        ficha['fecha_nacimiento'] = base._fecha(campos.get('fecha_nacimiento'), 'fecha_nacimiento')
        if ficha['fecha_nacimiento'] and ficha['fecha_nacimiento'] > date.today():
            raise ValidacionError('La fecha de nacimiento no puede ser futura.')
        ficha['sexo'] = campos.get('sexo')
        if ficha['sexo'] not in (None, 'Masculino', 'Femenino'):
            raise ValidacionError('Selecciona un sexo válido o Sin registrar.')
        ficha['id_club'] = base._entero(campos.get('id_club'), 'id_club', True)
    rol = campos.get('rol_propuesto')
    if rol not in (None, 'Patron', 'Tripulante'):
        raise ValidacionError('Selecciona un rol válido o Sin confirmar.')
    propuesta = dict(nombre_propuesto=ficha['nombre'], apellidos_propuestos=ficha['apellidos'],
                     documento_propuesto=ficha['dni'], fecha_nacimiento_propuesta=ficha['fecha_nacimiento'],
                     sexo_propuesto=ficha['sexo'], id_club_identificado=ficha['id_club'], rol_propuesto=rol,
                     observaciones_revision=base._texto(campos.get('observaciones_revision'), 'observaciones_revision'))
    return ficha, propuesta


def estado_fila(fila, miembros, tripulantes):
    faltas = []
    if fila['posicion_general'] is None:
        faltas.append('Falta la posición general.')
    if fila['puntos'] is None:
        faltas.append('Falta la puntuación.')
    if len(miembros) != tripulantes:
        faltas.append(f'Se esperaban {tripulantes} tripulantes; hay {len(miembros)}.')
    if tripulantes == 2 and sorted((m['rol_propuesto'] or '') for m in miembros) != ['Patron', 'Tripulante']:
        faltas.append('Confirma un patrón y un tripulante.')
    confirmados = len(miembros) == tripulantes and all(m['dni_deportista_confirmado'] for m in miembros)
    estado = 'requiere_correccion' if faltas else ('lista' if confirmados else 'pendiente')
    return estado, ' '.join(faltas) or None


def _refrescar_fila(conexion, fila, tripulantes):
    estado, incidencias = estado_fila(fila, datos.miembros_revision(conexion, fila['id_fila']), tripulantes)
    datos.estado_fila_revision(conexion, fila['id_fila'], estado, incidencias)


def guardar_revision_en_conexion(conexion, participante, accion, campos, version,
                     dni_existente=None, confirmar_nuevo_distinto=False, *, fichas=None, aliases=None):
    """Guarda ficha e identidad dentro de la transacción abierta por el llamador."""
    if accion not in ('pendiente', 'vincular', 'crear'):
        raise ValidacionError('Selecciona una operación de revisión válida.')
    if accion == 'crear' and isinstance(campos, dict):
        campos = {**campos, 'dni': deportistas.documento_para_alta(conexion, campos.get('dni'))}
    ficha, propuesta = _validar_campos(campos, completo=accion == 'crear')
    p = base._bloquear_participante(conexion, participante)
    if not isinstance(version, str) or version_participante(p) != version:
        raise ConflictoError('La revisión cambió desde que la abriste. Actualiza los datos antes de guardar.')
    imp = datos.obtener_importacion(conexion, p['id_importacion'])
    if imp['numero_tripulantes'] == 1:
        propuesta['rol_propuesto'] = 'Patron'
    competicion = datos.referencia_competicion(conexion, imp['id_competicion']) if imp['id_competicion'] else None
    fecha_regata = competicion['fecha_inicio'] if competicion else imp['fecha_inicio_propuesta']
    if ficha['id_club'] is not None and not datos.existe_club(conexion, ficha['id_club']):
        raise ValidacionError('El club seleccionado ya no existe.')
    if accion in ('crear', 'pendiente') and p['dni_deportista_confirmado']:
        raise ConflictoError('La identidad ya está confirmada. Usa Vincular ficha existente para corregir el vínculo.')
    candidatos = _candidatos(conexion, {**p, **propuesta}, fichas=fichas, aliases=aliases)
    for candidato in candidatos:
        datos.guardar_sugerencia(conexion, participante, candidato['dni'],
                                 candidato['indice_similitud'], candidato['motivos'])
    if accion == 'crear':
        if datos.ficha_por_documento(conexion, ficha['dni']):
            raise ConflictoError('Ya existe una ficha con ese documento. Vincula la ficha existente.')
        if candidatos and confirmar_nuevo_distinto is not True:
            raise ValidacionError('Hay fichas similares. Revisa las coincidencias y confirma que es una persona diferente.')
        datos.insertar_ficha_revision(conexion, ficha)
        dni, estado = ficha['dni'], 'nuevo_confirmado'
    elif accion == 'vincular':
        dni = base._texto(dni_existente, 'dni_existente', 20, True).upper()
        existente = datos.ficha_por_documento(conexion, dni)
        if existente is None:
            raise ValidacionError('La ficha seleccionada ya no existe.')
        # Usar el documento almacenado, incluso en fichas antiguas con otro formato.
        dni, estado = existente['dni'], 'vinculado'
        nacimiento = existente['fecha_nacimiento']
        if nacimiento and fecha_regata and nacimiento > fecha_regata:
            raise ValidacionError('La ficha nació después de la fecha de la regata. Revisa la identidad o la fecha.')
        datos.guardar_sugerencia(conexion, participante, dni, None, 'Vinculación confirmada por el usuario')
    else:
        dni, estado = None, 'pendiente_datos'
    if accion != 'vincular' and ficha['fecha_nacimiento'] and fecha_regata and ficha['fecha_nacimiento'] > fecha_regata:
        raise ValidacionError('El nacimiento no puede ser posterior a la regata.')
    if dni is not None:
        datos.rechazar_otras_sugerencias(conexion, participante, dni)
        datos.confirmar_identidad(conexion, participante, dni)
    datos.actualizar_revision(conexion, participante, propuesta, estado)
    fila = datos.fila_revision(conexion, p['id_fila'])
    _refrescar_fila(conexion, fila, imp['numero_tripulantes'])
    datos.marcar_en_revision(conexion, p['id_importacion'])
    return dni


def guardar_revision(engine, participante, accion, campos, version,
                     dni_existente=None, confirmar_nuevo_distinto=False):
    try:
        with engine.begin() as conexion:
            return guardar_revision_en_conexion(conexion, participante, accion, campos, version,
                                                 dni_existente, confirmar_nuevo_distinto)
    except IntegrityError:
        raise ConflictoError('No se guardó la revisión: el documento ya existe, el deportista ya está en la tripulación o una referencia ha cambiado.') from None


def agregar_miembro(engine, fila, nombre_original, orden):
    """Completa un hueco de tripulación sin crear todavía una ficha definitiva."""
    base._entero(fila, 'id_fila')
    nombre = base._texto(nombre_original, 'nombre_original', obligatorio=True)
    base._entero(orden, 'orden_en_tripulacion', maximo=32767)
    try:
        with engine.begin() as conexion:
            f = datos.fila_revision(conexion, fila)
            if f is None:
                raise ValidacionError('La fila ya no existe.')
            imp = base._editable(conexion, f['id_importacion'])
            f = datos.fila_revision(conexion, fila)
            if not f or not f['cumple_criterio'] or f['estado'] in ('excluida', 'importada'):
                raise ValidacionError('Solo se pueden completar filas seleccionadas y pendientes.')
            if orden > imp['numero_tripulantes']:
                raise ValidacionError('El orden supera el número de tripulantes de la clase.')
            ident = datos.insertar(conexion, 'participante_importado', {
                'id_fila': fila, 'nombre_original': nombre, 'orden_en_tripulacion': orden,
                'estado': 'pendiente_revision',
            })
            _refrescar_fila(conexion, f, imp['numero_tripulantes'])
            datos.marcar_en_revision(conexion, imp['id_importacion'])
    except IntegrityError:
        raise ConflictoError('Ese hueco de la tripulación ya está ocupado. Actualiza la revisión.') from None
    return ident


def guardar_en_proveedor(proveedor, participante, accion, campos, version,
                         dni_existente=None, confirmar_nuevo_distinto=False,
                         *, datos_resultado=None, version_importacion=None):
    from database.database import crear_engine
    motor = crear_engine(proveedor)
    try:
        if datos_resultado is not None:
            from services.resultados_importados import guardar_con_resultado
            return guardar_con_resultado(motor, participante, accion, campos, version,
                                         dni_existente, confirmar_nuevo_distinto,
                                         datos_resultado, version_importacion)
        return guardar_revision(motor, participante, accion, campos, version,
                                dni_existente, confirmar_nuevo_distinto)
    finally:
        motor.dispose()


def agregar_en_proveedor(proveedor, fila, nombre_original, orden):
    from database.database import crear_engine
    motor = crear_engine(proveedor)
    try:
        return agregar_miembro(motor, fila, nombre_original, orden)
    finally:
        motor.dispose()
