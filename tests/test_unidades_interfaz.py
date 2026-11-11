from datetime import date
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from app import datos
from services import unidades_competitivas as s

CLASES=[dict(id_clase=1,nombre='Optimist',numero_tripulantes=1),dict(id_clase=2,nombre='420',numero_tripulantes=2)]
PERSONAS=[dict(dni='D1',nombre='Ana',apellidos='Lago',club='Vigo'),dict(dni='D2',nombre='Brais',apellidos='Rey',club='Vigo')]
UNIDADES=[dict(id_unidad=10,fecha_inicio=date(2026,1,1),fecha_fin=None,clase='Optimist',miembros=['Ana Lago (Patrón)'])]
SCRIPT='''
from app import unidades_competitivas

def lectura(clave,funcion,*args):
    return funcion(*args)
unidades_competitivas.mostrar("supabase","motor",lectura)
'''
class PruebasFormulario(unittest.TestCase):
    def setUp(self):
        pp=[patch.object(datos,'cargar_clases',return_value=CLASES),patch.object(datos,'buscar',return_value=PERSONAS),patch.object(s,'listar_unidades',return_value=UNIDADES),patch.object(s,'guardar_en_proveedor',return_value=11)]
        self.m=[p.start() for p in pp]
        self.addCleanup(lambda:[p.stop() for p in reversed(pp)])
        self.at=AppTest.from_string(SCRIPT,default_timeout=10)
    def selector(self,label):return next(x for x in self.at.selectbox if x.label==label)
    def pulsar(self,label):next(b for b in self.at.button if b.label==label).click().run()
    def test_abre_listado_sin_escrituras(self):
        at=self.at.run();self.assertEqual(len(at.exception),0)
        self.assertEqual(len(at.dataframe[0].value),1)
        self.assertEqual({x.label for x in at.selectbox},{'Filtrar listado por clase','Clase de la nueva unidad','Patrón'})
        self.m[3].assert_not_called()
    def test_crear_individual(self):
        at=self.at.run();self.selector('Patrón').set_value('D1')
        self.pulsar('Crear unidad')
        self.assertEqual(len(at.exception),0)
        proveedor,accion,campos=self.m[3].call_args.args
        self.assertEqual((proveedor,accion),('supabase','crear'))
        self.assertEqual(campos['patron'],'D1');self.assertIsNone(campos['tripulante'])
        self.assertIn('creada',at.success[0].value)
    def test_crear_doble(self):
        at=self.at.run();self.selector('Clase de la nueva unidad').set_value(2).run()
        self.selector('Patrón').set_value('D1');self.selector('Tripulante').set_value('D2')
        self.pulsar('Crear unidad')
        self.assertEqual(len(at.exception),0)
        self.assertEqual(self.m[3].call_args.args[2]['tripulante'],'D2')
        self.assertEqual(self.m[3].call_args.args[2]['id_clase'],2)
    def test_conflicto_visible_conserva_seleccion(self):
        at=self.at.run();self.selector('Patrón').set_value('D1')
        self.m[3].side_effect=s.ConflictoError('Las fechas están solapadas.')
        self.pulsar('Crear unidad')
        self.assertEqual(len(at.exception),0)
        self.assertIn('solapadas',at.error[0].value)
        self.assertEqual(self.selector('Patrón').value,'D1')
    def test_finalizacion(self):
        at=self.at.run();at.radio(key='unidades_operacion').set_value('Finalizar unidad').run()
        self.pulsar('Finalizar unidad')
        self.assertEqual(len(at.exception),0)
        self.assertEqual(self.m[3].call_args.args[1],'finalizar')
        self.assertEqual(self.m[3].call_args.args[2]['id_unidad'],10)
        self.assertIn('finalizada',at.success[0].value)
    def test_sin_abiertas(self):
        at=self.at.run();self.m[2].return_value=[{**UNIDADES[0],'fecha_fin':date(2026,5,1)}]
        at.radio(key='unidades_operacion').set_value('Finalizar unidad').run()
        self.assertEqual(len(at.exception),0)
        self.assertTrue(any('No hay unidades abiertas' in i.value for i in at.info))
        self.m[3].assert_not_called()
    def test_sin_regatistas(self):
        self.m[1].return_value=[];at=self.at.run()
        self.assertEqual(len(at.exception),0)
        self.assertTrue(any('No se han encontrado' in i.value for i in at.info))
        self.m[3].assert_not_called()
    def test_error_red_sin_credenciales(self):
        at=self.at.run();self.m[3].side_effect=OSError('CONTRASEÑA_PRIVADA')
        self.pulsar('Crear unidad')
        self.assertEqual(len(at.exception),0)
        self.assertIn('No se pudo confirmar',at.error[0].value)
        self.assertNotIn('CONTRASEÑA_PRIVADA',at.error[0].value)

    def test_clase_nueva_no_cambia_filtro_listado(self):
        at=self.at.run()
        self.selector('Clase de la nueva unidad').set_value(2).run()
        self.assertEqual(self.selector('Filtrar listado por clase').value,1)
        self.assertEqual(self.m[2].call_args.args[1],1)
        self.assertEqual(len(at.exception),0)
    def test_filtro_listado_no_cambia_clase_nueva(self):
        at=self.at.run()
        self.selector('Filtrar listado por clase').set_value(2).run()
        self.assertEqual(self.selector('Clase de la nueva unidad').value,1)
        self.assertEqual(self.m[2].call_args.args[1],2)
        self.assertEqual(len(at.exception),0)
    def test_cambio_clase_conserva_fecha_y_patron(self):
        at=self.at.run()
        next(x for x in at.date_input if x.label=='Fecha de inicio').set_value(date(2026,10,1)).run()
        self.selector('Patrón').set_value('D1').run()
        self.selector('Clase de la nueva unidad').set_value(2).run()
        self.assertEqual(self.selector('Patrón').value,'D1')
        self.assertEqual(next(x for x in at.date_input if x.label=='Fecha de inicio').value,date(2026,10,1))
        self.assertIn('Tripulante',{x.label for x in at.selectbox})
        self.selector('Clase de la nueva unidad').set_value(1).run()
        self.assertNotIn('Tripulante',{x.label for x in at.selectbox})
        self.assertEqual(len(at.exception),0)

if __name__=='__main__':unittest.main(verbosity=2)
