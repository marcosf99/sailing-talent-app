"""PDF -> tabla de texto revisable -> filas normalizadas. Sin red ni base de datos.

La detección usa las posiciones de los encabezados y de la columna inicial de
puestos. No pretende interpretar cualquier PDF ni hacer OCR. La selección final
de columnas y la revisión de nombres corresponden al usuario.
"""
from bisect import bisect_right
from decimal import Decimal, InvalidOperation
from io import BytesIO
from statistics import median
import re
import unicodedata

from services.deportistas import ValidacionError
from services.importaciones import calcular_huella

MAX_BYTES = 20 * 1024 * 1024
MAX_PAGINAS = 50


def _normalizar(texto):
    return ''.join(c for c in unicodedata.normalize('NFKD', texto.casefold())
                   if not unicodedata.combining(c)).strip(' .:')


def validar_pdf(contenido):
    if not isinstance(contenido, bytes) or not contenido or len(contenido) > MAX_BYTES:
        raise ValidacionError('Selecciona un PDF de hasta 20 MB.')
    if not contenido.lstrip().startswith(b'%PDF-'):
        raise ValidacionError('El archivo no tiene una cabecera PDF válida.')


def _lineas(palabras, tolerancia=2):
    lineas = []
    for palabra in sorted(palabras, key=lambda p: (p['top'], p['x0'])):
        if not lineas or abs(palabra['top'] - lineas[-1][0]['top']) > tolerancia:
            lineas.append([palabra])
        else:
            lineas[-1].append(palabra)
    return [sorted(linea, key=lambda p: p['x0']) for linea in lineas]


def _encabezado(palabras):
    for linea in _lineas(palabras):
        etiquetas = [_normalizar(p['text']) for p in linea]
        if not any(e in ('pos', 'rank', 'puesto') for e in etiquetas):
            continue
        if not any(e in ('barco', 'sail', 'vela', 'sail#') for e in etiquetas):
            continue
        if len(linea) < 4:
            continue
        unidos = []
        for palabra in linea:
            if unidos and palabra['text'] in ('#', '/'):
                unidos[-1]['text'] += ' ' + palabra['text']
                unidos[-1]['x1'] = palabra['x1']
            elif unidos and unidos[-1]['text'].endswith('/'):
                unidos[-1]['text'] += ' ' + palabra['text']
                unidos[-1]['x1'] = palabra['x1']
            else:
                unidos.append(dict(palabra))
        return unidos
    return None


def _columnas(encabezado, ancho):
    columnas = []
    for i, palabra in enumerate(encabezado):
        centro = (palabra['x0'] + palabra['x1']) / 2
        anterior = encabezado[i - 1] if i else None
        previo_numerico = anterior and (_normalizar(anterior['text']).isdigit()
                                        or _normalizar(anterior['text']) in ('total', 'net', 'puntos'))
        if previo_numerico or palabra['text'].isdigit():
            limite = (((anterior['x0'] + anterior['x1']) / 2) + centro) / 2
        else:
            limite = palabra['x0'] - (15 if i == 0 else 6)
        columnas.append({'id': f'c{i}', 'nombre': palabra['text'],
                         'inicio': max(0, limite / ancho)})
    if any(a['inicio'] >= b['inicio'] for a, b in zip(columnas, columnas[1:])):
        raise ValidacionError('Los encabezados se solapan. Este documento necesita preparación manual.')
    return columnas


def _reglas_horizontales(pagina):
    # Unir segmentos a la misma altura; las tablas pueden dibujar cada celda aparte.
    grupos = {}
    for e in pagina.edges:
        if e.get('orientation') == 'h' and e['x1'] > e['x0']:
            grupos.setdefault(round(e['top'], 1), []).append((e['x0'], e['x1']))
    reglas = []
    for altura, intervalos in grupos.items():
        fin, cobertura = -1, 0
        for inicio, final in sorted(intervalos):
            cobertura += max(0, final - max(inicio, fin))
            fin = max(fin, final)
        if cobertura > pagina.width * .65:
            reglas.append(altura)
    return sorted(reglas)


def _texto_celda(palabras):
    return '\n'.join(' '.join(p['text'] for p in linea) for linea in _lineas(palabras))


def extraer_pdf(contenido):
    validar_pdf(contenido)
    import pdfplumber
    resultado = {'columnas': [], 'filas': [], 'avisos': [], 'paginas': [],
                 'huella': calcular_huella(contenido), 'clase_detectada': None}
    try:
        with pdfplumber.open(BytesIO(contenido)) as pdf:
            if not 1 <= len(pdf.pages) <= MAX_PAGINAS:
                raise ValidacionError('El documento debe tener entre 1 y 50 páginas.')
            for numero, pagina in enumerate(pdf.pages, 1):
                if pagina.width > 3000 or pagina.height > 3000 or min(pagina.width, pagina.height) <= 0:
                    raise ValidacionError('El tamaño de página no es compatible con esta vista previa.')
                if len(pagina.chars) > 200000:
                    raise ValidacionError('La página contiene demasiado texto para analizarla con seguridad.')
                palabras = pagina.dedupe_chars().extract_words(x_tolerance=1, y_tolerance=2)
                encabezado = _encabezado(palabras)
                if not resultado['columnas']:
                    if encabezado is None:
                        resultado['avisos'].append(f'Página {numero}: no se encontró un encabezado de clasificación.')
                        resultado['paginas'].append({'pagina': numero, 'filas': 0})
                        continue
                    resultado['columnas'] = _columnas(encabezado, pagina.width)
                    texto = pagina.extract_text() or ''
                    clase = re.search(r'(?:Clase|Class)\s*:?\s+([^\n]+)', texto, re.I)
                    if clase:
                        resultado['clase_detectada'] = clase.group(1).split('RACE')[0].strip()
                elif encabezado and [p['text'] for p in encabezado] != [c['nombre'] for c in resultado['columnas']]:
                    raise ValidacionError(f'La página {numero} cambia de estructura. Separa las clasificaciones antes de cargarlas.')
                limites = [c['inicio'] * pagina.width for c in resultado['columnas']]
                desde = max(p['bottom'] for p in encabezado) if encabezado else 0
                candidatos = [p for p in palabras if p['top'] >= desde
                              and limites[0] <= (p['x0'] + p['x1']) / 2 < limites[1]
                              and re.fullmatch(r'=?\d{1,5}[ºª=]?|DNC|DNF|DNS|RET|DSQ|BFD|UFD|DNE|OCS', p['text'], re.I)]
                candidatos.sort(key=lambda p: p['top'])
                # Evitar contar un número de pie de página como participante: debe
                # existir texto en la columna de vela a una altura próxima.
                anclas = [p for p in candidatos if any(
                    limites[1] <= (w['x0'] + w['x1']) / 2 < limites[2]
                    and abs(w['top'] - p['top']) < 12 for w in palabras)]
                if not anclas:
                    resultado['avisos'].append(f'Página {numero}: no se identificaron filas. Revisa si contiene una continuación o una imagen escaneada.')
                    resultado['paginas'].append({'pagina': numero, 'filas': 0})
                    continue
                centros = [(p['top'] + p['bottom']) / 2 for p in anclas]
                paso = median([b - a for a, b in zip(centros, centros[1:])]) if len(centros) > 1 else 30
                reglas = _reglas_horizontales(pagina)
                cortes = []
                for j, centro in enumerate(centros):
                    anterior = centros[j - 1] if j else max(desde, centro - paso)
                    entre = [r for r in reglas if anterior < r < centro]
                    cortes.append(min(entre, key=lambda r: abs(r - (anterior + centro) / 2))
                                  if entre else (anterior + centro) / 2)
                despues = [r for r in reglas if centros[-1] < r < centros[-1] + paso]
                cortes.append(min(despues) if despues else min(pagina.height, centros[-1] + paso / 2))
                for j, ancla in enumerate(anclas):
                    celdas = {c['id']: [] for c in resultado['columnas']}
                    for palabra in palabras:
                        y = (palabra['top'] + palabra['bottom']) / 2
                        if not cortes[j] <= y < cortes[j + 1]:
                            continue
                        indice = bisect_right(limites, (palabra['x0'] + palabra['x1']) / 2) - 1
                        if indice >= 0:
                            celdas[resultado['columnas'][indice]['id']].append(palabra)
                    celdas = {campo: _texto_celda(valor) for campo, valor in celdas.items()}
                    resultado['filas'].append({'numero_fila': len(resultado['filas']) + 1,
                                               'pagina_origen': numero, 'celdas': celdas})
                resultado['paginas'].append({'pagina': numero, 'filas': len(anclas)})
            if not resultado['filas']:
                raise ValidacionError('No se pudo extraer una clasificación. Se requiere un PDF con texto seleccionable y columnas de posición y vela; los escaneados necesitan OCR previo.')
    except ValidacionError:
        raise
    except Exception:
        # Bibliotecas PDF pueden emitir varias familias de errores en archivos dañados.
        raise ValidacionError('No se pudo leer el PDF. Comprueba que no esté dañado ni protegido con contraseña.') from None
    resultado['avisos'].append('La extracción es una propuesta: compara filas, nombres y puntuaciones con las páginas originales antes de guardar.')
    if any('crew' in _normalizar(c['nombre']) for c in resultado['columnas']):
        resultado['avisos'].append('La columna Crew / Club mezcla nombres y clubes y puede presentar texto superpuesto. Revisa cada miembro manualmente.')
    return resultado


def sugerir_mapeo(columnas):
    """Solo sugerencias visibles; la interfaz debe exigir confirmación."""
    def buscar(opciones):
        return next((c['id'] for c in columnas if _normalizar(c['nombre']) in opciones), None)
    return {'posicion_general': buscar(('pos', 'rank', 'puesto')),
            'puntos': buscar(('net',)) or buscar(('puntos', 'total')),
            'numero_vela_original': buscar(('barco', 'sail #', 'sail#', 'vela')),
            'participantes': buscar(('patron', 'crew / club', 'nombre', 'tripulacion')),
            'categoria_original': buscar(('cat', 'categoria'))}


def convertir_posicion(valor):
    texto = str(valor or '').strip()
    if not re.fullmatch(r'=?\s*\d+\s*[ºª.=]?', texto):
        return None
    numero = int(re.search(r'\d+', texto).group())
    return numero if 0 < numero <= 2147483647 else None


def convertir_puntos(valor):
    try:
        numero = Decimal(str(valor).strip().replace(',', '.'))
        if (not numero.is_finite() or not 0 <= numero <= Decimal('99999999.99')
                or numero != numero.quantize(Decimal('.01'))):
            return None
        return numero
    except (InvalidOperation, ValueError):
        return None


def mapear_filas(extraccion, mapeo, modo_nombres='manual'):
    """Conserva celdas originales y convierte solo las columnas elegidas.

    nombre_club: elección explícita para individuales (primera línea nombre,
    siguientes líneas club). manual: no divide nombres ni tripulaciones.
    """
    ids = {c['id'] for c in extraccion['columnas']}
    permitidos = {'posicion_general', 'puntos', 'numero_vela_original', 'participantes', 'categoria_original'}
    if not isinstance(mapeo, dict) or set(mapeo) - permitidos:
        raise ValidacionError('El mapeo contiene campos no admitidos.')
    if any(valor is not None and valor not in ids for valor in mapeo.values()):
        raise ValidacionError('Una de las columnas seleccionadas ya no existe.')
    if not mapeo.get('posicion_general') or not mapeo.get('puntos'):
        raise ValidacionError('Selecciona las columnas de posición general y puntos.')
    if mapeo['posicion_general'] == mapeo['puntos']:
        raise ValidacionError('Posición general y puntos deben ser columnas distintas.')
    if modo_nombres not in ('manual', 'nombre_club'):
        raise ValidacionError('Selecciona un modo válido para revisar los nombres.')
    salida = []
    for fuente in extraccion['filas']:
        def valor(campo):
            return fuente['celdas'].get(mapeo.get(campo), '')
        miembros = []
        lineas = [l.strip() for l in valor('participantes').splitlines() if l.strip()]
        if modo_nombres == 'nombre_club' and lineas:
            miembros.append({'nombre_original': lineas[0], 'club_original': ' '.join(lineas[1:]) or None})
        salida.append({'numero_fila': fuente['numero_fila'], 'pagina_origen': fuente['pagina_origen'],
                       'datos_originales': {'columnas': {c['id']: c['nombre'] for c in extraccion['columnas']},
                                           'celdas': dict(fuente['celdas'])},
                       'posicion_general': convertir_posicion(valor('posicion_general')),
                       'puntos': convertir_puntos(valor('puntos')),
                       'numero_vela_original': valor('numero_vela_original').replace('\n', ' ').strip() or None,
                       'categoria_original': valor('categoria_original').strip() or None,
                       'participantes': miembros})
    return salida


def renderizar_pagina(contenido, numero):
    validar_pdf(contenido)
    import pdfplumber
    if type(numero) is not int or numero < 1:
        raise ValidacionError('Selecciona una página válida.')
    try:
        with pdfplumber.open(BytesIO(contenido)) as pdf:
            if numero > min(len(pdf.pages), MAX_PAGINAS):
                raise ValidacionError('Esa página no existe.')
            p = pdf.pages[numero - 1]
            if p.width > 3000 or p.height > 3000:
                raise ValidacionError('La página es demasiado grande para la vista previa.')
            imagen = p.to_image(resolution=110).original
            destino = BytesIO()
            imagen.save(destino, format='PNG')
            return destino.getvalue()
    except ValidacionError:
        raise
    except Exception:
        raise ValidacionError('No se pudo mostrar la página original.') from None
