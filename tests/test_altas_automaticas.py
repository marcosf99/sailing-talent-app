"""Altas por umbral con datos ficticios y controles de identidad y equipo."""
import copy
from datetime import date
from decimal import Decimal
import unittest
from sqlalchemy import event,text
from services import revision_lotes as s, importaciones as base
from services.deportistas import ValidacionError,ConflictoError
import test_revision_lotes as fixtures

class AltasAutomaticas(unittest.TestCase):
    def setUp(self):
        self.helper=fixtures.RevisionLotes();self.helper.setUp();self.addCleanup(self.helper.doCleanups)
        self.engine=self.helper.engine;self.ident=self.helper.ident
        event.listen(self.engine,'before_cursor_execute',lambda c,cu,q,p,ctx,m:(q.replace(' FOR UPDATE',''),p),retval=True)
        self.preparar(('Ana Peláez','Úrsula Abad Montoro'))
        self.meta=dict(nombre='Automáticas',fecha_inicio=date(2026,10,3),fecha_fin=date(2026,10,4),localidad='Vigo',tipo_clasificacion='definitiva')

    def preparar(self,nombres):
        r,decisiones=self.helper.preparar_altas(nombres)
        with self.engine.begin() as c:
            for d in decisiones:
                c.execute(text('UPDATE participante_importado SET nombre_propuesto=:n,apellidos_propuestos=:a,rol_propuesto=:r WHERE id_participante_importado=:id'),{'n':d['campos']['nombre'],'a':d['campos']['apellidos'],'r':'Patron','id':d['participante']})
        self.actualizar()

    def actualizar(self):
        self.resumen=s.cargar_resumen(self.engine,self.ident)
        self.contenido=base.obtener_borrador(self.engine,self.ident)

    def plan(self,umbral='.75',propuestas=None):
        return s.plan_altas_automaticas(self.contenido,self.resumen['propuestas'] if propuestas is None else propuestas,umbral)

    def aplicar(self,umbral='.75',version=None):
        return s.crear_nuevos(self.engine,self.ident,None,self.resumen['version'] if version is None else version,self.meta,confirmar=True,umbral_altas=umbral)

    def test_coincidencia_debil_crea_ficha_y_resultado_con_auditoria(self):
        primero=self.resumen['propuestas'][0]
        self.assertGreater(primero['coincidencias'],0)
        self.assertLess(max(c['indice_similitud'] for c in primero['candidatos']),Decimal('.75'))
        self.assertEqual(self.aplicar(),{'creados':2,'resultados_incorporados':2})
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text('SELECT count(*) FROM deportista')).scalar_one(),4)
            self.assertGreater(c.execute(text("SELECT count(*) FROM coincidencia_propuesta WHERE estado_revision='rechazada'")).scalar_one(),0)
        b=base.obtener_borrador(self.engine,self.ident)
        self.assertTrue(all(p['dni_deportista_confirmado'].startswith('TEMP-') for p in b['participantes']))
        self.assertTrue(all('umbral 0.75' in p['observaciones_revision'] for p in b['participantes']))
        with self.assertRaises((ValidacionError,ConflictoError)):self.aplicar()
        self.assertEqual(self.helper.db.contar('deportista'),4)

    def test_familiar_nuevo_no_bloquea_vinculo_exacto_y_ambos_tienen_resultado(self):
        with self.engine.begin() as c:
            c.exec_driver_sql("UPDATE deportista SET nombre='Jesús',apellidos='Campos Muñoz de Cuena' WHERE dni='D1'")
        self.preparar(('Jesús Campos Muñoz de Cuena','Miguel Campos Muñoz de Cuena'))
        self.assertEqual(self.resumen['propuestas'][0]['propuesta']['dni'],'D1')
        self.assertEqual(self.resumen['propuestas'][1]['coincidencias'],0)
        self.assertEqual(len(self.plan()['decisiones']),1)
        s.confirmar_vinculos(self.engine,self.ident,self.helper.decisiones(self.resumen),
            self.resumen['version'],confirmar=True,datos_resultado=self.meta)
        self.actualizar()
        self.assertEqual(self.aplicar(),{'creados':1,'resultados_incorporados':1})
        self.assertEqual(self.helper.db.contar('participa_en'),2)
        self.assertEqual(self.helper.db.contar('deportista'),3)

    def test_limite_es_estricto_y_umbral_configurable(self):
        for score,umbral,esperado in [('.74999','.75',1),('.75','.75',0),('.75001','.75',0),('.77','.75',0),('.77','.80',1)]:
            r=copy.deepcopy(self.resumen['propuestas'][0]);r['candidatos'][0]['indice_similitud']=Decimal(score)
            with self.subTest(score=score,umbral=umbral):
                self.assertEqual(len(self.plan(umbral,[r])['decisiones']),esperado)

    def test_nombre_abreviado_mismo_club_no_genera_duplicado(self):
        self.preparar(('Ana Pérez García','Úrsula Abad Montoro'))
        r=self.resumen['propuestas'][0]
        self.assertGreaterEqual(r['candidatos'][0]['indice_similitud'],Decimal('.95'))
        self.assertTrue(r['candidatos'][0]['nombre_abreviado'])
        ids={d['participante'] for d in self.plan()['decisiones']}
        self.assertNotIn(r['participante']['id_participante_importado'],ids)
        self.assertEqual(self.aplicar()['creados'],1)

    def test_abreviatura_larga_se_detecta_aunque_similitud_sea_baja(self):
        self.preparar(('Ana María Del Mar Pérez García','Úrsula Abad Montoro'))
        r=self.resumen['propuestas'][0]
        self.assertTrue(any(x['nombre_abreviado'] for x in r['candidatos']))
        self.assertNotIn(r['participante']['id_participante_importado'],{d['participante'] for d in self.plan()['decisiones']})

    def test_apellido_omitido_con_federacion_de_otro_club_permite_alta(self):
        self.preparar(('Ana Pérez García','Úrsula Abad Montoro'))
        ident = self.resumen['propuestas'][0]['participante']['id_participante_importado']
        with self.engine.begin() as c:
            c.exec_driver_sql("INSERT INTO federacion_autonomica(nombre) VALUES ('Otra federación')")
            c.exec_driver_sql('UPDATE club SET id_federacion=2 WHERE id_club=2')
            c.execute(text('UPDATE participante_importado SET id_club_identificado=2 WHERE id_participante_importado=:id'),{'id':ident})
        self.actualizar()
        r=self.resumen['propuestas'][0]
        self.assertEqual(r['participante']['federacion_club_identificado'],'Otra federación')
        self.assertIsNone(r['propuesta'])
        self.assertLess(r['candidatos'][0]['indice_similitud'],Decimal('.65'))
        self.assertIn(ident,{d['participante'] for d in self.plan()['decisiones']})
        self.assertEqual(self.aplicar()['creados'],2)

    def test_nombre_exacto_no_se_crea_con_umbral_maximo(self):
        self.preparar(('Ana Pérez','Úrsula Abad Montoro'))
        ids={d['participante'] for d in self.plan('.85')['decisiones']}
        self.assertNotIn(self.resumen['propuestas'][0]['participante']['id_participante_importado'],ids)

    def test_dos_altas_iguales_quedan_ambas_pendientes(self):
        self.preparar(('Marta Lago Blanco','Marta Lago Blanco'))
        self.assertEqual(self.plan()['decisiones'],[])
        with self.assertRaises(ValidacionError):self.aplicar()
        self.assertEqual(self.helper.db.contar('deportista'),2)

    def test_sin_club_o_apellidos_no_hay_alta_automatica(self):
        propuestas=copy.deepcopy(self.resumen['propuestas'])
        propuestas[0]['participante']['id_club_identificado']=None
        propuestas[1]['participante']['apellidos_propuestos']=None
        self.assertEqual(self.plan(propuestas=propuestas)['decisiones'],[])

    def test_nombre_sin_propuestas_se_separa_desde_fuente_y_respeta_coma(self):
        propuestas=copy.deepcopy(self.resumen['propuestas'])
        p=propuestas[0]['participante']
        p.update(nombre_propuesto=None,apellidos_propuestos=None,nombre_original='Pérez, Alba')
        d=self.plan(propuestas=propuestas)['decisiones'][0]
        self.assertEqual(d['campos']['nombre'],'Alba')
        self.assertEqual(d['campos']['apellidos'],'Pérez')

    def test_sin_propuestas_en_bd_el_alta_automatica_utiliza_el_texto_original(self):
        with self.engine.begin() as c:
            c.exec_driver_sql('UPDATE participante_importado SET nombre_propuesto=NULL,apellidos_propuestos=NULL')
        self.actualizar()
        self.assertEqual(self.aplicar()['creados'],2)

    def test_datos_invalidos_se_dejan_pendientes_sin_bloquear_otras_altas(self):
        propuestas=copy.deepcopy(self.resumen['propuestas'])
        propuestas[0]['participante']['nombre_propuesto']=' '*3
        plan=self.plan(propuestas=propuestas)
        self.assertEqual(len(plan['decisiones']),1)
        self.assertIn('nombre',plan['pendientes'][0]['motivo'])

    def test_fallo_de_resultado_revierte_altas_automaticas(self):
        with self.engine.begin() as c:
            c.exec_driver_sql("CREATE TRIGGER fallo BEFORE INSERT ON participa_en BEGIN SELECT RAISE(ABORT,'fallo'); END")
        with self.assertRaises(ConflictoError):self.aplicar()
        self.assertEqual(self.helper.db.contar('deportista'),2)
        self.assertEqual(self.helper.db.contar('coincidencia_propuesta'),0)

    def test_equipo_doble_incompleto_se_deja_pendiente(self):
        with self.engine.begin() as c:c.exec_driver_sql('UPDATE clase SET numero_tripulantes=2 WHERE id_clase=1')
        self.actualizar()
        self.assertEqual(self.plan()['decisiones'],[])
        self.assertEqual(self.helper.db.contar('deportista'),2)

    def test_avisos_de_extraccion_no_se_saltan(self):
        propuestas=copy.deepcopy(self.resumen['propuestas'])
        for r in propuestas:r['participante']['fila']['datos_originales']['avisos_extraccion']=['Revisar nombres']
        self.assertEqual(self.plan(propuestas=propuestas)['decisiones'],[])

    def test_version_obsoleta_no_crea_fichas(self):
        with self.assertRaises(ConflictoError):self.aplicar(version='obsoleta')
        self.assertEqual(self.helper.db.contar('deportista'),2)

    def test_umbral_invalido_no_escribe(self):
        for v in (True,'NaN','Infinity',0,.64,.86,'texto'):
            with self.subTest(umbral=v),self.assertRaises(ValidacionError):self.aplicar(v)
        self.assertEqual(self.helper.db.contar('deportista'),2)
