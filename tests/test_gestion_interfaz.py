from datetime import date
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from app import datos,gestion_deportistas as g
from services import deportistas as s

ORIGINAL=dict(dni='STDEMO0001',nombre='Alba',apellidos='Lago',fecha_nacimiento=date(2012,1,4),sexo='Femenino',id_club=1)
SCRIPT='''
import streamlit as st
from app import gestion_deportistas

def lectura(clave,funcion,*args):
    return funcion(*args)

gestion_deportistas.mostrar("supabase","motor",lectura)
'''
class TestFormularios(unittest.TestCase):
    def setUp(self):
        pp=[patch.object(datos,'cargar_clubes',return_value=[dict(id_club=1,nombre='Portosín',federacion='Galicia',id_federacion=1),dict(id_club=2,nombre='Palma',federacion='Baleares',id_federacion=2)]),patch.object(datos,'buscar',return_value=[{**ORIGINAL,'club':'Portosín'}]),patch.object(g,'cargar_original',return_value=ORIGINAL.copy()),patch.object(s,'guardar_en_proveedor',return_value='PRUEBA-001')]
        pp.append(patch.object(datos,'cargar_federaciones',return_value=[dict(id_federacion=1,nombre='Galicia'),dict(id_federacion=2,nombre='Baleares'),dict(id_federacion=3,nombre='Canarias')]))
        self.m=[p.start() for p in pp]
        self.addCleanup(lambda:[p.stop() for p in reversed(pp)])
        self.at=AppTest.from_string(SCRIPT,default_timeout=10)
    def campo(self,label):return next(x for x in self.at.text_input if x.label==label)
    def guardar(self):next(x for x in self.at.button if x.label in ('Crear deportista','Guardar cambios')).click().run()
    def test_nunca_guarda_al_abrir(self):
        self.at.run();self.assertEqual(len(self.at.exception),0);self.m[3].assert_not_called()
    def test_alta_confirmada_limpia_formulario(self):
        at=self.at.run()
        self.campo('DNI / documento *').set_value('PRUEBA-001')
        self.campo('Nombre *').set_value('Nombre')
        self.campo('Apellidos *').set_value('Apellido')
        self.guardar()
        self.assertEqual(len(at.exception),0)
        self.assertIn('guardada en Supabase',at.success[0].value)
        self.assertEqual(self.campo('Nombre *').value,'')
        self.assertEqual(self.m[3].call_count,1)
        self.assertEqual(self.m[3].call_args.args[0],'supabase')
    def test_error_validacion_visible(self):
        at=self.at.run();self.m[3].side_effect=s.ValidacionError('El campo nombre es obligatorio.')
        self.guardar()
        self.assertEqual(len(at.exception),0)
        self.assertIn('obligatorio',at.error[0].value)
    def test_edicion_documento_bloqueado_y_baseline(self):
        at=self.at.run();at.radio[0].set_value('Editar ficha').run()
        self.assertEqual(len(at.exception),0)
        self.assertTrue(self.campo('DNI / documento *').disabled)
        self.campo('Nombre *').set_value('Alba María')
        self.guardar()
        self.assertEqual(len(at.exception),0)
        self.assertEqual(self.m[3].call_args.args[1]['nombre'],'Alba María')
        self.assertEqual(self.m[3].call_args.args[2]['nombre'],'Alba')
    def test_conflicto_no_limpia_borrador(self):
        at=self.at.run();at.radio[0].set_value('Editar ficha').run()
        self.campo('Nombre *').set_value('Cambio pendiente')
        self.m[3].side_effect=s.ConflictoError('La ficha cambió. Recarga la ficha.')
        self.guardar()
        self.assertEqual(len(at.exception),0)
        self.assertIn('Recarga',at.error[0].value)
        self.assertEqual(self.campo('Nombre *').value,'Cambio pendiente')
    def test_recargar_descarta_borrador(self):
        at=self.at.run();at.radio[0].set_value('Editar ficha').run()
        self.campo('Nombre *').set_value('Borrador').run()
        next(b for b in at.button if b.label=='Recargar ficha').click().run()
        self.assertEqual(len(at.exception),0)
        self.assertEqual(self.campo('Nombre *').value,'Alba')
    def test_busqueda_vacia_sin_formulario_de_guardado(self):
        at=self.at.run();self.m[1].return_value=[]
        at.radio[0].set_value('Editar ficha').run()
        self.assertEqual(len(at.exception),0)
        self.assertTrue(any('No se han encontrado' in i.value for i in at.info))
        self.m[3].assert_not_called()
    def test_error_de_red_no_expone_detalles(self):
        at=self.at.run();self.m[3].side_effect=OSError('CONTRASEÑA_PRIVADA')
        self.guardar()
        self.assertEqual(len(at.exception),0)
        self.assertIn('No se pudo confirmar',at.error[0].value)
        self.assertNotIn('CONTRASEÑA_PRIVADA',at.error[0].value)

    def selector(self, etiqueta):
        return next(x for x in self.at.selectbox if x.label==etiqueta)
    def test_federacion_filtra_clubes(self):
        at=self.at.run()
        self.selector('Federación autonómica').set_value(2).run()
        self.assertEqual(self.selector('Club').options,['Sin club','Palma · Baleares'])
        self.assertEqual(len(at.exception),0)
        self.m[3].assert_not_called()
    def test_cambio_federacion_conserva_borrador_y_limpia_club(self):
        at=self.at.run()
        self.campo('Nombre *').set_value('Nombre pendiente').run()
        self.selector('Club').set_value(1).run()
        self.selector('Federación autonómica').set_value(2).run()
        self.assertEqual(self.campo('Nombre *').value,'Nombre pendiente')
        self.assertIsNone(self.selector('Club').value)
        self.m[3].assert_not_called()
        self.assertEqual(len(at.exception),0)
    def test_edicion_inicia_en_federacion_original(self):
        at=self.at.run();at.radio[0].set_value('Editar ficha').run()
        self.assertEqual(self.selector('Federación autonómica').value,1)
        self.assertEqual(self.selector('Club').value,1)
    def test_federacion_sin_clubes(self):
        at=self.at.run();self.selector('Federación autonómica').set_value(3).run()
        self.assertEqual(self.selector('Club').options,['Sin club'])
        self.assertTrue(any('No hay clubes' in x.value for x in at.info))
        self.assertEqual(len(at.exception),0)
    def test_guardado_utiliza_club_filtrado(self):
        at=self.at.run()
        self.selector('Federación autonómica').set_value(2).run()
        self.selector('Club').set_value(2).run()
        self.campo('DNI / documento *').set_value('PRUEBA-002')
        self.campo('Nombre *').set_value('Prueba')
        self.campo('Apellidos *').set_value('Club')
        self.guardar()
        self.assertEqual(self.m[3].call_args.args[1]['id_club'],2)
        self.assertEqual(len(at.exception),0)

if __name__=='__main__':unittest.main(verbosity=2)
