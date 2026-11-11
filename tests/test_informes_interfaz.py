from datetime import date
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from app import datos
from services import informes as s

PERSONAS=[dict(dni='D1',nombre='Alba',apellidos='Lago',club='Portosín',fecha_nacimiento=date(2012,1,4))]
TECNICOS=[dict(dni='T1',nombre='Eva',apellidos='Lago',titulacion='Técnico de vela')]
HISTORIAL=[dict(id_informe=3,fecha=date(2026,10,20),estrategia=4,tactica=None,trimado=3,tecnica=5,fortalezas='Buena preparación.',debilidades=None,recomendaciones='Practicar salidas.',dni_deportista='D1',dni_tecnico='T1',nombre_tecnico='Eva',apellidos_tecnico='Lago')]
SCRIPT='''
from app import informes

def lectura(clave,funcion,*args):
    return funcion(*args)
informes.mostrar("supabase","motor",lectura)
'''
class PruebasFormulario(unittest.TestCase):
    def setUp(self):
        def guardar(proveedor,campos):s.validar(campos);return 5
        pp=[patch.object(datos,'buscar',return_value=PERSONAS),patch.object(s,'listar_tecnicos',return_value=TECNICOS),patch.object(s,'listar_informes',return_value=HISTORIAL),patch.object(s,'guardar_en_proveedor',side_effect=guardar)]
        self.m=[p.start() for p in pp]
        self.addCleanup(lambda:[p.stop() for p in reversed(pp)])
        self.at=AppTest.from_string(SCRIPT,default_timeout=10)
    def selector(self,label):return next(x for x in self.at.selectbox if x.label==label)
    def guardar(self):next(b for b in self.at.button if b.label=='Guardar informe').click().run()
    def test_formulario_contiene_todos_los_campos(self):
        at=self.at.run()
        self.assertEqual(len(at.exception),0)
        self.assertTrue({'Estrategia','Táctica','Trimado','Técnica','Técnico *','Deportista'}.issubset({x.label for x in at.selectbox}))
        self.assertEqual({x.label for x in at.text_area},{'Fortalezas','Debilidades','Recomendaciones'})
        self.assertEqual(len(at.dataframe[0].value),1)
        self.m[3].assert_not_called()
    def test_guardado_completo(self):
        at=self.at.run();self.selector('Técnico *').set_value('T1')
        self.selector('Estrategia').set_value(4)
        self.selector('Táctica').set_value(3)
        next(x for x in at.text_area if x.label=='Fortalezas').set_value('Preparación.')
        next(x for x in at.text_area if x.label=='Recomendaciones').set_value('Mejorar salidas.')
        self.guardar()
        self.assertEqual(len(at.exception),0)
        self.assertIn('Informe 5 guardado en Supabase',at.success[0].value)
        proveedor,campos=self.m[3].call_args.args
        self.assertEqual(proveedor,'supabase')
        self.assertEqual(campos['dni_tecnico'],'T1')
        self.assertEqual(campos['estrategia'],4)
        self.assertIsNone(campos['trimado'])
        self.assertEqual(campos['fortalezas'],'Preparación.')
        self.assertTrue(all(x.value=='' for x in at.text_area))
    def test_tecnico_obligatorio(self):
        at=self.at.run();self.guardar()
        self.assertEqual(len(at.exception),0)
        self.assertIn('técnico',at.error[0].value)
    def test_sin_tecnicos(self):
        self.m[1].return_value=[];at=self.at.run()
        self.assertEqual(len(at.exception),0)
        self.assertTrue(any('No hay técnicos' in w.value for w in at.warning))
        self.m[0].assert_not_called();self.m[3].assert_not_called()
    def test_sin_deportistas(self):
        self.m[0].return_value=[];at=self.at.run()
        self.assertEqual(len(at.exception),0)
        self.assertTrue(any('No se han encontrado' in i.value for i in at.info))
        self.m[3].assert_not_called()
    def test_historial_sin_informes(self):
        self.m[2].return_value=[];at=self.at.run()
        self.assertEqual(len(at.exception),0)
        self.assertTrue(any('todavía no tiene informes' in i.value for i in at.info))
    def test_duplicado_conserva_borrador(self):
        at=self.at.run();self.selector('Técnico *').set_value('T1')
        next(x for x in at.text_area if x.label=='Fortalezas').set_value('Borrador')
        self.m[3].side_effect=s.ConflictoError('Ya existe un informe idéntico.')
        self.guardar()
        self.assertEqual(len(at.exception),0)
        self.assertIn('Ya existe',at.error[0].value)
        self.assertEqual(next(x for x in at.text_area if x.label=='Fortalezas').value,'Borrador')
    def test_error_conexion_no_expone_secretos(self):
        at=self.at.run();self.m[3].side_effect=OSError('CONTRASEÑA_PRIVADA')
        self.guardar()
        self.assertEqual(len(at.exception),0)
        self.assertIn('No se pudo confirmar',at.error[0].value)
        self.assertNotIn('CONTRASEÑA_PRIVADA',at.error[0].value)
    def test_detalle_texto_completo(self):
        at=self.at.run()
        self.assertEqual(len(at.exception),0)
        self.assertIn('Buena preparación.',[x.value for x in at.text])
        self.assertIn('Sin registrar',[x.value for x in at.text])
        self.assertIn('Practicar salidas.',[x.value for x in at.text])

if __name__=='__main__':unittest.main(verbosity=2)
