"""Edición de tablas y confirmaciones explícitas, usando datos ficticios."""
import copy
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from app import datos
from services import revision_lotes as servicio
from services import revision_participantes as individual
import test_revision_lotes as fixtures


SCRIPT = '''
import streamlit as st
from app import revision_lotes, datos
from services import revision_participantes
proveedor=st.selectbox('Proveedor de prueba',['supabase','cloudsql'])
mensaje=st.session_state.pop('mensaje_prueba',None)
if mensaje:st.success(mensaje)
def lectura(clave,funcion,*args):return funcion(*args)
def exito(mensaje):
    st.session_state['mensaje_prueba']=mensaje
    st.rerun()
revision_lotes.mostrar(proveedor,'motor',lectura,
    revision_participantes.cargar_revision('motor',1),datos.cargar_clubes('motor'),exito,
    datos_regata=st.session_state.get('datos_regata_prueba'))
'''


class TablasRevision(unittest.TestCase):
    def setUp(self):
        helper=fixtures.RevisionLotes();helper.setUp();self.addCleanup(helper.doCleanups)
        self.resumen=helper.resumen()
        self.revision=individual.cargar_revision(helper.engine,helper.ident)
        self.clubes=[dict(id_club=1,nombre='Club A',federacion='Galicia'),dict(id_club=2,nombre='Club B',federacion='Baleares')]
        parches=[patch.object(servicio,'cargar_resumen',side_effect=lambda *a:copy.deepcopy(self.resumen)),
                 patch.object(servicio,'guardar_en_proveedor',return_value={'clubes':1,'participantes':2,'vinculados':1,'resultados_preparados':1,'resultados_incorporados':2,'creados':1}),
                 patch.object(individual,'cargar_revision',side_effect=lambda *a:copy.deepcopy(self.revision)),
                 patch.object(datos,'cargar_clubes',return_value=self.clubes)]
        self.mocks=[p.start() for p in parches]
        self.addCleanup(lambda:[p.stop() for p in reversed(parches)])
        self.at=AppTest.from_string(SCRIPT,default_timeout=15)
        self.ediciones={}

    def boton(self,etiqueta):return next(b for b in self.at.button if b.label==etiqueta)
    def clave(self,tabla,proveedor='supabase'):
        return f'revision_lotes_{proveedor}_1_{self.resumen["version"][:12]}_{tabla}'
    def ejecutar(self):
        # AppTest no serializa el editor como widget interactivo. Reenviamos
        # sus ediciones igual que el navegador en cada interacción posterior.
        for tabla,filas in self.ediciones.items():
            self.at.session_state[self.clave(tabla)]={'edited_rows':filas,'added_rows':[],'deleted_rows':[]}
        return self.at.run()

    def editar(self,tabla,filas):
        self.ediciones[tabla]=filas
        self.ejecutar()

    def test_tablas_sin_selecciones_ni_guardados_automaticos(self):
        self.at.run();self.assertEqual(len(self.at.exception),0)
        self.assertEqual(len(self.at.dataframe),2)
        self.assertFalse(self.at.dataframe[0].value['Confirmar'].any())
        self.assertFalse(self.at.dataframe[1].value['Vincular'].any())
        self.assertTrue(self.boton('Confirmar clubes seleccionados').disabled)
        self.assertTrue(self.boton('Confirmar vinculaciones seleccionadas').disabled)
        self.mocks[1].assert_not_called()

    def test_confirmar_sin_marcar_filas_no_habilita_guardado(self):
        self.at.run()
        next(c for c in self.at.checkbox if c.label.startswith('He revisado los clubes')).check();self.ejecutar()
        self.assertTrue(self.boton('Confirmar clubes seleccionados').disabled)
        self.mocks[1].assert_not_called()

    def test_seleccionar_todas_omite_identidades_sin_propuesta(self):
        self.resumen['propuestas'][1]['propuesta']=None
        self.at.run()
        next(c for c in self.at.checkbox if c.label=='Seleccionar todas las coincidencias propuestas').check().run()
        self.assertEqual(self.at.dataframe[1].value['Vincular'].tolist(),[True])
        self.assertTrue(self.boton('Confirmar vinculaciones seleccionadas').disabled)
        next(c for c in self.at.checkbox if c.label.startswith('Confirmo que cada ficha')).check().run()
        self.boton('Confirmar vinculaciones seleccionadas').click().run()
        self.assertEqual(len(self.mocks[1].call_args.args[3]),1)

    def test_seleccionar_todos_los_clubes_necesita_confirmacion(self):
        self.at.run()
        next(c for c in self.at.checkbox if c.label=='Seleccionar todos los clubes propuestos').check().run()
        self.assertTrue(self.at.dataframe[0].value['Confirmar'].all())
        self.assertTrue(self.boton('Confirmar clubes seleccionados').disabled)
        self.mocks[1].assert_not_called()

    def test_incorporacion_conjunta_exige_revisar_regata_y_envia_metadatos(self):
        from datetime import date
        campos=dict(nombre='Vigo',fecha_inicio=date(2026,10,3),fecha_fin=date(2026,10,4),localidad='Vigo',tipo_clasificacion='definitiva')
        self.at.session_state['datos_regata_prueba']=campos
        self.at.run()
        next(c for c in self.at.checkbox if c.label=='Seleccionar todas las coincidencias propuestas').check().run()
        next(c for c in self.at.checkbox if c.label.startswith('Confirmo que cada ficha')).check().run()
        self.assertTrue(self.boton('Vincular e incorporar resultados seleccionados').disabled)
        next(c for c in self.at.checkbox if c.label.startswith('He revisado los datos de la regata')).check().run()
        self.boton('Vincular e incorporar resultados seleccionados').click().run()
        self.assertEqual(len(self.at.exception),0)
        llamada=self.mocks[1].call_args.args
        self.assertEqual(llamada[1],'vinculos_resultados')
        self.assertEqual(len(llamada[3]),2)
        self.assertEqual(llamada[5],campos)
        self.assertTrue(any('resultados incorporados' in m.value for m in self.at.success))

    def test_altas_sin_dni_solo_sin_coincidencias_y_con_club(self):
        from datetime import date
        self.at.session_state['datos_regata_prueba']=dict(nombre='Vigo',fecha_inicio=date(2026,10,3),fecha_fin=date(2026,10,4),localidad='Vigo',tipo_clasificacion='definitiva')
        self.resumen['propuestas'][0].update(propuesta=None,coincidencias=0)
        self.resumen['propuestas'][0]['participante']['id_club_identificado']=1
        self.resumen['propuestas'][1].update(propuesta=None,coincidencias=2)
        self.at.run()
        self.assertEqual(len(self.at.dataframe),2)
        next(c for c in self.at.checkbox if c.label=='Seleccionar todas las altas propuestas').check().run()
        self.assertTrue(self.boton('Crear fichas seleccionadas e incorporar resultados').disabled)
        next(c for c in self.at.checkbox if c.label.startswith('He revisado las altas seleccionadas')).check().run()
        self.boton('Crear fichas seleccionadas e incorporar resultados').click().run()
        self.assertEqual(len(self.at.exception),0)
        llamada=self.mocks[1].call_args.args
        self.assertEqual(llamada[1],'altas_resultados')
        self.assertEqual(len(llamada[3]),1)
        self.assertNotIn('dni',llamada[3][0]['campos'])
        self.assertEqual(llamada[3][0]['campos']['id_club'],1)

    def test_club_seleccionado_y_recordatorio_opcional(self):
        self.at.run();self.editar('clubes',{0:{'Confirmar':True,'Recordar equivalencia':True,'Club identificado':'Club B · Baleares'}})
        self.assertTrue(self.boton('Confirmar clubes seleccionados').disabled)
        next(c for c in self.at.checkbox if c.label.startswith('He revisado los clubes')).check();self.ejecutar()
        self.boton('Confirmar clubes seleccionados').click();self.ejecutar()
        self.assertEqual(len(self.at.exception),0)
        llamada=self.mocks[1].call_args.args
        self.assertEqual(llamada[:3],('supabase','clubes',1))
        self.assertEqual(llamada[3],[dict(normalizado='club a',id_club=2,recordar=True,version=self.resumen['grupos_club'][0]['version'])])
        self.assertTrue(any('clubes confirmados' in m.value for m in self.at.success))

    def test_dejar_club_pendiente_no_guarda_equivalencia(self):
        self.resumen['grupos_club'][0]['id_club_propuesto']=None
        self.at.run();self.editar('clubes',{0:{'Confirmar':True}})
        next(c for c in self.at.checkbox if c.label.startswith('He revisado los clubes')).check();self.ejecutar()
        self.boton('Confirmar clubes seleccionados').click();self.ejecutar()
        self.assertTrue(any('Selecciona un club' in e.value for e in self.at.error))
        self.mocks[1].assert_not_called()

    def test_vincula_solo_filas_marcadas_y_exige_confirmar(self):
        self.at.run();self.editar('participantes',{0:{'Vincular':True}})
        self.assertTrue(self.boton('Confirmar vinculaciones seleccionadas').disabled)
        next(c for c in self.at.checkbox if c.label.startswith('Confirmo que cada ficha')).check();self.ejecutar()
        self.boton('Confirmar vinculaciones seleccionadas').click();self.ejecutar()
        self.assertEqual(len(self.at.exception),0)
        llamada=self.mocks[1].call_args.args
        self.assertEqual(llamada[:3],('supabase','vinculos',1))
        self.assertEqual(len(llamada[3]),1)
        self.assertEqual(llamada[3][0]['dni'],'D1')
        self.assertEqual(llamada[3][0]['rol'],'Patron')
        self.assertEqual(llamada[4],self.resumen['version'])
        self.assertTrue(any('fichas vinculadas' in m.value for m in self.at.success))
        self.at.run();self.mocks[1].assert_called_once()

    def test_identidad_ambigua_se_deriva_a_revision_individual(self):
        self.resumen['propuestas'][0]['propuesta']=None
        self.at.run()
        self.assertEqual(len(self.at.dataframe[1].value),1)
        self.assertTrue(all('Luis' in n for n in self.at.dataframe[1].value['Nombre en la fuente']))
        self.mocks[1].assert_not_called()

    def test_roles_de_dobles_se_confirman_y_se_envian_canonicos(self):
        self.revision['importacion']['numero_tripulantes']=2
        self.at.run();self.editar('participantes',{0:{'Vincular':True},1:{'Vincular':True}})
        next(c for c in self.at.checkbox if c.label.startswith('Confirmo que cada ficha')).check();self.ejecutar()
        self.boton('Confirmar vinculaciones seleccionadas').click();self.ejecutar()
        self.assertTrue(any('rol' in e.value for e in self.at.error))
        self.mocks[1].assert_not_called()
        self.editar('participantes',{0:{'Vincular':True,'Rol':'Patrón'},1:{'Vincular':True,'Rol':'Tripulante'}})
        self.boton('Confirmar vinculaciones seleccionadas').click();self.ejecutar()
        self.assertEqual(len(self.at.exception),0)
        self.assertEqual([d['rol'] for d in self.mocks[1].call_args.args[3]],['Patron','Tripulante'])

    def test_conflicto_mantiene_seleccion_y_no_anuncia_exito(self):
        self.mocks[1].side_effect=servicio.ConflictoError('La revisión cambió. Actualiza los datos.')
        self.at.run();self.editar('participantes',{0:{'Vincular':True}})
        next(c for c in self.at.checkbox if c.label.startswith('Confirmo que cada ficha')).check();self.ejecutar()
        self.boton('Confirmar vinculaciones seleccionadas').click();self.ejecutar()
        self.assertEqual(len(self.at.exception),0)
        self.assertTrue(any('revisión cambió' in e.value for e in self.at.error))
        self.assertEqual(len(self.at.success),0)
        self.assertTrue(self.at.session_state[self.clave('participantes')]['edited_rows'][0]['Vincular'])

    def test_cambio_de_proveedor_no_reutiliza_selecciones(self):
        self.at.run();self.editar('participantes',{0:{'Vincular':True}})
        self.at.selectbox[0].set_value('cloudsql').run()
        self.assertFalse(self.at.dataframe[1].value['Vincular'].any())
        self.assertTrue(self.boton('Confirmar vinculaciones seleccionadas').disabled)
        self.mocks[1].assert_not_called()

    def test_fallo_lectura_no_expone_secretos(self):
        self.mocks[0].side_effect=OSError('CONTRASEÑA_PRIVADA')
        self.at.run();self.assertEqual(len(self.at.exception),0)
        self.assertTrue(any('formulario individual' in w.value for w in self.at.warning))
        self.assertNotIn('CONTRASEÑA_PRIVADA',str(self.at.warning))
        self.mocks[1].assert_not_called()

    def test_borrador_cerrado_no_muestra_editores(self):
        self.revision['importacion']['estado']='completada'
        self.at.run();self.assertEqual(len(self.at.exception),0)
        self.assertEqual(len(self.at.dataframe),0)
        self.mocks[0].assert_not_called();self.mocks[1].assert_not_called()
