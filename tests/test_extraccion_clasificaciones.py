"""PDF sintéticos generados en memoria; sin documentos personales en el repositorio."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from services import extraccion_clasificaciones as e
from services import documentos_importacion as d
from services.deportistas import ValidacionError


def crear_pdf(paginas, encabezados=None, encabezados_continuados=None):
    """PDF mínimo con fuente estándar y texto posicionado, sin otra dependencia."""
    encabezados = encabezados or [(20, 'Pos'), (80, 'Barco'), (180, 'Patron'),
                                  (300, 'Cat'), (360, '1'), (420, 'TOTAL'), (500, 'NET'), (555, 'Pos')]
    objetos = [b'<< /Type /Catalog /Pages 2 0 R >>', b'', b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    indices = []
    for indice, filas in enumerate(paginas):
        page_id = len(objetos) + 1
        indices.append(page_id)
        contenido = []
        def texto(x, y, valor):
            valor = str(valor).replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
            contenido.append(f'BT /F1 10 Tf 1 0 0 1 {x} {y} Tm ({valor}) Tj ET')
        if indice == 0 or encabezados_continuados is not None:
            texto(20, 460, 'Clase Optimist')
            for x, nombre in (encabezados if indice == 0 else encabezados_continuados):
                texto(x, 420, nombre)
        for i, fila in enumerate(filas):
            y = 380 - i * 40
            for x, valor in zip([20, 80, 180, 300, 360, 420, 500, 555], fila):
                if '\n' in str(valor):
                    for j, linea in enumerate(str(valor).splitlines()):
                        texto(x, y + 8 - j * 12, linea)
                else:
                    texto(x, y, valor)
            contenido.append(f'10 {y+20} m 590 {y+20} l S')
        if filas:
            contenido.append(f'10 {y-20} m 590 {y-20} l S')
        texto(20, 20, indice + 1)  # Pie de página que no es una fila.
        contenido = '\n'.join(contenido).encode('latin1')
        objetos.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 500] /Resources << /Font << /F1 3 0 R >> >> /Contents {page_id+1} 0 R >>'.encode())
        objetos.append(f'<< /Length {len(contenido)} >>\nstream\n'.encode() + contenido + b'\nendstream')
    objetos[1] = f'<< /Type /Pages /Count {len(indices)} /Kids [ {" ".join(str(i)+" 0 R" for i in indices)} ] >>'.encode()
    pdf = bytearray(b'%PDF-1.4\n'); offsets = [0]
    for i, objeto in enumerate(objetos, 1):
        offsets.append(len(pdf));pdf.extend(f'{i} 0 obj\n'.encode()+objeto+b'\nendobj\n')
    inicio = len(pdf);pdf.extend(f'xref\n0 {len(objetos)+1}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:
        pdf.extend(f'{offset:010} 00000 n \n'.encode())
    pdf.extend(f'trailer << /Size {len(objetos)+1} /Root 1 0 R >>\nstartxref\n{inicio}\n%%EOF'.encode())
    return bytes(pdf)


FILA = ['40', 'ESP 123', 'Ana Lago\nClub A', 'S13', '99', '50', '25,5', '2']


class Extraccion(unittest.TestCase):
    def setUp(self):
        self.pdf = crear_pdf([[FILA, ['40', 'POR 9', 'Luis Lago\nClub B', 'S16', '88', '70', '30', '3']],
                              [['41', 'ESP 321', 'Otra Persona\nClub C', 'S13', '77', '100', '80', '1']]])

    def test_paginas_continuadas_y_empates_sin_renumerar(self):
        r = e.extraer_pdf(self.pdf)
        filas = e.mapear_filas(r, e.sugerir_mapeo(r['columnas']))
        self.assertEqual([f['posicion_general'] for f in filas], [40, 40, 41])
        self.assertEqual([f['numero_fila'] for f in filas], [1, 2, 3])
        self.assertEqual([f['pagina_origen'] for f in filas], [1, 1, 2])
        self.assertEqual([p['filas'] for p in r['paginas']], [2, 1])

    def test_columnas_repetidas_y_puntos_netos(self):
        r = e.extraer_pdf(self.pdf)
        self.assertEqual(sum(c['nombre'] == 'Pos' for c in r['columnas']), 2)
        mapa = e.sugerir_mapeo(r['columnas'])
        filas = e.mapear_filas(r, mapa)
        self.assertEqual(str(filas[0]['puntos']), '25.5')
        mapa['puntos'] = 'c5'  # El usuario puede elegir TOTAL explícitamente.
        self.assertEqual(e.mapear_filas(r, mapa)[0]['puntos'], 50)
        self.assertEqual(filas[0]['datos_originales']['celdas']['c5'], '50')

    def test_modo_manual_no_inventa_ni_divide_identidades(self):
        r = e.extraer_pdf(self.pdf)
        filas = e.mapear_filas(r, e.sugerir_mapeo(r['columnas']))
        self.assertEqual(filas[0]['participantes'], [])
        self.assertNotIn('fecha_nacimiento_propuesta', filas[0])

    def test_nombre_club_solo_por_eleccion_explicita(self):
        r = e.extraer_pdf(self.pdf)
        fila = e.mapear_filas(r, e.sugerir_mapeo(r['columnas']), 'nombre_club')[0]
        self.assertEqual(fila['participantes'], [{'nombre_original': 'Ana Lago', 'club_original': 'Club A'}])

    def test_columnas_invalidas(self):
        r = e.extraer_pdf(self.pdf)
        for m in [{'puntos': 'c6'}, {'posicion_general': 'c0', 'puntos': 'c0'},
                  {'posicion_general': 'c0', 'puntos': 'no_existe'}]:
            with self.assertRaises(ValidacionError):
                e.mapear_filas(r, m)

    def test_numeros_ambiguos_quedan_pendientes(self):
        for valor in ['DNF', '1 / 2', '40 DNS', '0', '-1', 'NaN']:
            self.assertIsNone(e.convertir_posicion(valor))
        for valor in ['DNF', 'NaN', 'Infinity', '-1', '1.234,5', '1.234']:
            self.assertIsNone(e.convertir_puntos(valor))
        self.assertEqual(e.convertir_posicion('40='), 40)
        self.assertEqual(e.convertir_posicion('=40'), 40)
        self.assertEqual(e.convertir_posicion('1º'), 1)

    def test_archivo_invalido_escaneado_o_demasiado_grande(self):
        for contenido in [b'no es PDF', b'%PDF-roto', crear_pdf([[]]), b'%PDF-' + b'0' * e.MAX_BYTES]:
            with self.assertRaises(ValidacionError):
                e.extraer_pdf(contenido)

    def test_rechaza_cambio_de_estructura_entre_paginas(self):
        nuevos = [(20, 'Pos'), (80, 'Barco'), (180, 'Patron'),
                  (300, 'Cat'), (360, '1'), (420, 'Otro'), (500, 'NET'), (555, 'Pos')]
        with self.assertRaises(ValidacionError):
            e.extraer_pdf(crear_pdf([[FILA], [FILA]], encabezados_continuados=nuevos))

    def test_estado_sin_puesto_numerico_no_se_pierde(self):
        pdf = crear_pdf([[['DNF', 'ESP 9', 'Ana Lago', '', '10', '80', '70', 'DNF']]])
        r = e.extraer_pdf(pdf)
        filas = e.mapear_filas(r, e.sugerir_mapeo(r['columnas']))
        self.assertEqual(len(filas), 1)
        self.assertIsNone(filas[0]['posicion_general'])
        self.assertEqual(filas[0]['datos_originales']['celdas']['c0'], 'DNF')

    def test_renderizado_y_pagina_fuera_de_rango(self):
        self.assertTrue(e.renderizar_pagina(self.pdf, 1).startswith(b'\x89PNG'))
        for pagina in [0, True, 99]:
            with self.assertRaises(ValidacionError):
                e.renderizar_pagina(self.pdf, pagina)


class Almacenamiento(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.carpeta = Path(self.temporal.name)
        self.pdf = crear_pdf([[FILA]])

    def test_fuente_inmutable_nombre_por_huella_y_reutilizacion(self):
        destino = d.guardar_fuente(self.pdf, self.carpeta)
        self.assertEqual(destino.parent, self.carpeta.resolve())
        self.assertEqual(destino.read_bytes(), self.pdf)
        self.assertEqual(d.guardar_fuente(self.pdf, self.carpeta), destino)
        self.assertEqual(len(list(self.carpeta.iterdir())), 1)
        self.assertEqual(destino.stat().st_mode & 0o077, 0)

    def test_detecta_copia_alterada(self):
        destino = d.guardar_fuente(self.pdf, self.carpeta)
        destino.write_bytes(b'alterado')
        with self.assertRaises(ValidacionError):
            d.guardar_fuente(self.pdf, self.carpeta)

    def test_guardado_usa_huella_real_y_conserva_fuente_si_falla_bd(self):
        campos = dict(nombre_archivo='resultado.pdf', id_clase=1, nivel='Nacional')
        with patch.object(d.importaciones, 'crear_borrador', side_effect=OSError('sin conexion')) as guardar:
            with self.assertRaises(OSError):
                d.guardar_borrador_pdf('motor', self.pdf, campos, [], self.carpeta)
        metadatos = guardar.call_args.args[1]
        self.assertEqual(metadatos['huella_documento'], d.importaciones.calcular_huella(self.pdf))
        self.assertEqual(Path(metadatos['referencia_documento']).read_bytes(), self.pdf)
        self.assertEqual(campos, dict(nombre_archivo='resultado.pdf', id_clase=1, nivel='Nacional'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
