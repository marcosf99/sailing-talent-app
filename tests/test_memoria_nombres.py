"""Memoria explícita, contextual y transaccional de decisiones de identidad."""
from datetime import date
import unittest
from unittest.mock import patch
from sqlalchemy import event,text
import test_importaciones as fixtures
from database import importaciones as datos
from services import importaciones as base, revision_participantes as r, revision_lotes as lotes
from services import memoria_nombres as m, resultados_importados as resultados
from services.deportistas import ValidacionError

class MemoriaNombres(unittest.TestCase):
    def setUp(self):
        self.db=fixtures.PersistenciaImportaciones();self.db.setUp();self.addCleanup(self.db.doCleanups)
        self.engine=self.db.engine
        event.listen(self.engine,'before_cursor_execute',lambda c,cu,q,p,ctx,many:(q.replace(' FOR UPDATE',''),p),retval=True)
    def crear(self,nombre='PERALTA SALAS, Anita',club=1):
        return self.db.crear(filas=[{**self.db.filas[0],'participantes':[
            dict(nombre_original=nombre,club_original='Club A' if club else None,id_club_identificado=club)]}])
    def persona(self,ident):return base.obtener_borrador(self.engine,ident)['participantes'][0]
    def vincular(self,ident,dni='D1',**extra):
        p=self.persona(ident)
        return r.guardar_revision(self.engine,p['id_participante_importado'],'vincular',
            dict(id_club=p['id_club_identificado'],**extra),r.version_participante(p),dni_existente=dni)
    def candidatos(self,ident,consulta=''):
        return r.buscar_coincidencias(self.engine,self.persona(ident)['id_participante_importado'],consulta)
    def contar(self,tabla):
        with self.engine.connect() as c:return c.execute(text('SELECT COUNT(*) FROM '+tabla)).scalar_one()
    def test_vincular_no_recuerda_nada_sin_optar(self):
        self.vincular(self.crear())
        self.assertEqual(self.contar('variante_nombre_deportista'),0)
    def test_variante_confirmada_reutiliza_nombre_invertido_sin_cambiar_ficha(self):
        ident=self.crear();self.vincular(ident,recordar_nombre=True)
        otro=self.crear('Anita Peralta Salas')
        candidatos=self.candidatos(otro)
        self.assertEqual([c['dni'] for c in candidatos],['D1'])
        self.assertTrue(candidatos[0]['variante_confirmada'])
        resumen=lotes.cargar_resumen(self.engine,otro)
        self.assertEqual(resumen['propuestas'][0]['propuesta']['dni'],'D1')
        self.assertIsNone(self.persona(otro)['dni_deportista_confirmado'])
        with self.engine.connect() as c:
            self.assertEqual(c.exec_driver_sql("SELECT nombre,apellidos FROM deportista WHERE dni='D1'").one(),('Ana','Pérez'))
    def test_no_se_aplica_a_otro_club(self):
        self.vincular(self.crear(),recordar_nombre=True)
        self.assertEqual(self.candidatos(self.crear(club=2)),[])
    def test_sin_club_se_revierte_el_vinculo_y_la_memoria(self):
        ident=self.crear(club=None)
        with self.assertRaisesRegex(ValidacionError,'club'):self.vincular(ident,recordar_nombre=True)
        self.assertIsNone(self.persona(ident)['dni_deportista_confirmado'])
        self.assertEqual(self.contar('variante_nombre_deportista'),0)
    def test_descarte_confirmado_no_reaparece_pero_busqueda_manual_lo_muestra(self):
        ident=self.crear('Ana Pérez')
        self.vincular(ident,'D2',descartar_dnis=['D1'])
        otro=self.crear('PÉREZ, Ana')
        self.assertFalse(any(c['dni']=='D1' for c in self.candidatos(otro)))
        candidato=self.candidatos(otro,'D1')[0]
        self.assertTrue(candidato['coincidencia_descartada'])
    def test_no_puede_descartar_ficha_confirmada_ni_ficha_no_mostrada(self):
        for descartes in (['D1'],['INEXISTENTE'],['D2']):
            ident=self.crear('Ana Pérez')
            with self.assertRaises(ValidacionError):self.vincular(ident,descartar_dnis=descartes)
            self.assertIsNone(self.persona(ident)['dni_deportista_confirmado'])
    def test_homonimos_con_misma_variante_permanecen_ambiguos(self):
        ident=self.crear();self.vincular(ident,recordar_nombre=True)
        otro=self.crear();self.vincular(otro,'D2',recordar_nombre=True)
        resumen=lotes.cargar_resumen(self.engine,self.crear())
        self.assertIsNone(resumen['propuestas'][0]['propuesta'])
        self.assertEqual(resumen['propuestas'][0]['coincidencias'],2)
    def test_olvidar_se_limita_a_nombre_y_club_y_refresca_propuestas(self):
        a=self.crear();self.vincular(a,recordar_nombre=True)
        b=self.crear('Nombre Alternativo');self.vincular(b,recordar_nombre=True)
        p=self.persona(a)
        m.olvidar(self.engine,p['id_participante_importado'],r.version_participante(p),[dict(tipo='variante',dni='D1')])
        self.assertEqual(self.contar('variante_nombre_deportista'),1)
        self.assertEqual(self.candidatos(self.crear()),[])
    def test_recordar_repetidamente_es_idempotente_y_corregir_elimina_opuesto(self):
        ident=self.crear('Ana Pérez');self.vincular(ident,recordar_nombre=True)
        otro=self.crear('Ana Pérez');self.vincular(otro,recordar_nombre=True)
        self.assertEqual(self.contar('variante_nombre_deportista'),1)
        tercero=self.crear('Ana Pérez');self.vincular(tercero,'D2',descartar_dnis=['D1'])
        self.assertEqual(self.contar('variante_nombre_deportista'),0)
        self.assertEqual(self.contar('descarte_nombre_deportista'),1)
        cuarto=self.crear('Ana Pérez');self.vincular(cuarto,recordar_nombre=True)
        self.assertEqual(self.contar('descarte_nombre_deportista'),0)
    def test_documento_exacto_prevalece_sobre_descarte_pero_se_advierte(self):
        ident=self.crear('Ana Pérez');self.vincular(ident,'D2',descartar_dnis=['D1'])
        otro=self.crear('Ana Pérez')
        with self.engine.begin() as c:c.execute(text('UPDATE participante_importado SET documento_propuesto=:dni WHERE id_participante_importado=:id'),dict(dni='D1',id=self.persona(otro)['id_participante_importado']))
        self.assertTrue(self.candidatos(otro)[0]['coincidencia_descartada'])
    def test_fecha_nacimiento_contradictoria_impide_propuesta_por_variante(self):
        ident=self.crear();self.vincular(ident,recordar_nombre=True)
        otro=self.crear()
        pid=self.persona(otro)['id_participante_importado']
        with self.engine.begin() as c:
            c.exec_driver_sql("UPDATE deportista SET fecha_nacimiento='2012-01-01' WHERE dni='D1'")
            c.execute(text("UPDATE participante_importado SET fecha_nacimiento_propuesta='2013-01-01' WHERE id_participante_importado=:id"),{'id':pid})
        self.assertIsNone(lotes.cargar_resumen(self.engine,otro)['propuestas'][0]['propuesta'])
    def test_fallo_del_resultado_revierte_nueva_ficha_y_memoria(self):
        ident=self.crear('Persona Totalmente Nueva');p=self.persona(ident);b=base.obtener_borrador(self.engine,ident)
        campos=dict(nombre='Persona',apellidos='Totalmente Nueva',id_club=1,recordar_nombre=True)
        regata=dict(nombre='Vigo',fecha_inicio=date(2026,10,3),fecha_fin=date(2026,10,4),localidad='Vigo',tipo_clasificacion='definitiva')
        with patch.object(resultados,'incorporar_en_conexion',side_effect=ValidacionError('Conflicto de resultado')):
            with self.assertRaises(ValidacionError):
                resultados.guardar_con_resultado(self.engine,p['id_participante_importado'],'crear',campos,r.version_participante(p),None,True,regata,resultados.version_resultados(b))
        self.assertEqual(self.contar('variante_nombre_deportista'),0)
        self.assertEqual(self.contar('deportista'),2)
    def test_actualizar_documento_conserva_memoria(self):
        from services import deportistas
        ident=self.crear();self.vincular(ident,recordar_nombre=True)
        with self.engine.connect() as c:original=dict(c.execute(text("SELECT * FROM deportista WHERE dni='D1'")).mappings().one())
        deportistas.actualizar_deportista(self.engine,{**original,'dni':'12345678Z'},original)
        self.assertEqual(self.candidatos(self.crear())[0]['dni'],'12345678Z')

    def test_documento_exacto_gana_a_variante_de_otra_ficha(self):
        self.vincular(self.crear(),'D2',recordar_nombre=True)
        otro=self.crear();pid=self.persona(otro)['id_participante_importado']
        with self.engine.begin() as c:
            c.exec_driver_sql("UPDATE deportista SET nombre='Zoe',apellidos='Zeta' WHERE dni='D1'")
            c.execute(text("UPDATE participante_importado SET documento_propuesto='D1' WHERE id_participante_importado=:id"),{'id':pid})
        self.assertEqual(lotes.cargar_resumen(self.engine,otro)['propuestas'][0]['propuesta']['dni'],'D1')

    def test_recordar_en_lote_y_version_de_memoria_obsoleta(self):
        ident=self.crear('Ana Pérez');resumen=lotes.cargar_resumen(self.engine,ident)
        propuesta=resumen['propuestas'][0]
        decision=dict(participante=propuesta['participante']['id_participante_importado'],dni='D1',
            rol='Patron',version_ficha=propuesta['propuesta']['version_ficha'],recordar_nombre=True)
        lotes.confirmar_vinculos(self.engine,ident,[decision],resumen['version'],confirmar=True)
        self.assertEqual(self.contar('variante_nombre_deportista'),1)
        otro=self.crear('Ana Pérez');resumen=lotes.cargar_resumen(self.engine,otro)
        p=resumen['propuestas'][0];decision.update(participante=p['participante']['id_participante_importado'],version_ficha=p['propuesta']['version_ficha'])
        persona=self.persona(ident)
        with self.engine.begin() as c:
            m.guardar(c,persona,'D1','descarte')
        from services.deportistas import ConflictoError
        with self.assertRaises(ConflictoError):lotes.confirmar_vinculos(self.engine,otro,[decision],resumen['version'],confirmar=True)
