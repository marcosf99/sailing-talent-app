"""Prioridad del nacimiento y guardado explícito, sin bases externas."""
from datetime import date
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from services import deportistas


class CalidadFichas(unittest.TestCase):
    def setUp(self):
        self.filas=[dict(dni='TEMP-1',nombre='Ana',apellidos='Pérez',id_federacion=1,
            federacion='Federación A',id_club=1,club='Club A',sin_dni=True,sin_nacimiento=True),
            dict(dni='TEMP-2',nombre='Luis',apellidos='Lago',id_federacion=2,
            federacion='Federación B',id_club=2,club='Club B',sin_dni=True,sin_nacimiento=False)]
        self.m=patch.object(deportistas,'datos_pendientes',side_effect=lambda m:self.filas)
        self.m.start();self.addCleanup(self.m.stop)
        self.at=AppTest.from_string('''from app.calidad_fichas import mostrar
def lectura(clave,funcion,*args):return funcion(*args)
mostrar('supabase','motor',lectura)
''')

    def test_prioriza_nacimiento_y_agrupa_sin_escribir(self):
        with patch.object(deportistas,'guardar_nacimiento_en_proveedor') as guardar:
            self.at.run()
            self.assertEqual(len(self.at.exception),0)
            self.assertEqual(self.at.selectbox(key='pendientes_dato_supabase_calidad').value,'Sin fecha de nacimiento')
            self.assertEqual(len(self.at.dataframe[1].value),1)
            self.assertEqual(self.at.metric[0].value,'1')
            guardar.assert_not_called()

    def test_guardado_actualiza_pendientes_y_respeta_proveedor(self):
        def guardar(proveedor,dni,nacimiento,anterior):
            self.assertEqual((proveedor,dni,nacimiento,anterior),('supabase','TEMP-1',date(2012,1,4),None))
            self.filas[0]['sin_nacimiento']=False
        with patch.object(deportistas,'guardar_nacimiento_en_proveedor',side_effect=guardar) as mock:
            self.at.run()
            self.at.date_input[0].set_value(date(2012,1,4))
            next(b for b in self.at.button if b.label=='Guardar fecha de nacimiento').click().run()
            self.assertEqual(len(self.at.exception),0)
            mock.assert_called_once()
            self.assertEqual(self.at.metric[0].value,'0')
            self.assertTrue(any('guardada' in s.value for s in self.at.success))

    def test_conflicto_no_se_oculta_ni_limpia_la_fecha_introducida(self):
        with patch.object(deportistas,'guardar_nacimiento_en_proveedor',side_effect=deportistas.ConflictoError('La fecha cambió. Actualiza los datos.')):
            self.at.run()
            self.at.date_input[0].set_value(date(2012,1,4))
            next(b for b in self.at.button if b.label=='Guardar fecha de nacimiento').click().run()
            self.assertEqual(len(self.at.exception),0)
            self.assertTrue(any('La fecha cambió' in e.value for e in self.at.error))
            self.assertEqual(self.at.date_input[0].value,date(2012,1,4))
