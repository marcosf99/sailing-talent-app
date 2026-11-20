"""Una propuesta nunca ejecuta una unión sin la decisión y motivo del usuario."""
import copy
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from services import duplicados as s
import test_duplicados as fixtures


class DuplicadosInterfaz(unittest.TestCase):
    def setUp(self):
        self.helper=fixtures.Duplicados();self.helper.setUp();self.addCleanup(self.helper.doCleanups)
        self.catalogo=s.catalogo(self.helper.engine)
        self.plan=copy.deepcopy(self.helper.plan)
        self.mocks=[]
        for p in (patch.object(s,'catalogo',return_value=self.catalogo),
                  patch.object(s,'preparar',side_effect=lambda *args:self.plan),
                  patch.object(s,'unir_en_proveedor',return_value={'dni':self.helper.destino})):
            self.mocks.append(p.start());self.addCleanup(p.stop)
        self.at=AppTest.from_string('''from app import duplicados
from app.calidad_fichas import mensaje_guardado
def lectura(clave,funcion,*args):return funcion(*args)
mensaje_guardado()
duplicados.mostrar('supabase','motor',lectura)
''')

    def abrir(self):
        self.at.run()
        self.at.checkbox(key='calidad_buscar_duplicados_supabase').check().run()

    def boton(self):return next(b for b in self.at.button if b.label=='Unir las dos fichas revisadas')

    def test_no_consulta_ni_escribe_hasta_activar_la_revision(self):
        self.at.run()
        self.mocks[0].assert_not_called();self.mocks[2].assert_not_called()

    def test_preview_conserva_documento_definitivo_y_expone_ficha_resultante(self):
        self.abrir()
        self.assertEqual(len(self.at.exception),0)
        selector=next(s for s in self.at.selectbox if s.label=='Ficha que se conservará')
        self.assertEqual(selector.value,self.helper.destino)
        self.assertIn('Ficha resultante',self.at.dataframe[0].value.columns)
        self.mocks[2].assert_not_called()

    def test_sin_confirmacion_y_motivo_no_llama_al_guardado(self):
        self.abrir();self.boton().click().run()
        self.mocks[2].assert_not_called()
        self.assertTrue(any('Confirma' in e.value for e in self.at.error))

    def test_guardado_solo_al_confirmar_y_motivo_con_version(self):
        self.abrir()
        self.at.text_area[0].set_value('Identidad verificada con el club')
        next(c for c in self.at.checkbox if c.label.startswith('He comprobado')).check()
        self.boton().click().run()
        self.assertEqual(len(self.at.exception),0)
        self.mocks[2].assert_called_once_with('supabase',self.helper.origen,self.helper.destino,
            self.plan['version'],'Identidad verificada con el club',confirmar=True)
        self.assertTrue(any('Fichas unidas' in m.value for m in self.at.success))

    def test_incompatibilidades_deshabilitan_el_boton(self):
        self.plan['bloqueos']=['Las fechas de nacimiento son distintas.']
        self.abrir()
        self.assertTrue(self.boton().disabled)
        self.assertTrue(any('fechas de nacimiento' in w.value for w in self.at.warning))
        self.mocks[2].assert_not_called()
