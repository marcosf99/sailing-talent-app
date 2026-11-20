"""Unión revisada con todo el historial ficticio y copia de auditoría."""
from datetime import date
import json
import unittest
from sqlalchemy import event,text
from services import duplicados as s, importaciones as base
import test_importaciones as fixtures


class Duplicados(unittest.TestCase):
    def setUp(self):
        self.db=fixtures.PersistenciaImportaciones();self.db.setUp();self.addCleanup(self.db.doCleanups)
        self.engine=self.db.engine
        event.listen(self.engine,'before_cursor_execute',lambda c,cu,q,p,ctx,m:(q.replace(' FOR UPDATE',''),p),retval=True)
        self.origen='TEMP-ABC';self.destino='12345678Z'
        with self.engine.begin() as c:
            c.exec_driver_sql("UPDATE deportista SET dni='TEMP-ABC',nombre='Ana',apellidos='Pérez',fecha_nacimiento='2012-01-04' WHERE dni='D1'")
            c.exec_driver_sql("UPDATE deportista SET dni='12345678Z',nombre='Ana',apellidos='Pérez García',id_club=2 WHERE dni='D2'")
            c.exec_driver_sql("INSERT INTO unidad_competitiva(id_unidad,id_clase,fecha_inicio) VALUES (1,1,'2025-01-01'),(2,1,'2026-01-01')")
            c.exec_driver_sql("INSERT INTO forma_parte(dni_deportista,id_unidad,rol) VALUES ('TEMP-ABC',1,'Patron'),('12345678Z',2,'Patron')")
            c.exec_driver_sql("INSERT INTO competicion(id_competicion,nombre,fecha_inicio,fecha_fin,nivel,id_clase) VALUES (2,'Anterior','2025-05-01','2025-05-02','Nacional',1)")
            c.exec_driver_sql("INSERT INTO participa_en(id_unidad,id_competicion,posicion_general,puntos) VALUES (1,2,3,15.5),(2,1,1,10)")
            c.exec_driver_sql("INSERT INTO registro_antropometrico(fecha,altura,dni_deportista) VALUES ('2025-01-01',155,'TEMP-ABC'),('2026-01-01',160,'12345678Z')")
            c.exec_driver_sql("INSERT INTO tecnico(dni,nombre,apellidos) VALUES ('T1','Eva','Lago')")
            c.exec_driver_sql("INSERT INTO informe(fecha,dni_deportista,dni_tecnico,tactica) VALUES ('2025-06-01','TEMP-ABC','T1',4)")
        self.ident=self.db.crear()
        self.persona=base.obtener_borrador(self.engine,self.ident)['participantes'][0]['id_participante_importado']
        with self.engine.begin() as c:
            c.execute(text("UPDATE participante_importado SET dni_deportista_confirmado=:dni,confirmado_en=CURRENT_TIMESTAMP,estado='vinculado' WHERE id_participante_importado=:id"),dict(dni=self.origen,id=self.persona))
            c.execute(text("INSERT INTO coincidencia_propuesta(id_participante_importado,dni_deportista,indice_similitud,motivos,estado_revision,revisado_en) VALUES (:id,:dni,.95,'Revisado','aceptada',CURRENT_TIMESTAMP)"),dict(id=self.persona,dni=self.origen))
            c.exec_driver_sql("INSERT INTO variante_nombre_deportista(dni_deportista,id_club,nombre_original,nombre_normalizado) VALUES ('TEMP-ABC',1,'PEREZ, Ana','ana perez')")
        self.plan=s.preparar(self.engine,self.origen,self.destino)

    def unir(self,**opciones):
        return s.unir(self.engine,self.origen,self.destino,opciones.pop('version',self.plan['version']),
            opciones.pop('motivo','Identidad confirmada por el club'),confirmar=opciones.pop('confirmar',True),**opciones)

    def filas(self,tabla):
        with self.engine.connect() as c:return [dict(r) for r in c.execute(text('SELECT * FROM '+tabla)).mappings()]

    def test_preview_no_escribe_y_familiares_no_generan_propuestas(self):
        self.assertEqual(self.plan['bloqueos'],[])
        self.assertEqual(self.plan['cantidades']['informe'],1)
        self.assertEqual(self.plan['ficha_final']['fecha_nacimiento'],date(2012,1,4))
        self.assertEqual(self.filas('fusion_deportista'),[])
        fichas=s.catalogo(self.engine)
        self.assertEqual(len(s.posibles(fichas)),1)
        fichas[0]['nombre']='Miguel';fichas[1]['nombre']='Jesús'
        self.assertEqual(s.posibles(fichas),[])

    def test_union_conserva_resultados_mediciones_informes_y_fuentes(self):
        antes=self.filas('participa_en')
        self.assertEqual(self.unir()['dni'],self.destino)
        self.assertEqual(len(self.filas('deportista')),1)
        self.assertEqual(self.filas('deportista')[0]['fecha_nacimiento'],'2012-01-04')
        self.assertEqual(self.filas('deportista')[0]['apellidos'],'Pérez García')
        self.assertEqual(self.filas('participa_en'),antes)
        self.assertEqual({r['dni_deportista'] for r in self.filas('registro_antropometrico')},{self.destino})
        self.assertEqual(len(self.filas('registro_antropometrico')),2)
        self.assertEqual(self.filas('informe')[0]['dni_deportista'],self.destino)
        self.assertEqual(self.filas('participante_importado')[0]['dni_deportista_confirmado'],self.destino)
        self.assertEqual(self.filas('coincidencia_propuesta')[0]['dni_deportista'],self.destino)
        self.assertEqual(len(self.filas('forma_parte')),2)
        self.assertTrue(all(r['dni_deportista']==self.destino for r in self.filas('forma_parte')))
        memoria=self.filas('variante_nombre_deportista')
        self.assertTrue(any(r['nombre_normalizado']=='ana perez' and r['dni_deportista']==self.destino for r in memoria))
        auditoria=self.filas('fusion_deportista')[0]
        copia=json.loads(auditoria['datos_antes'])
        self.assertEqual(len(copia['fichas']),2)
        self.assertEqual(len(copia['relaciones']['registro_antropometrico']),2)
        self.assertEqual(auditoria['documento_origen'],self.origen)
        with self.assertRaises(s.ConflictoError):self.unir()

    def test_sin_confirmacion_o_motivo_no_se_guarda(self):
        for opciones in (dict(confirmar=False),dict(motivo=' ')):
            with self.subTest(opciones=opciones),self.assertRaises(s.ValidacionError):self.unir(**opciones)
        self.assertEqual(len(self.filas('deportista')),2)
        self.assertEqual(self.filas('fusion_deportista'),[])

    def test_cambio_en_ficha_o_historial_invalida_la_version(self):
        with self.engine.begin() as c:c.exec_driver_sql("UPDATE informe SET tactica=5")
        with self.assertRaisesRegex(s.ConflictoError,'cambiado'):self.unir()
        self.assertEqual(len(self.filas('deportista')),2)

    def test_nacimientos_distintos_y_documentos_definitivos_bloquean(self):
        with self.engine.begin() as c:c.exec_driver_sql("UPDATE deportista SET fecha_nacimiento='2013-01-01' WHERE dni='12345678Z'")
        p=s.preparar(self.engine,self.origen,self.destino)
        self.assertTrue(any('nacimiento' in m for m in p['bloqueos']))
        with self.assertRaises(s.ConflictoError):self.unir(version=p['version'])
        with self.engine.begin() as c:c.exec_driver_sql("UPDATE deportista SET dni='87654321X' WHERE dni='TEMP-ABC'")
        p=s.preparar(self.engine,'87654321X',self.destino)
        self.assertTrue(any('documentos definitivos' in m for m in p['bloqueos']))

    def test_no_retira_documento_definitivo_para_conservar_un_temporal(self):
        p=s.preparar(self.engine,self.destino,self.origen)
        self.assertTrue(any('documento definitivo' in m for m in p['bloqueos']))

    def test_no_reduce_un_equipo_doble_a_una_sola_persona(self):
        with self.engine.begin() as c:
            c.exec_driver_sql('UPDATE unidad_competitiva SET id_clase=2 WHERE id_unidad=1')
            c.exec_driver_sql("INSERT INTO forma_parte(dni_deportista,id_unidad,rol) VALUES ('12345678Z',1,'Tripulante')")
        p=s.preparar(self.engine,self.origen,self.destino)
        self.assertTrue(any('mismo equipo' in m for m in p['bloqueos']))
        with self.assertRaises(s.ConflictoError):self.unir(version=p['version'])

    def test_no_decide_entre_dos_resultados_distintos_de_la_misma_regata(self):
        with self.engine.begin() as c:c.exec_driver_sql('INSERT INTO participa_en(id_unidad,id_competicion,posicion_general) VALUES (1,1,2)')
        p=s.preparar(self.engine,self.origen,self.destino)
        self.assertTrue(any('Regata' in m for m in p['bloqueos']))

    def test_fallo_tardio_revierte_traslados_y_copia_de_auditoria(self):
        with self.engine.begin() as c:
            c.exec_driver_sql("CREATE TRIGGER fallo_fusion BEFORE DELETE ON deportista BEGIN SELECT RAISE(ABORT,'fallo'); END")
        with self.assertRaises(s.ConflictoError):self.unir()
        self.assertEqual(len(self.filas('deportista')),2)
        self.assertEqual(self.filas('fusion_deportista'),[])
        self.assertEqual(self.filas('informe')[0]['dni_deportista'],self.origen)
        self.assertEqual(self.filas('participante_importado')[0]['dni_deportista_confirmado'],self.origen)

    def test_no_duplica_propuestas_o_variantes_ya_presentes(self):
        with self.engine.begin() as c:
            c.execute(text("INSERT INTO coincidencia_propuesta(id_participante_importado,dni_deportista,motivos) VALUES (:id,:dni,'Otra propuesta')"),dict(id=self.persona,dni=self.destino))
            c.exec_driver_sql("INSERT INTO variante_nombre_deportista(dni_deportista,id_club,nombre_original,nombre_normalizado) VALUES ('12345678Z',1,'Ana Pérez','ana perez')")
        p=s.preparar(self.engine,self.origen,self.destino)
        self.unir(version=p['version'])
        self.assertEqual(len(self.filas('coincidencia_propuesta')),1)
        self.assertEqual(len([r for r in self.filas('variante_nombre_deportista') if r['nombre_normalizado']=='ana perez']),1)

    def test_rechazos_contradictorios_exigen_revision(self):
        with self.engine.begin() as c:c.exec_driver_sql("INSERT INTO descarte_nombre_deportista(dni_deportista,id_club,nombre_original,nombre_normalizado) VALUES ('12345678Z',1,'Ana Pérez','ana perez')")
        p=s.preparar(self.engine,self.origen,self.destino)
        self.assertTrue(any('contradictorios' in m for m in p['bloqueos']))

    def test_no_colapsa_dos_miembros_confirmados_en_la_misma_fila(self):
        with self.engine.begin() as c:
            fila=self.filas('participante_importado')[0]['id_fila']
            c.execute(text("""INSERT INTO participante_importado(id_fila,orden_en_tripulacion,nombre_original,
                dni_deportista_confirmado,confirmado_en,estado) VALUES (:fila,2,'Otra aparición',:dni,CURRENT_TIMESTAMP,'vinculado')"""),dict(fila=fila,dni=self.destino))
        p=s.preparar(self.engine,self.origen,self.destino)
        self.assertTrue(any('misma embarcación importada' in m for m in p['bloqueos']))

    def test_pertenencia_duplicada_individual_no_multiplica_resultados(self):
        with self.engine.begin() as c:c.exec_driver_sql("INSERT INTO forma_parte(dni_deportista,id_unidad,rol) VALUES ('12345678Z',1,'Patron')")
        p=s.preparar(self.engine,self.origen,self.destino)
        self.assertEqual(p['bloqueos'],[])
        self.unir(version=p['version'])
        self.assertEqual(len(self.filas('forma_parte')),2)
        self.assertEqual(len(self.filas('participa_en')),2)

    def test_uniones_sucesivas_conservan_las_copias_y_referencias(self):
        with self.engine.begin() as c:c.exec_driver_sql("UPDATE deportista SET dni='TEMP-DEST' WHERE dni='12345678Z'")
        p=s.preparar(self.engine,self.origen,'TEMP-DEST')
        s.unir(self.engine,self.origen,'TEMP-DEST',p['version'],'Primera unión',confirmar=True)
        with self.engine.begin() as c:c.exec_driver_sql("INSERT INTO deportista(dni,nombre,apellidos,id_club) VALUES ('12345678Z','Ana','Pérez García',2)")
        p=s.preparar(self.engine,'TEMP-DEST','12345678Z')
        s.unir(self.engine,'TEMP-DEST','12345678Z',p['version'],'Documento confirmado',confirmar=True)
        copias=self.filas('fusion_deportista')
        self.assertEqual(len(copias),2)
        self.assertEqual({r['dni_deportista'] for r in copias},{'12345678Z'})
        self.assertEqual(copias[0]['documento_conservado'],'TEMP-DEST')
        self.assertEqual(len(self.filas('participa_en')),2)
