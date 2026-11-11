"""Lectura del detalle de informes y conexión con la ficha, sin bases reales."""
from datetime import date
import copy
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from app import datos
from services import informes as s


HISTORIAL = [dict(id_informe=11, fecha=date(2026,10,20), estrategia=4, tactica=None, trimado=3, tecnica=5,
    fortalezas='Buena preparación.', debilidades=None, recomendaciones='Practicar salidas.',
    dni_deportista='D1', dni_tecnico='T1', nombre_tecnico='Eva', apellidos_tecnico='Lago', titulacion_tecnico='Técnico de vela'),
    dict(id_informe=10, fecha=date(2026,9,1), estrategia=2, tactica=3, trimado=None, tecnica=4,
    fortalezas='Constancia.', debilidades='Maniobras.', recomendaciones='Trabajo por parejas.',
    dni_deportista='D1', dni_tecnico='T2', nombre_tecnico='Toni', apellidos_tecnico='Serra', titulacion_tecnico=None)]
SCRIPT = '''
from datetime import date
from services import informes
from app import consulta_informes
historial=informes.listar_informes("motor", "D1", fecha_referencia=date(2026,10,20))
consulta_informes.mostrar_historial(historial,"detalle_informe")
'''


class DetalleInformes(unittest.TestCase):
    def setUp(self):
        parche=patch.object(s,'listar_informes',return_value=copy.deepcopy(HISTORIAL))
        self.listar=parche.start();self.addCleanup(parche.stop)
        self.at=AppTest.from_string(SCRIPT,default_timeout=15)

    def test_detalle_completo_autor_y_sin_valorar(self):
        self.at.run()
        self.assertEqual(len(self.at.exception),0)
        self.assertEqual([m.value for m in self.at.metric],['4/5','Sin valorar','3/5','5/5'])
        self.assertTrue(any('Eva Lago' in m.value for m in self.at.markdown))
        self.assertTrue(any('Técnico de vela' in m.value for m in self.at.caption))
        self.assertEqual([t.value for t in self.at.text],['Buena preparación.','Sin registrar','Practicar salidas.'])
        self.assertTrue(self.at.dataframe[0].value['Táctica'].isna().iloc[0])

    def test_cambia_informe_individual_sin_mezclar_textos(self):
        self.at.run()
        self.at.selectbox(key='detalle_informe').set_value(10).run()
        self.assertEqual([m.value for m in self.at.metric],['2/5','3/5','Sin valorar','4/5'])
        self.assertEqual([t.value for t in self.at.text],['Constancia.','Maniobras.','Trabajo por parejas.'])
        self.assertTrue(any('Toni Serra' in m.value for m in self.at.markdown))

    def test_historial_vacio_no_muestra_informe_anterior(self):
        self.at.run();self.listar.return_value=[];self.at.run()
        self.assertEqual(len(self.at.exception),0)
        self.assertEqual(len(self.at.metric),0)
        self.assertEqual(len(self.at.text),0)
        self.assertTrue(any('No hay informes técnicos' in m.value for m in self.at.info))

    def test_seleccion_obsoleta_se_reemplaza_por_informe_disponible(self):
        self.at.run();self.at.selectbox(key='detalle_informe').set_value(10).run()
        self.listar.return_value=[HISTORIAL[0]];self.at.run()
        self.assertEqual(len(self.at.exception),0)
        self.assertEqual(self.at.selectbox(key='detalle_informe').value,11)

    def test_texto_se_presenta_como_texto_sin_html(self):
        self.listar.return_value=[{**HISTORIAL[0],'fortalezas':'<script>alert(1)</script>'}]
        self.at.run()
        self.assertEqual(self.at.text[0].value,'<script>alert(1)</script>')

    def test_adapter_de_ficha_consulta_informes_con_fecha_y_motor(self):
        from database import queries
        with patch.object(queries,'obtener_ficha_deportista',return_value={'dni':'D1'}), \
             patch.object(queries,'consultar_historial_antropometrico',return_value=[]), \
             patch.object(queries,'consultar_resultados_deportista',return_value=[]), \
             patch.object(queries,'consultar_trayectoria_deportista',return_value=[]):
            ficha=datos.cargar_ficha('motor','D1',date(2026,10,20))
        self.assertEqual(ficha['informes'],HISTORIAL)
        self.listar.assert_called_once_with('motor','D1',fecha_referencia=date(2026,10,20))
