"""Revisión explícita por lotes: propuestas de lectura y escrituras atómicas."""
from difflib import SequenceMatcher
from decimal import Decimal
import hashlib
import json

from sqlalchemy.exc import IntegrityError

from database import importaciones as datos
from services import importaciones as base
from services import revision_participantes as revision
from services import resultados_importados as resultados
from services.deportistas import ValidacionError, ConflictoError


def _huella(valor):
    return hashlib.sha256(json.dumps(valor, sort_keys=True, default=str).encode()).hexdigest()


def _contenido(c, identificador, bloquear=False):
    imp = base._editable(c, identificador) if bloquear else datos.obtener_importacion(c, identificador)
    if imp is None:
        raise ValidacionError('El borrador ya no existe.')
    return {'importacion': imp, 'filas': datos.listar_filas(c, identificador),
            'participantes': datos.listar_participantes(c, identificador)}


def _pendientes(contenido):
    filas = {f['id_fila']: f for f in contenido['filas']
             if f['cumple_criterio'] is True and f['estado'] not in ('importada', 'excluida')
             and base.evaluar_seleccion(contenido['importacion']['nivel'], f['posicion_general'],
                                       f['numero_vela_original'])['cumple_criterio'] is True}
    return [{**p, 'fila': filas[p['id_fila']]} for p in contenido['participantes']
            if p['id_fila'] in filas and not p['dni_deportista_confirmado']]


def _grupos(contenido):
    grupos = {}
    for p in _pendientes(contenido):
        if p['id_club_identificado'] is not None:
            continue  # Una decisión ya confirmada no vuelve a ser tarea pendiente.
        normal = revision.normalizar(p.get('club_original'))
        if not normal:
            continue  # La ausencia de texto no identifica un club compartido.
        grupo = grupos.setdefault(normal, {'normalizado': normal, 'textos': set(), 'participantes': []})
        grupo['textos'].add(p['club_original'])
        grupo['participantes'].append(p)
    for grupo in grupos.values():
        grupo['textos'] = sorted(grupo['textos'])
        grupo['version'] = _huella([grupo['normalizado'], grupo['textos'],
            [(p['id_participante_importado'], revision.version_participante(p)) for p in grupo['participantes']]])
    return list(grupos.values())


def _sugerir_club(grupo, clubes, aliases):
    conocidos = {p['id_club_identificado'] for p in grupo['participantes']}
    if len(conocidos) == 1 and None not in conocidos:
        return next(iter(conocidos)), 'Identificado en esta revisión'
    if len(conocidos) > 1:
        return None, 'Hay decisiones distintas: revisar individualmente'
    alias = {a['id_club'] for a in aliases if a['texto_normalizado'] == grupo['normalizado']}
    if len(alias) == 1:
        return next(iter(alias)), 'Equivalencia confirmada anteriormente'
    if alias:
        return None, 'Equivalencia ambigua'
    exactos = [c for c in clubes if revision.normalizar(c['nombre']) == grupo['normalizado']
               or revision._club_normalizado(c['nombre']) == revision._club_normalizado(grupo['textos'][0])]
    if len(exactos) == 1:
        return exactos[0]['id_club'], 'Coincide el nombre o su abreviatura'
    if exactos:
        return None, 'Varios clubes coinciden con el texto'
    ordenados = sorted(((SequenceMatcher(None, revision._club_normalizado(grupo['textos'][0]),
                                        revision._club_normalizado(c['nombre'])).ratio(), c['id_club'])
                        for c in clubes), reverse=True)
    if ordenados and ordenados[0][0] >= .7 and (len(ordenados) == 1 or ordenados[0][0]-ordenados[1][0] >= .08):
        return ordenados[0][1], 'Sugerencia por texto: comprobar'
    return None, 'Seleccionar un club o dejar pendiente'


def _version_ficha(ficha):
    return _huella({k: ficha.get(k) for k in ('dni', 'nombre', 'apellidos', 'fecha_nacimiento', 'sexo', 'id_club', 'memoria_nombres')})


def _propuestas(c, contenido, fichas, aliases):
    salida = []
    for p in _pendientes(contenido):
        candidatos = revision._candidatos(c, p, limite=5, fichas=fichas, aliases=aliases)
        propuesta, motivo = None, 'Sin coincidencia suficiente: revisión individual'
        if candidatos:
            primero = candidatos[0]
            documento = (p.get('documento_propuesto') or '').upper()
            exacto = bool(documento and documento == primero['dni'].upper()
                          and sum(f['dni'].upper() == documento for f in fichas) == 1)
            clara = (primero['indice_similitud'] >= Decimal('.75') and (len(candidatos) == 1
                     or primero['indice_similitud']-candidatos[1]['indice_similitud'] >= Decimal('.05')))
            nacimiento = p.get('fecha_nacimiento_propuesta')
            compatible = not (nacimiento and primero.get('fecha_nacimiento') and nacimiento != primero['fecha_nacimiento'])
            if exacto or (clara and compatible):
                propuesta = {**primero, 'version_ficha': _version_ficha(primero)}
                motivo = primero['motivos']
            else:
                motivo = 'Coincidencias ambiguas: revisión individual'
        salida.append({'participante': p, 'version': revision.version_participante(p),
                       'propuesta': propuesta, 'motivo': motivo, 'coincidencias': len(candidatos),
                       'candidatos': candidatos})
    documentos = [r['propuesta']['dni'] for r in salida if r['propuesta']]
    confirmados = {p['dni_deportista_confirmado'] for p in contenido['participantes']
                   if p['dni_deportista_confirmado'] and any(
                       f['id_fila'] == p['id_fila'] and f['cumple_criterio'] is True and f['estado'] != 'excluida'
                       for f in contenido['filas'])}
    for r in salida:
        if r['propuesta'] and (documentos.count(r['propuesta']['dni']) > 1 or r['propuesta']['dni'] in confirmados):
            r['propuesta'] = None
            r['motivo'] = 'La ficha aparece en otra posición de esta clasificación: revisión individual'
    return salida


def incidencias_altas(contenido, decisiones):
    """Simula solo las identidades seleccionadas, sin escribir fichas ni resultados."""
    cambios = {d['participante']: d['campos'] for d in decisiones}
    personas = []
    afectadas = set()
    for p in contenido['participantes']:
        campos = cambios.get(p['id_participante_importado'])
        if campos is not None:
            afectadas.add(p['id_fila'])
            p = {**p, 'dni_deportista_confirmado': 'ALTA-' + str(p['id_participante_importado']),
                 'estado': 'nuevo_confirmado', 'rol_propuesto': (
                     'Patron' if contenido['importacion']['numero_tripulantes'] == 1
                     else campos.get('rol_propuesto'))}
        personas.append(p)
    previsto = {**contenido, 'participantes': personas}
    salida = {}
    for fila in contenido['filas']:
        if fila['id_fila'] not in afectadas:
            continue
        errores = resultados.incidencias(previsto, fila)
        pendientes = [p['nombre_original'] for p in resultados.miembros_fila(previsto, fila)
                      if not p['dni_deportista_confirmado']]
        if pendientes:
            errores = ['Falta revisar o seleccionar a: ' + ', '.join(pendientes)] + errores
        if errores:
            salida[fila['id_fila']] = f"Puesto {fila['posicion_general']}: " + ' '.join(errores)
    return salida


def similitudes_altas(contenido, decisiones):
    """Coincidencias entre personas seleccionadas, todavía fuera del catálogo."""
    personas = {p['id_participante_importado']:p for p in contenido['participantes']}
    previas, salida = [], []
    for d in decisiones:
        campos = d['campos']
        p = personas[d['participante']]
        propuesta = {**p, 'nombre_propuesto':campos.get('nombre'),
                     'apellidos_propuestos':campos.get('apellidos')}
        for c in revision._candidatos(None, propuesta, fichas=previas, aliases=[]):
            salida.append({'Participante': (campos.get('nombre') or '') + ' ' + (campos.get('apellidos') or ''),
                           'Otra alta del lote':c['nombre'] + ' ' + c['apellidos']})
        previas.append(dict(campos,dni='ALTA-'+str(d['participante']),club=None,
                            federacion=None,id_federacion=None))
    return salida


def cargar_resumen(engine, identificador):
    base._entero(identificador, 'id_importacion')
    with engine.connect() as c:
        contenido = _contenido(c, identificador)
        clubes, aliases, fichas = datos.clubes_revision(c), datos.aliases_revision(c), datos.fichas_revision(c)
        grupos = []
        for g in _grupos(contenido):
            club, motivo = _sugerir_club(g, clubes, aliases)
            grupos.append({**g, 'id_club_propuesto': club, 'motivo': motivo})
        return {'grupos_club': grupos, 'propuestas': _propuestas(c, contenido, fichas, aliases),
                'version': resultados.version_resultados(contenido)}


def confirmar_clubes(engine, identificador, decisiones, *, confirmar=False):
    if confirmar is not True or not isinstance(decisiones, list) or not decisiones:
        raise ValidacionError('Selecciona y confirma las equivalencias de clubes que has revisado.')
    try:
        with engine.begin() as c:
            contenido = _contenido(c, identificador, True)
            grupos = {g['normalizado']: g for g in _grupos(contenido)}
            vistos, total = set(), 0
            for d in decisiones:
                if not isinstance(d, dict) or set(d) != {'normalizado', 'id_club', 'recordar', 'version'}:
                    raise ValidacionError('Una decisión de club contiene campos inválidos.')
                normal = d['normalizado']
                if not isinstance(normal, str) or normal in vistos or normal not in grupos:
                    raise ConflictoError('Los clubes pendientes han cambiado. Actualiza la revisión.')
                vistos.add(normal)
                grupo = grupos[normal]
                if d['version'] != grupo['version']:
                    raise ConflictoError('Cambió una de las revisiones del club. Actualiza antes de guardar.')
                club = base._entero(d['id_club'], 'id_club')
                if type(d['recordar']) is not bool or not datos.existe_club(c, club):
                    raise ValidacionError('Selecciona un club existente y una opción de equivalencia válida.')
                if d['recordar']:
                    texto = base._texto(grupo['textos'][0], 'texto_alias', 250, True)
                    base._texto(normal, 'texto_normalizado', 250, True)
                    if datos.recordar_alias_revision(c, texto, normal, club) != [club]:
                        raise ConflictoError('La abreviatura ya corresponde a otro club. Puedes aplicarla solo a este documento sin recordar la equivalencia.')
                datos.identificar_clubes_lote(c, [p['id_participante_importado'] for p in grupo['participantes']], club)
                total += len(grupo['participantes'])
            datos.marcar_en_revision(c, identificador)
            return {'clubes': len(vistos), 'participantes': total}
    except IntegrityError:
        raise ConflictoError('No se guardó el lote de clubes: una equivalencia o referencia ha cambiado. Actualiza la revisión.') from None


def confirmar_vinculos(engine, identificador, decisiones, version, *, confirmar=False, datos_resultado=None):
    if confirmar is not True or not isinstance(decisiones, list) or not decisiones:
        raise ValidacionError('Selecciona y confirma las vinculaciones revisadas.')
    try:
        with engine.begin() as c:
            contenido = _contenido(c, identificador, True)
            if not isinstance(version, str) or version != resultados.version_resultados(contenido):
                raise ConflictoError('El borrador cambió. Actualiza la revisión antes de confirmar el lote.')
            fichas, aliases = datos.fichas_revision(c), datos.aliases_revision(c)
            clubes_validos = {cl['id_club'] for cl in datos.clubes_revision(c)}
            if datos_resultado is not None:
                fecha_regata = resultados._metadatos(datos_resultado)['fecha_inicio']
            else:
                competicion = datos.referencia_competicion(c, contenido['importacion']['id_competicion']) if contenido['importacion']['id_competicion'] else None
                fecha_regata = competicion['fecha_inicio'] if competicion else contenido['importacion']['fecha_inicio_propuesta']
            propuestas = {r['participante']['id_participante_importado']: r for r in _propuestas(c, contenido, fichas, aliases)}
            vistos, documentos, preparadas = set(), set(), []
            seleccionadas = {f['id_fila'] for f in contenido['filas'] if f['cumple_criterio'] is True and f['estado'] != 'excluida'}
            confirmados = {p['dni_deportista_confirmado'] for p in contenido['participantes']
                           if p['id_fila'] in seleccionadas and p['dni_deportista_confirmado']}
            for d in decisiones:
                if not isinstance(d, dict) or not {'participante', 'dni', 'version_ficha', 'rol'} <= set(d) or set(d) - {'participante', 'dni', 'version_ficha', 'rol', 'recordar_nombre'}:
                    raise ValidacionError('Una vinculación contiene campos inválidos.')
                ident = base._entero(d['participante'], 'id_participante_importado')
                if ident in vistos or ident not in propuestas:
                    raise ConflictoError('Un participante está repetido o ya no está pendiente.')
                vistos.add(ident)
                r, dni = propuestas[ident], d['dni']
                if type(d.get('recordar_nombre',False)) is not bool:
                    raise ValidacionError('Confirma si quieres recordar los nombres del lote.')
                p = r['participante']
                if d.get('recordar_nombre') and p['id_club_identificado'] is None:
                    raise ValidacionError(f"{p['nombre_original']}: confirma el club de la fuente antes de recordar el nombre.")
                contexto = f"Puesto {p['fila']['posicion_general']} · {p['nombre_original']}: "
                ficha = r['propuesta']
                if not ficha or dni != ficha['dni'] or d['version_ficha'] != ficha['version_ficha']:
                    raise ConflictoError(contexto + 'La ficha propuesta cambió o necesita revisión individual. Actualiza las propuestas.')
                if dni in documentos or dni in confirmados:
                    raise ConflictoError(contexto + 'La misma ficha aparece en varias posiciones de esta clasificación. Revisa las identidades individualmente.')
                documentos.add(dni)
                rol = 'Patron' if contenido['importacion']['numero_tripulantes'] == 1 else d['rol']
                if rol not in ('Patron', 'Tripulante'):
                    raise ValidacionError(contexto + 'Confirma su rol: patrón o tripulante.')
                p = r['participante']
                if p['id_club_identificado'] is not None and p['id_club_identificado'] not in clubes_validos:
                    raise ValidacionError(contexto + 'El club seleccionado ya no existe.')
                if ficha['fecha_nacimiento'] and fecha_regata and ficha['fecha_nacimiento'] > fecha_regata:
                    raise ValidacionError(contexto + 'La ficha nació el ' + resultados._fecha_aviso(ficha['fecha_nacimiento']) + ', después del inicio de la regata (' + resultados._fecha_aviso(fecha_regata) + '). Revisa la identidad o las fechas.')
                campos = dict(dni=p['documento_propuesto'], nombre=p['nombre_propuesto'],
                    apellidos=p['apellidos_propuestos'], fecha_nacimiento=p['fecha_nacimiento_propuesta'],
                    sexo=p['sexo_propuesto'], id_club=p['id_club_identificado'], rol_propuesto=rol,
                    observaciones_revision=p['observaciones_revision'])
                preparadas.append((ident, campos, r['version'], dni))
            # Ninguna escritura se confirma hasta que se validan todas las filas.
            datos.marcar_en_revision(c,identificador)
            datos.guardar_vinculos_lote(c, [dict(id=ident,dni=dni,rol=campos['rol_propuesto'])
                                          for ident,campos,_,dni in sorted(preparadas)])
            from services import memoria_nombres
            for d in decisiones:
                if d.get('recordar_nombre'):
                    memoria_nombres.guardar(c,propuestas[d['participante']]['participante'],d['dni'],'variante')
            actual = _contenido(c, identificador)
            afectadas = {propuestas[i]['participante']['id_fila'] for i in vistos}
            estados = []
            for f in actual['filas']:
                if f['id_fila'] in afectadas:
                    estado,incidencias = revision.estado_fila(f,resultados.miembros_fila(actual,f),actual['importacion']['numero_tripulantes'])
                    estados.append(dict(id=f['id_fila'],estado=estado,incidencias=incidencias))
                    f.update(estado=estado,incidencias=incidencias)
                if f['id_fila'] in afectadas and actual['importacion']['numero_tripulantes'] == 2:
                    miembros = [p for p in actual['participantes'] if p['id_fila'] == f['id_fila'] and p['dni_deportista_confirmado']]
                    if len(miembros) == 2 and sorted(p['rol_propuesto'] or '' for p in miembros) != ['Patron', 'Tripulante']:
                        raise ValidacionError(resultados.contexto_fila(actual, f) + ': una tripulación completa necesita un patrón y un tripulante. No se guardó el lote.')
            datos.estados_filas_lote(c,estados)
            salida = {'vinculados': len(preparadas), 'resultados_preparados': len(resultados.filas_preparadas(actual))}
            if datos_resultado is not None:
                afectadas = {propuestas[i]['participante']['id_fila'] for i in vistos}
                listas = [f['id_fila'] for f in resultados.filas_preparadas(actual) if f['id_fila'] in afectadas]
                pendientes = []
                for f in actual['filas']:
                    if f['id_fila'] not in afectadas - set(listas):
                        continue
                    miembros = resultados.miembros_fila(actual, f)
                    # Vincular una persona no exige inventar la identidad de su pareja.
                    # Se conserva el vínculo; el resultado espera a completar el equipo.
                    if (len(miembros) == actual['importacion']['numero_tripulantes']
                            and any(not p['dni_deportista_confirmado'] for p in miembros)
                            and f['posicion_general'] is not None and f['puntos'] is not None):
                        pendientes.append(f['id_fila'])
                    else:
                        raise ValidacionError(f"Puesto {f['posicion_general']}: " +
                            ' '.join(resultados.incidencias(actual, f)) + ' No se guardó el lote.')
                salida['resultados_incorporados'] = resultados.incorporar_en_conexion(
                    c, identificador, listas, datos_resultado, resultados.version_resultados(actual)) if listas else 0
                if pendientes:
                    salida['equipos_pendientes'] = len(pendientes)
            return salida
    except IntegrityError:
        raise ConflictoError('No se guardó ninguna vinculación del lote: hay identidades o referencias incompatibles. Actualiza y revisa los datos.') from None


def guardar_en_proveedor(proveedor, operacion, identificador, decisiones, version=None, datos_resultado=None):
    from database.database import crear_engine
    motor = crear_engine(proveedor)
    try:
        if operacion == 'clubes':
            return confirmar_clubes(motor, identificador, decisiones, confirmar=True)
        if operacion == 'vinculos':
            return confirmar_vinculos(motor, identificador, decisiones, version, confirmar=True)
        if operacion == 'vinculos_resultados':
            if datos_resultado is None:
                raise ValidacionError('Completa los datos de la regata antes de incorporar el lote.')
            return confirmar_vinculos(motor, identificador, decisiones, version, confirmar=True,
                                      datos_resultado=datos_resultado)
        if operacion == 'altas_resultados':
            return crear_nuevos(motor, identificador, decisiones, version, datos_resultado, confirmar=True)
        raise ValidacionError('Selecciona una operación de revisión válida.')
    finally:
        motor.dispose()


def crear_nuevos(engine, identificador, decisiones, version, datos_resultado, *, confirmar=False):
    """Altas provisionales conservadoras y sus resultados, sin saltar coincidencias."""
    if confirmar is not True or not isinstance(decisiones, list) or not decisiones:
        raise ValidacionError('Selecciona y confirma las altas revisadas.')
    try:
        with engine.begin() as c:
            contenido = _contenido(c, identificador, True)
            if version != resultados.version_resultados(contenido):
                raise ConflictoError('El borrador cambió. Actualiza antes de crear el lote.')
            resultados._metadatos(datos_resultado)
            fichas, aliases = datos.fichas_revision(c), datos.aliases_revision(c)
            clubes = {cl['id_club']:cl for cl in datos.clubes_revision(c)}
            pendientes = {p['id_participante_importado']: p for p in _pendientes(contenido)}
            # Validar la forma antes de simular, sin confiar en datos de la interfaz.
            for d in decisiones:
                if not isinstance(d, dict) or not {'participante', 'version', 'campos'} <= set(d) or set(d) - {'participante', 'version', 'campos', 'confirmar_distinto_lote'} or not isinstance(d['campos'], dict):
                    raise ValidacionError('Una alta del lote contiene datos no admitidos.')
                base._entero(d['participante'], 'id_participante_importado')
            faltas = incidencias_altas(contenido, decisiones)
            if faltas:
                raise ValidacionError('No se guardó ninguna alta. ' + ' | '.join(faltas.values()))
            fichas_iniciales = list(fichas)
            vistos, afectadas = set(), set()
            for d in decisiones:
                if not isinstance(d, dict) or not {'participante', 'version', 'campos'} <= set(d) or set(d) - {'participante', 'version', 'campos', 'confirmar_distinto_lote'}:
                    raise ValidacionError('Una alta del lote contiene datos no admitidos.')
                ident = base._entero(d['participante'], 'id_participante_importado')
                if ident in vistos or ident not in pendientes:
                    raise ConflictoError('Una alta está repetida o ya no está pendiente.')
                vistos.add(ident)
                p = pendientes[ident]
                campos = d['campos']
                if not isinstance(campos, dict) or set(campos) - (revision._CAMPOS - {'dni'}):
                    raise ValidacionError('Revisa los campos de la nueva ficha.')
                contexto = f"Puesto {p['fila']['posicion_general']} · {p['nombre_original']}: "
                try:
                    revision._validar_campos({**campos, 'dni': 'TEMP-VALIDACION'}, completo=True)
                except ValidacionError as error:
                    raise ValidacionError(contexto + str(error) + ' No se creó ninguna ficha del lote.') from None
                if not campos.get('id_club') or campos['id_club'] != p['id_club_identificado']:
                    raise ValidacionError(contexto + 'Confirma primero el club del participante para crear altas por lotes.')
                # Se vuelven a buscar coincidencias después de cada alta: impide
                # duplicar también dos personas del mismo lote con distinto ID.
                propuesta = {**p, 'nombre_propuesto': campos.get('nombre'), 'apellidos_propuestos': campos.get('apellidos')}
                existentes = revision._candidatos(c, propuesta, fichas=fichas_iniciales, aliases=aliases)
                if existentes:
                    nombres = ', '.join(f['nombre']+' '+f['apellidos'] for f in existentes)
                    raise ConflictoError(f"{campos['nombre']} {campos['apellidos']}: hay fichas existentes similares ({nombres}). Revisa esa persona individualmente; no se creó ninguna ficha del lote.")
                similares_lote = revision._candidatos(c, propuesta, fichas=fichas[len(fichas_iniciales):], aliases=aliases)
                distinto = d.get('confirmar_distinto_lote', False)
                if type(distinto) is not bool:
                    raise ValidacionError('Confirma explícitamente si las altas similares son personas distintas.')
                completo = revision.normalizar(campos['nombre']+' '+campos['apellidos'])
                if any(revision.normalizar(f['nombre']+' '+f['apellidos']) == completo for f in similares_lote):
                    raise ConflictoError(f"{campos['nombre']} {campos['apellidos']}: el mismo nombre aparece en varias altas del lote. Revisa esa identidad individualmente; no se creó ninguna ficha.")
                if similares_lote and distinto is not True:
                    nombres = ', '.join(f['nombre']+' '+f['apellidos'] for f in similares_lote)
                    raise ConflictoError(f"{campos['nombre']} {campos['apellidos']} se parece a otra alta de este lote ({nombres}). Confirma que son personas distintas; no se creó ninguna ficha del lote.")
                dni = revision.guardar_revision_en_conexion(c, ident, 'crear', {**campos, 'dni': None}, d['version'],
                    confirmar_nuevo_distinto=distinto, fichas=fichas,aliases=aliases)
                club = clubes[campos['id_club']]
                fichas.append(dict(campos,dni=dni,club=club['nombre'],id_federacion=club['id_federacion'],federacion=club['federacion']))
                afectadas.add(p['id_fila'])
            actual = _contenido(c, identificador)
            listas = [f['id_fila'] for f in resultados.filas_preparadas(actual) if f['id_fila'] in afectadas]
            if afectadas != set(listas):
                raise ValidacionError('Completa los miembros, roles, puestos y puntos de los equipos del lote. No se guardó ninguna alta.')
            total = resultados.incorporar_en_conexion(c, identificador, listas, datos_resultado,
                                                     resultados.version_resultados(actual))
            return {'creados': len(vistos), 'resultados_incorporados': total}
    except IntegrityError:
        raise ConflictoError('No se creó ninguna ficha del lote: hay documentos o referencias incompatibles. Actualiza los datos.') from None
