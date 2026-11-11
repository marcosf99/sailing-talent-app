"""Borradores y revisión de clasificaciones, independientes de Streamlit y proveedor.

Entrada: filas ya normalizadas por la futura vista previa/extracción. Se conserva
la fuente original; no se crean deportistas, unidades ni resultados definitivos.
Cada escritura bloquea su importación y se realiza en una única transacción.
"""
import hashlib
import json
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from sqlalchemy.exc import IntegrityError

from database import importaciones as datos
from services.deportistas import ConflictoError, ValidacionError


NIVELES = ("Autonomico", "Nacional", "Internacional")
_EDITABLES = ("recibida", "extraida", "en_revision", "parcialmente_importada")
_PARTICIPANTE = (
    "nombre_original", "nombre_propuesto", "apellidos_propuestos", "documento_propuesto",
    "fecha_nacimiento_propuesta", "sexo_propuesto", "club_original", "federacion_original",
    "id_club_identificado", "rol_propuesto", "observaciones_revision",
)


def _texto(valor, campo, maximo=None, obligatorio=False):
    if valor is None and not obligatorio:
        return None
    if not isinstance(valor, str):
        raise ValidacionError(f"{campo}: debe ser texto.")
    valor = valor.strip()
    if obligatorio and not valor:
        raise ValidacionError(f"{campo}: es obligatorio.")
    if maximo and len(valor) > maximo:
        raise ValidacionError(f"{campo}: admite hasta {maximo} caracteres.")
    return valor or None


def _entero(valor, campo, opcional=False, maximo=2147483647):
    if valor is None and opcional:
        return None
    if type(valor) is not int or not 1 <= valor <= maximo:
        raise ValidacionError(f"{campo}: debe ser un entero positivo.")
    return valor


def _fecha(valor, campo):
    if valor is not None and type(valor) is not date:
        raise ValidacionError(f"{campo}: debe ser una fecha, sin hora.")
    return valor


def _objeto(valor, campo):
    if not isinstance(valor, dict):
        raise ValidacionError(f"{campo}: debe ser un objeto JSON.")
    try:
        # Copia independiente: no mutar los datos originales al preparar la revisión.
        return json.loads(json.dumps(valor, ensure_ascii=False, allow_nan=False))
    except (ValueError, TypeError, OverflowError):
        raise ValidacionError(f"{campo}: contiene valores que no se pueden guardar como JSON.") from None


def _nivel(valor):
    if valor == "Autonómico":
        valor = "Autonomico"
    if valor not in NIVELES:
        raise ValidacionError("Selecciona nivel Autonomico, Nacional o Internacional.")
    return valor


def _puntos(valor):
    if valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, (str, int, float, Decimal)):
        raise ValidacionError("Los puntos deben ser un número no negativo.")
    try:
        # Admite la coma decimal; no interpreta separadores de miles ambiguos.
        puntos = Decimal(str(valor).strip().replace(',', '.'))
        if not puntos.is_finite() or not 0 <= puntos <= Decimal('99999999.99'):
            raise ValueError
        if puntos != puntos.quantize(Decimal('0.01')):
            raise ValueError
        return puntos
    except (InvalidOperation, ValueError):
        raise ValidacionError("Los puntos deben ser finitos, no negativos y tener hasta dos decimales.") from None


def calcular_huella(contenido):
    """SHA-256 de la copia de la fuente; no lee archivos ni descarga enlaces."""
    if not isinstance(contenido, bytes) or not contenido:
        raise ValidacionError("El documento está vacío o no contiene bytes válidos.")
    return hashlib.sha256(contenido).hexdigest()


def criterio_inclusion(nivel):
    nivel = _nivel(nivel)
    return {"version": 1, "nivel": nivel, "incluir_empates": True,
            "posicion_maxima": {"Autonomico": 40, "Nacional": 80}.get(nivel),
            "codigo_pais_vela": "ESP" if nivel == "Internacional" else None}


def evaluar_seleccion(nivel, posicion_general=None, numero_vela=None):
    """Devuelve TRUE/FALSE/NULL; NULL exige revisión y no significa excluido.

    ESP se busca como código, admitiendo ESP123 y ESP-123, sin aceptar DESP o
    ESPECIAL. El criterio es de la embarcación, no de cada miembro del equipo.
    """
    nivel = _nivel(nivel)
    posicion = _entero(posicion_general, "posicion_general", opcional=True)
    vela = _texto(numero_vela, "numero_vela", 100)
    if nivel == "Internacional":
        if vela is None:
            return {"cumple_criterio": None, "motivo_seleccion": "Falta el número de vela para comprobar ESP."}
        esp = re.search(r"(?<![A-Z])ESP(?![A-Z])", vela.upper()) is not None
        return {"cumple_criterio": esp, "motivo_seleccion":
                "ESP en el número de vela: se selecciona toda la tripulación." if esp
                else "El número de vela no contiene el código ESP."}
    if posicion is None:
        return {"cumple_criterio": None, "motivo_seleccion": "Falta confirmar la posición general."}
    corte = 40 if nivel == "Autonomico" else 80
    return {"cumple_criterio": posicion <= corte,
            "motivo_seleccion": f"Posición {posicion}; corte hasta {corte}, incluidos los empates."}


def validar_importacion(campos):
    if not isinstance(campos, dict):
        raise ValidacionError("Los datos de la importación deben ser un diccionario.")
    admitidos = set(datos.CAMPOS_IMPORTACION) - {'criterio_inclusion'}
    if set(campos) - admitidos:
        raise ValidacionError("La importación contiene campos desconocidos o estados que no se pueden fijar manualmente.")
    salida = {}
    for campo, maximo in (
        ('tipo_fuente', 10), ('nombre_archivo', None), ('url_origen', None),
        ('referencia_documento', None), ('huella_documento', 64),
        ('nombre_competicion_propuesto', 200), ('localidad_propuesta', 100),
        ('observaciones', None),
    ):
        salida[campo] = _texto(campos.get(campo), campo, maximo,
                               campo in ('tipo_fuente', 'referencia_documento', 'huella_documento'))
    if salida['tipo_fuente'] not in ('pdf', 'enlace'):
        raise ValidacionError("La fuente debe ser pdf o enlace.")
    if salida['tipo_fuente'] == 'pdf' and salida['nombre_archivo'] is None:
        raise ValidacionError("Indica el nombre del PDF.")
    if salida['tipo_fuente'] == 'enlace' and not salida['url_origen']:
        raise ValidacionError("Indica el enlace de origen.")
    if salida['url_origen']:
        try:
            url = urlsplit(salida['url_origen'])
            valida = url.scheme in ('http', 'https') and bool(url.hostname) and not url.username
        except ValueError:
            valida = False
        if not valida:
            raise ValidacionError("El enlace debe ser HTTP o HTTPS, sin credenciales incrustadas.")
    if not re.fullmatch(r'[0-9a-f]{64}', salida['huella_documento']):
        raise ValidacionError("La huella debe ser SHA-256 en hexadecimal minúsculo.")
    for campo in ('fecha_inicio_propuesta', 'fecha_fin_propuesta'):
        salida[campo] = _fecha(campos.get(campo), campo)
    if (salida['fecha_inicio_propuesta'] and salida['fecha_fin_propuesta']
            and salida['fecha_fin_propuesta'] < salida['fecha_inicio_propuesta']):
        raise ValidacionError("La fecha final no puede ser anterior a la inicial.")
    actualizado = campos.get('fecha_actualizacion_fuente')
    if actualizado is not None and (not isinstance(actualizado, datetime)
                                   or actualizado.utcoffset() is None):
        raise ValidacionError("La actualización de la fuente debe incluir fecha, hora y zona horaria.")
    salida['fecha_actualizacion_fuente'] = actualizado
    salida['id_clase'] = _entero(campos.get('id_clase'), 'id_clase')
    salida['id_competicion'] = _entero(campos.get('id_competicion'), 'id_competicion', True)
    salida['nivel'] = _nivel(campos['nivel']) if campos.get('nivel') is not None else None
    tipo = campos.get('tipo_clasificacion', 'sin_confirmar')
    if tipo not in ('sin_confirmar', 'provisional', 'definitiva'):
        raise ValidacionError("Indica si la clasificación es provisional, definitiva o sin confirmar.")
    salida['tipo_clasificacion'] = tipo
    salida['mapeo_columnas'] = _objeto(campos.get('mapeo_columnas', {}), 'mapeo_columnas')
    salida['criterio_inclusion'] = criterio_inclusion(salida['nivel']) if salida['nivel'] else None
    return salida


def _validar_participante(campos, orden):
    if not isinstance(campos, dict) or set(campos) - set(_PARTICIPANTE):
        raise ValidacionError("El participante contiene campos desconocidos; la identidad se confirma por separado.")
    salida = {campo: _texto(campos.get(campo), campo, maximo, campo == 'nombre_original')
              for campo, maximo in (
                  ('nombre_original', None), ('nombre_propuesto', 100), ('apellidos_propuestos', 150),
                  ('documento_propuesto', 20), ('club_original', None), ('federacion_original', None),
                  ('observaciones_revision', None),
              )}
    salida['fecha_nacimiento_propuesta'] = _fecha(campos.get('fecha_nacimiento_propuesta'), 'fecha_nacimiento_propuesta')
    nacimiento = salida['fecha_nacimiento_propuesta']
    if nacimiento and nacimiento > date.today():
        raise ValidacionError("La fecha de nacimiento propuesta no puede ser futura.")
    for campo, opciones in (('sexo_propuesto', ('Masculino', 'Femenino')),
                           ('rol_propuesto', ('Patron', 'Tripulante'))):
        valor = campos.get(campo)
        if valor is not None and valor not in opciones:
            raise ValidacionError(f"{campo}: valor no admitido.")
        salida[campo] = valor
    salida['id_club_identificado'] = _entero(campos.get('id_club_identificado'), 'id_club_identificado', True)
    salida.update(orden_en_tripulacion=orden, estado='pendiente_revision')
    return salida


def preparar_filas(filas, nivel, numero_tripulantes):
    """Normaliza la entrada sin modificarla ni descartar filas de la fuente."""
    nivel = _nivel(nivel)
    _entero(numero_tripulantes, 'numero_tripulantes', maximo=32767)
    if not isinstance(filas, list) or not filas or len(filas) > 10000:
        raise ValidacionError("Proporciona entre 1 y 10000 filas de la clasificación.")
    salida, numeros = [], set()
    permitidos = set(datos.CAMPOS_FILA) - {
        'id_importacion', 'cumple_criterio', 'motivo_seleccion', 'estado', 'incidencias',
    }
    for indice, fila in enumerate(filas, 1):
        if not isinstance(fila, dict) or set(fila) - (permitidos | {'participantes'}):
            raise ValidacionError(f"Fila {indice}: contiene campos no admitidos.")
        numero = _entero(fila.get('numero_fila', indice), 'numero_fila')
        if numero in numeros:
            raise ValidacionError(f"El número de fila {numero} está repetido.")
        numeros.add(numero)
        datos_fila = {'numero_fila': numero,
                      'pagina_origen': _entero(fila.get('pagina_origen'), 'pagina_origen', True),
                      'datos_originales': _objeto(fila.get('datos_originales'), 'datos_originales'),
                      'posicion_general': _entero(fila.get('posicion_general'), 'posicion_general', True),
                      'posicion_categoria': _entero(fila.get('posicion_categoria'), 'posicion_categoria', True),
                      'puntos': _puntos(fila.get('puntos'))}
        for campo, maximo in (('numero_vela_original', 100), ('codigo_pais_vela', 3),
                              ('categoria_original', 100), ('observaciones_revision', None)):
            datos_fila[campo] = _texto(fila.get(campo), campo, maximo)
        pais = datos_fila['codigo_pais_vela']
        if pais is not None and not re.fullmatch('[A-Z]{3}', pais):
            raise ValidacionError("El código de país debe tener tres letras mayúsculas.")
        # El código de una columna separada nunca sustituye el ESP del número de vela.
        seleccion = evaluar_seleccion(nivel, datos_fila['posicion_general'], datos_fila['numero_vela_original'])
        miembros = fila.get('participantes', [])
        if not isinstance(miembros, list) or len(miembros) > 32767:
            raise ValidacionError("La tripulación debe ser una lista válida.")
        participantes = [_validar_participante(p, n) for n, p in enumerate(miembros, 1)]
        incidencias = []
        if seleccion['cumple_criterio'] is None:
            incidencias.append(seleccion['motivo_seleccion'])
        if datos_fila['posicion_general'] is None:
            incidencias.append('Falta la posición general.')
        if datos_fila['puntos'] is None:
            incidencias.append('Falta la puntuación.')
        if len(participantes) != numero_tripulantes:
            incidencias.append(f'Se esperaban {numero_tripulantes} tripulantes; hay {len(participantes)}.')
        estado = 'excluida' if seleccion['cumple_criterio'] is False else (
            'requiere_correccion' if incidencias else 'pendiente')
        datos_fila.update(seleccion, estado=estado, incidencias=' '.join(incidencias) or None)
        salida.append({'fila': datos_fila, 'participantes': participantes})
    return salida


def _referencias(conexion, campos):
    clase = datos.referencia_clase(conexion, campos['id_clase'])
    if clase is None:
        raise ValidacionError("La clase seleccionada ya no existe.")
    if campos['id_competicion'] is not None:
        competicion = datos.referencia_competicion(conexion, campos['id_competicion'])
        if competicion is None or competicion['id_clase'] != campos['id_clase']:
            raise ValidacionError("La competición no existe o pertenece a otra clase.")
        if competicion['nivel'] and campos['nivel'] and competicion['nivel'] != campos['nivel']:
            raise ValidacionError("El nivel no coincide con el de la competición seleccionada.")
    return clase


def _editable(conexion, identificador):
    _entero(identificador, 'id_importacion')
    imp = datos.obtener_importacion(conexion, identificador, bloquear=True)
    if imp is None:
        raise ValidacionError("La importación no existe.")
    if imp['estado'] not in _EDITABLES:
        raise ConflictoError("Esta importación ya no admite cambios de borrador.")
    return imp


def _guardar_filas(conexion, imp, filas):
    if datos.listar_filas(conexion, imp['id_importacion']):
        raise ConflictoError("La importación ya tiene filas. No se sobrescribe una revisión existente.")
    preparadas = preparar_filas(filas, imp['nivel'], imp['numero_tripulantes'])
    for item in preparadas:
        fila = dict(item['fila'], id_importacion=imp['id_importacion'])
        id_fila = datos.insertar(conexion, 'fila_clasificacion_importada', fila)
        for participante in item['participantes']:
            datos.insertar(conexion, 'participante_importado', dict(participante, id_fila=id_fila))
    datos.marcar_en_revision(conexion, imp['id_importacion'])
    return len(preparadas)


def crear_borrador(engine, campos, filas=None):
    """Crea la importación y, opcionalmente, todas sus filas en la misma transacción."""
    campos = validar_importacion(campos)
    try:
        with engine.begin() as conexion:
            clase = _referencias(conexion, campos)
            identificador = datos.insertar(conexion, 'importacion_clasificacion', campos)
            if filas is not None:
                _guardar_filas(conexion, {**campos, **clase, 'id_importacion': identificador}, filas)
    except IntegrityError:
        raise ConflictoError("No se guardó la importación: hay datos duplicados o referencias que han cambiado.") from None
    return identificador


def guardar_filas(engine, identificador, filas):
    try:
        with engine.begin() as conexion:
            return _guardar_filas(conexion, _editable(conexion, identificador), filas)
    except IntegrityError:
        raise ConflictoError("No se guardaron las filas: hay duplicados o referencias que han cambiado.") from None


def obtener_borrador(engine, identificador):
    _entero(identificador, 'id_importacion')
    with engine.connect() as conexion:
        imp = datos.obtener_importacion(conexion, identificador)
        if imp is None:
            return None
        return {'importacion': imp, 'filas': datos.listar_filas(conexion, identificador),
                'participantes': datos.listar_participantes(conexion, identificador),
                'coincidencias': datos.listar_coincidencias(conexion, identificador)}


def listar_borradores(engine, limite=50, desplazamiento=0):
    if type(limite) is not int or not 1 <= limite <= 200:
        raise ValidacionError("El límite debe estar entre 1 y 200.")
    if type(desplazamiento) is not int or desplazamiento < 0:
        raise ValidacionError("El desplazamiento debe ser un entero no negativo.")
    with engine.connect() as conexion:
        return datos.listar_importaciones(conexion, limite, desplazamiento)


def _bloquear_participante(conexion, identificador):
    _entero(identificador, 'id_participante_importado')
    p = datos.contexto_participante(conexion, identificador)
    if p is None:
        raise ValidacionError("El participante no existe.")
    _editable(conexion, p['id_importacion'])
    # Volver a leer después del bloqueo para no trabajar con una identidad antigua.
    p = datos.contexto_participante(conexion, identificador)
    if p is None or p['estado_fila'] in ('importada', 'excluida') or not p['cumple_criterio']:
        raise ValidacionError("Solo se pueden revisar participantes de filas seleccionadas y pendientes.")
    return p


def proponer_coincidencias(engine, participante, candidatos):
    """Guarda sugerencias ya calculadas; ninguna confirma una identidad."""
    if not isinstance(candidatos, list) or not candidatos:
        raise ValidacionError("Proporciona una lista de candidatos.")
    preparados, vistos = [], set()
    for candidato in candidatos:
        if not isinstance(candidato, dict) or set(candidato) - {'dni_deportista', 'indice_similitud', 'motivos'}:
            raise ValidacionError("El candidato contiene campos no admitidos.")
        dni = _texto(candidato.get('dni_deportista'), 'dni_deportista', 20, True).upper()
        indice = candidato.get('indice_similitud')
        try:
            if isinstance(indice, bool):
                raise ValueError
            indice = None if indice is None else Decimal(str(indice))
            if indice is not None and (not indice.is_finite() or not 0 <= indice <= 1
                                       or indice != indice.quantize(Decimal('0.00001'))):
                raise ValueError
        except (InvalidOperation, ValueError):
            raise ValidacionError("La similitud debe estar entre 0 y 1 y admitir hasta cinco decimales.") from None
        if dni in vistos:
            raise ValidacionError("Hay candidatos repetidos.")
        vistos.add(dni)
        preparados.append({'id_participante_importado': participante, 'dni_deportista': dni,
                            'indice_similitud': indice,
                            'motivos': _texto(candidato.get('motivos'), 'motivos')})
    try:
        with engine.begin() as conexion:
            p = _bloquear_participante(conexion, participante)
            if p['dni_deportista_confirmado']:
                raise ConflictoError("La identidad ya está confirmada; no se añaden sugerencias.")
            for candidato in preparados:
                if not datos.existe_deportista(conexion, candidato['dni_deportista']):
                    raise ValidacionError("Uno de los deportistas propuestos ya no existe.")
                datos.insertar(conexion, 'coincidencia_propuesta', candidato)
    except IntegrityError:
        raise ConflictoError("No se guardaron las propuestas: ya existen o sus referencias han cambiado.") from None
    return len(preparados)


def vincular_participante(engine, participante, dni, documento_anterior=None):
    """Confirmación explícita de una ficha existente, con control de edición concurrente.

    documento_anterior es la identidad que vio la interfaz (None si estaba pendiente).
    No crea fichas ni cambia el club, nombre o fecha de nacimiento del deportista.
    """
    dni = _texto(dni, 'dni_deportista', 20, True).upper()
    try:
        with engine.begin() as conexion:
            p = _bloquear_participante(conexion, participante)
            if p['dni_deportista_confirmado'] != documento_anterior:
                raise ConflictoError("La identidad cambió desde que abriste la revisión. Recarga los datos.")
            if not datos.existe_deportista(conexion, dni):
                raise ValidacionError("El deportista seleccionado ya no existe.")
            datos.confirmar_identidad(conexion, participante, dni)
    except IntegrityError:
        raise ConflictoError("No se vinculó el participante: ese deportista ya está en la fila o sus datos han cambiado.") from None
    return dni


def registrar_alias_club(engine, texto_alias, id_club, contexto_fuente=None):
    alias = _texto(texto_alias, 'texto_alias', 250, True)
    club = _entero(id_club, 'id_club')
    contexto = _texto(contexto_fuente, 'contexto_fuente', 250)
    # No requiere extensiones de PostgreSQL. El mismo resultado sirve en ambos proveedores.
    limpio = ''.join(c for c in unicodedata.normalize('NFKD', alias) if not unicodedata.combining(c))
    normalizado = ' '.join(re.sub(r'[\W_]+', ' ', limpio.casefold()).split())
    if not normalizado:
        raise ValidacionError("El alias debe contener letras o números.")
    _texto(normalizado, 'texto_normalizado', 250, True)
    try:
        with engine.begin() as conexion:
            if not datos.existe_club(conexion, club):
                raise ValidacionError("El club seleccionado ya no existe.")
            return datos.insertar(conexion, 'alias_club', {
                'texto_alias': alias, 'texto_normalizado': normalizado,
                'id_club': club, 'contexto_fuente': contexto,
            })
    except IntegrityError:
        raise ConflictoError("Ese alias ya está registrado en el mismo contexto. Revisa el club antes de continuar.") from None


def actualizar_borrador(engine, identificador, campos, actualizado_en):
    """Completa metadatos antes de cargar filas; mantiene intacta la fuente original."""
    validados = validar_importacion(campos)
    try:
        with engine.begin() as conexion:
            imp = _editable(conexion, identificador)
            if imp['actualizado_en'] != actualizado_en:
                raise ConflictoError("El borrador cambió desde que lo abriste. Recarga los datos.")
            if datos.listar_filas(conexion, identificador):
                raise ConflictoError("No se puede cambiar la configuración después de guardar filas.")
            for campo in ('tipo_fuente', 'nombre_archivo', 'url_origen', 'referencia_documento', 'huella_documento'):
                if validados[campo] != imp[campo]:
                    raise ValidacionError("La fuente original no se puede reemplazar; crea otra importación.")
            _referencias(conexion, validados)
            datos.actualizar_importacion(conexion, identificador, validados)
    except IntegrityError:
        raise ConflictoError("No se actualizó el borrador porque sus referencias han cambiado.") from None
    return identificador
