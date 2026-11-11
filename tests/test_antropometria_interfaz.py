from datetime import date
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from app import datos, antropometria as pagina
from services import antropometria as servicio

PERSONAS=[dict(dni='DEMO001',nombre='Alba',apellidos='Lago',club='Portosín',fecha_nacimiento=date(2012,1,4)),dict(dni='DEMO002',nombre='Iago',apellidos='Rey',club=None,fecha_nacimiento=None)]
HISTORIAL=[dict(id_registro=1,fecha=date(2026,10,15),altura=148,peso=39,envergadura=151,porcentaje_graso=18)]
SCRIPT='''
from app import antropometria

def lectura(clave,funcion,*args):
    return funcion(*args)
antropometria.mostrar("supabase","motor",lectura)
'''

class PruebasFormulario(unittest.TestCase):
    def setUp(self):
        def guardar(proveedor,campos):
            servicio.validar(campos)
            return 77
        pp=[patch.object(datos,'buscar',return_value=PERSONAS),patch.object(pagina,'cargar_historial',return_value=HISTORIAL),patch.object(servicio,'guardar_en_proveedor',side_effect=guardar)]
        self.m=[p.start() for p in pp]
        self.addCleanup(lambda:[p.stop() for p in reversed(pp)])
        self.at=AppTest.from_string(SCRIPT,default_timeout=10)
    def medida(self,label):return next(x for x in self.at.number_input if x.label==label)
    def guardar(self):next(b for b in self.at.button if b.label=='Guardar medición').click().run()
    def test_abre_historial_sin_escribir(self):
        at=self.at.run()
        self.assertEqual(len(at.exception),0)
        self.assertEqual(len(at.dataframe[0].value),1)
        self.assertTrue(all(n.value is None for n in at.number_input))
        self.m[2].assert_not_called()
    def test_guardado_parcial_y_limpieza(self):
        at=self.at.run();self.medida('Altura (cm)').set_value(150.25)
        self.guardar()
        self.assertEqual(len(at.exception),0)
        self.assertIn('guardada en Supabase',at.success[0].value)
        self.assertTrue(all(n.value is None for n in at.number_input))
        self.assertEqual(self.m[2].call_count,1)
        proveedor,campos=self.m[2].call_args.args
        self.assertEqual(proveedor,'supabase')
        self.assertEqual(campos['altura'],150.25)
        self.assertIsNone(campos['peso'])
        self.assertEqual(campos['dni_deportista'],'DEMO001')
    def test_formulario_vacio_muestra_error(self):
        at=self.at.run();self.guardar()
        self.assertEqual(len(at.exception),0)
        self.assertIn('al menos una medida',at.error[0].value)
    def test_duplicado_conserva_borrador(self):
        at=self.at.run();self.medida('Peso (kg)').set_value(39)
        self.m[2].side_effect=servicio.ConflictoError('Ya existe una medición idéntica.')
        self.guardar()
        self.assertEqual(len(at.exception),0)
        self.assertIn('Ya existe',at.error[0].value)
        self.assertEqual(self.medida('Peso (kg)').value,39)
    def test_deportista_sin_historial(self):
        at=self.at.run();self.m[1].return_value=[]
        at.selectbox(key='antropo_documento').set_value('DEMO002').run()
        self.assertEqual(len(at.exception),0)
        self.assertTrue(any('todavía no tiene' in i.value for i in at.info))
        self.assertTrue(any('Sin registrar' in c.value for c in at.caption))
    def test_busqueda_sin_deportistas(self):
        self.m[0].return_value=[]
        at=self.at.run()
        self.assertEqual(len(at.exception),0)
        self.assertTrue(any('No se han encontrado' in i.value for i in at.info))
        self.assertEqual(len(at.number_input),0)
        self.m[2].assert_not_called()
    def test_error_red_sin_exponer_detalles(self):
        at=self.at.run();self.medida('Altura (cm)').set_value(150)
        self.m[2].side_effect=OSError('CONTRASEÑA_PRIVADA')
        self.guardar()
        self.assertEqual(len(at.exception),0)
        self.assertIn('No se pudo confirmar',at.error[0].value)
        self.assertNotIn('CONTRASEÑA_PRIVADA',at.error[0].value)
    def test_grasa_cero_se_envia(self):
        at=self.at.run();self.medida('Grasa corporal (%)').set_value(0.0)
        self.guardar()
        self.assertEqual(len(at.exception),0)
        self.assertEqual(self.m[2].call_args.args[1]['porcentaje_graso'],0)

if __name__=='__main__':unittest.main(verbosity=2)
