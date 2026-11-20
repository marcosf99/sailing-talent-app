"""Vista por embarcación: un guardado y solo un caso pendiente a la vez."""
import copy
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from app import datos
from services import revision_lotes as s, revision_participantes as individual
from database import importaciones as consultas
import test_revision_rapida as fixtures


SCRIPT='''import streamlit as st
from app import revision_guiada,datos
from services import revision_participantes
mensaje=st.session_state.pop('mensaje',None)
if mensaje:st.success(mensaje)
def lectura(clave,funcion,*args):return funcion(*args)
def exito(m):
    st.session_state['mensaje']=m
    st.rerun()
caso=revision_guiada.mostrar('supabase','motor',lectura,
    revision_participantes.cargar_revision('motor',1),datos.cargar_clubes('motor'),
    st.session_state['metadatos'],exito)
if caso is not None:st.caption('Revisión individual del caso: '+str(caso['fila']))
'''


class RevisionGuiada(unittest.TestCase):
    def setUp(self):
        self.helper=fixtures.RevisionRapida();self.helper.setUp();self.addCleanup(self.helper.doCleanups)
        self.helper.crear()
        self.revision=individual.cargar_revision(self.helper.engine,self.helper.ident)
        self.resumen=self.helper.resumen
        with self.helper.engine.connect() as c:self.clubes=consultas.clubes_revision(c)
        parches=[patch.object(s,'cargar_resumen',side_effect=lambda *a:copy.deepcopy(self.resumen)),
            patch.object(individual,'cargar_revision',side_effect=lambda *a:copy.deepcopy(self.revision)),
            patch.object(datos,'cargar_clubes',return_value=self.clubes),
            patch.object(s,'guardar_en_proveedor',return_value=dict(vinculados=1,creados=1,resultados_incorporados=1,pendientes=0,participantes=2))]
        self.mocks=[p.start() for p in parches]
        for p in parches:self.addCleanup(p.stop)
        self.at=AppTest.from_string(SCRIPT,default_timeout=15)
        self.at.session_state['metadatos']=self.helper.meta

    def test_muestra_un_solo_lote_y_no_pide_confirmaciones_repetidas(self):
        self.at.run()
        self.assertEqual(len(self.at.exception),0)
        self.assertEqual(len(self.at.dataframe),1)
        self.assertEqual(len(self.at.checkbox),0)
        self.assertEqual([m.value for m in self.at.metric],['0','1','0'])
        self.assertIn('Ana Pérez',self.at.dataframe[0].value.iloc[0]['Vincular a fichas existentes'])
        self.assertIn('Úrsula',self.at.dataframe[0].value.iloc[0]['Crear fichas nuevas'])
        self.mocks[3].assert_not_called()

    def test_un_boton_envia_filas_umbral_y_version_del_plan(self):
        self.at.run()
        next(b for b in self.at.button if b.label=='Guardar 1 resultado preparado').click().run()
        self.assertEqual(len(self.at.exception),0)
        args=self.mocks[3].call_args.args
        self.assertEqual(args[0:3],('supabase','revision_rapida',self.helper.ident))
        self.assertEqual(args[3]['filas'],[self.revision['filas'][0]['id_fila']])
        self.assertIn('version_plan',args[3])
        self.assertEqual(args[4],self.resumen['version'])
        self.at.run();self.mocks[3].assert_called_once()

    def test_excluir_una_embarcacion_no_selecciona_solo_un_miembro(self):
        self.at.run()
        plan=s.plan_revision_rapida(self.revision,self.resumen,.75,self.helper.meta)
        clave=f'revision_guiada_supabase_{self.helper.ident}_preparadas_'+plan['version'][:12]
        self.at.session_state[clave]={'edited_rows':{0:{'Guardar':False}},'added_rows':[],'deleted_rows':[]}
        self.at.run()
        self.assertTrue(next(b for b in self.at.button if b.label=='Guardar 0 resultados preparados').disabled)
        self.mocks[3].assert_not_called()

    def test_pendientes_se_abren_solo_al_pedirlo(self):
        self.revision['participantes']=self.revision['participantes'][:1]
        self.revision['participantes_revision']=self.revision['participantes_revision'][:1]
        self.resumen['propuestas']=self.resumen['propuestas'][:1]
        self.at.run()
        self.assertFalse(any(s.label=='Caso que quieres resolver' for s in self.at.selectbox))
        next(b for b in self.at.button if b.label=='Resolver 1 caso pendiente').click().run()
        self.assertEqual(len(self.at.exception),0)
        self.assertTrue(any(s.label=='Caso que quieres resolver' for s in self.at.selectbox))
        self.assertTrue(any('Revisión individual del caso' in c.value for c in self.at.caption))
        next(b for b in self.at.button if b.label=='Volver al resumen').click().run()
        self.assertFalse(any(s.label=='Caso que quieres resolver' for s in self.at.selectbox))

    def test_error_no_sugiere_un_guardado_parcial(self):
        self.mocks[3].side_effect=s.ConflictoError('Una ficha cambió. No se guardó el lote.')
        self.at.run()
        next(b for b in self.at.button if b.label=='Guardar 1 resultado preparado').click().run()
        self.assertTrue(any('No se guardó el lote' in e.value for e in self.at.error))
        self.assertEqual(len(self.at.success),0)
