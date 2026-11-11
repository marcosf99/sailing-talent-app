"""Pruebas de la vista previa con PDF sintético y escrituras simuladas."""
from io import BytesIO
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from app import datos
from app import importaciones as vista
from services import documentos_importacion as documentos
from services import extraccion_clasificaciones as extractor
from test_extraccion_clasificaciones import crear_pdf, FILA

SCRIPT = '''
from app import importaciones
def lectura(clave, funcion, *argumentos):
    return funcion(*argumentos)
importaciones.mostrar("supabase", "motor", lectura)
'''
CLASES = [dict(id_clase=1, nombre='Optimist', numero_tripulantes=1),
          dict(id_clase=2, nombre='420', numero_tripulantes=2)]


class VistaPrevia(unittest.TestCase):
    def setUp(self):
        self.pdf = crear_pdf([[FILA, ['41', 'POR 9', 'Luis Lago\nClub B', 'S13', '1', '80', '50', '1']]])
        self.archivo = BytesIO(self.pdf)
        self.archivo.name = 'clasificacion.pdf'
        patches = [patch.object(vista.st, 'file_uploader', return_value=self.archivo),
                   patch.object(datos, 'cargar_clases', return_value=CLASES),
                   patch.object(documentos, 'guardar_en_proveedor', return_value=7)]
        self.mocks = [p.start() for p in patches]
        self.addCleanup(lambda: [p.stop() for p in reversed(patches)])
        self.at = AppTest.from_string(SCRIPT, default_timeout=15)

    def analizar(self):
        self.at.run()
        self.at.button(key='importacion_analizar').click().run()
        self.assertEqual(len(self.at.exception), 0)

    def configurar(self):
        self.at.selectbox(key='importacion_nivel').set_value('Autonomico')
        self.at.selectbox(key='importacion_clase').set_value(1).run()

    def revisar(self):
        next(c for c in self.at.checkbox if c.label.startswith('He revisado')).check().run()

    def test_no_guarda_al_analizar_y_exige_revision(self):
        self.analizar();self.configurar()
        self.assertTrue(self.at.button(key='importacion_guardar').disabled)
        self.assertEqual([m.value for m in self.at.metric], ['1', '1', '0'])
        self.mocks[2].assert_not_called()

    def test_columnas_repetidas_se_distinguen_y_net_es_sugerencia(self):
        self.analizar()
        self.assertEqual(self.at.selectbox(key='importacion_mapa_posicion_general').value, 'c0')
        self.assertEqual(self.at.selectbox(key='importacion_mapa_puntos').value, 'c6')
        opciones = self.at.selectbox(key='importacion_mapa_posicion_general').options
        self.assertIn('1 · Pos', opciones)
        self.assertIn('8 · Pos', opciones)

    def test_guarda_borrador_y_conserva_excluidos(self):
        self.analizar();self.configurar()
        self.at.selectbox(key='importacion_nombres_1').set_value('nombre_club').run()
        self.revisar()
        self.at.button(key='importacion_guardar').click().run()
        self.assertEqual(len(self.at.exception), 0)
        self.assertIn('Borrador 7 guardado en Supabase', self.at.success[0].value)
        proveedor, contenido, campos, filas = self.mocks[2].call_args.args
        self.assertEqual(proveedor, 'supabase')
        self.assertEqual(contenido, self.pdf)
        self.assertEqual(campos['mapeo_columnas']['puntos'], 'c6')
        self.assertEqual(len(filas), 2)
        self.assertEqual(filas[0]['participantes'][0]['nombre_original'], 'Ana Lago')
        self.at.run()
        self.mocks[2].assert_called_once()

    def test_error_de_guardado_conserva_vista_sin_exponer_credenciales(self):
        self.analizar();self.configurar();self.revisar()
        self.mocks[2].side_effect = OSError('CONTRASEÑA_PRIVADA')
        self.at.button(key='importacion_guardar').click().run()
        self.assertEqual(len(self.at.exception), 0)
        self.assertIn('No se pudo confirmar', self.at.error[0].value)
        self.assertNotIn('CONTRASEÑA_PRIVADA', str(self.at.error))
        self.assertGreater(len(self.at.dataframe), 0)

    def test_internacional_exige_columna_vela(self):
        self.analizar();self.configurar()
        self.at.selectbox(key='importacion_nivel').set_value('Internacional')
        self.at.selectbox(key='importacion_mapa_numero_vela_original').set_value('').run()
        self.assertEqual(len(self.at.exception), 0)
        self.assertIn('número de vela', self.at.error[0].value)
        self.mocks[2].assert_not_called()

    def test_cambio_de_archivo_exige_nuevo_analisis(self):
        self.analizar();self.configurar()
        self.mocks[0].return_value = BytesIO(crear_pdf([[['1', 'ESP 77', 'Otra Persona', '', '1', '5', '3', '1']]]))
        self.mocks[0].return_value.name = 'otro.pdf'
        self.at.run()
        self.assertTrue(any('Pulsa Analizar PDF' in i.value for i in self.at.info))
        self.assertEqual(len(self.at.metric), 0)
        self.mocks[2].assert_not_called()

    def test_clase_incorrecta_bloquea_guardado(self):
        self.analizar();self.configurar()
        self.at.selectbox(key='importacion_clase').set_value(2).run()
        self.revisar()
        self.assertTrue(self.at.button(key='importacion_guardar').disabled)
        self.assertTrue(any('no coincide' in w.value for w in self.at.warning))

    def test_pdf_invalido_muestra_error_sin_guardado(self):
        self.mocks[0].return_value = BytesIO(b'no es un PDF')
        self.mocks[0].return_value.name = 'falso.pdf'
        self.analizar()
        self.assertTrue(self.at.error)
        self.mocks[2].assert_not_called()

    def test_columnas_iguales_no_permiten_continuar(self):
        self.analizar();self.configurar()
        self.at.selectbox(key='importacion_mapa_puntos').set_value('c0').run()
        self.assertIn('distintas', self.at.error[0].value)
        self.mocks[2].assert_not_called()

    def test_la_reanalizacion_reinicia_confirmacion(self):
        self.analizar();self.configurar();self.revisar()
        self.at.button(key='importacion_analizar').click().run()
        self.configurar()
        self.assertFalse(next(c for c in self.at.checkbox if c.label.startswith('He revisado')).value)
        self.assertTrue(self.at.button(key='importacion_guardar').disabled)

    def test_cambiar_nivel_exige_revisar_nuevo_criterio(self):
        self.analizar();self.configurar();self.revisar()
        self.at.selectbox(key='importacion_nivel').set_value('Nacional').run()
        self.assertFalse(next(c for c in self.at.checkbox if c.label.startswith('He revisado')).value)
        self.assertTrue(self.at.button(key='importacion_guardar').disabled)

    def test_pagina_original_se_puede_consultar(self):
        self.analizar()
        self.at.checkbox(key='importacion_ver_pdf').check().run()
        self.assertEqual(len(self.at.exception), 0)
        self.assertTrue(self.at.get('imgs'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
