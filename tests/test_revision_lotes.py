"""Lotes de revisión contra el DDL del proyecto, sin conexiones externas."""
from datetime import date
import unittest

from sqlalchemy import event, text
from unittest.mock import patch

from services import importaciones as base
from services import revision_participantes as individual
from services import revision_lotes as s
from services.deportistas import ConflictoError, ValidacionError
import test_importaciones as fixtures


class RevisionLotes(unittest.TestCase):
    def setUp(self):
        self.db = fixtures.PersistenciaImportaciones()
        self.db.setUp(); self.addCleanup(self.db.doCleanups)
        self.engine = self.db.engine
        self.filas = [self.db.filas[0], {**self.db.filas[0], 'numero_fila': 2,
            'posicion_general': 2, 'participantes': [{'nombre_original': 'Luis Lago', 'club_original': 'Club A'}]}]
        self.ident = self.db.crear(filas=self.filas)

    def resumen(self, ident=None):
        return s.cargar_resumen(self.engine, ident or self.ident)

    def decision_club(self, grupo=None, club=1, recordar=False):
        g = grupo or self.resumen()['grupos_club'][0]
        return dict(normalizado=g['normalizado'], version=g['version'], id_club=club, recordar=recordar)

    def decisiones(self, resumen=None, roles=None):
        salida=[]
        for i,r in enumerate((resumen or self.resumen())['propuestas']):
            if r['propuesta']:
                salida.append(dict(participante=r['participante']['id_participante_importado'],
                    dni=r['propuesta']['dni'], version_ficha=r['propuesta']['version_ficha'],
                    rol=roles[i] if roles else 'Patron'))
        return salida

    def test_preview_solo_lee_y_no_multiplica_consultas_por_participante(self):
        sql=[]
        event.listen(self.engine,'before_cursor_execute',lambda c,cu,s,p,ctx,m:sql.append(s))
        resumen=self.resumen()
        self.assertEqual(len(sql),6)
        self.assertTrue(all(q.strip().startswith('SELECT') for q in sql))
        self.assertEqual(len(resumen['grupos_club']),1)
        self.assertEqual(len(resumen['grupos_club'][0]['participantes']),2)
        self.assertEqual([r['propuesta']['dni'] for r in resumen['propuestas']],['D1','D2'])
        self.assertEqual(self.db.contar('coincidencia_propuesta'),0)
        self.assertEqual(self.db.contar('alias_club'),0)

    def test_clubes_aplica_a_pendientes_sin_modificar_fuente_ni_fichas(self):
        total=s.confirmar_clubes(self.engine,self.ident,[self.decision_club(club=2)],confirmar=True)
        self.assertEqual(total,{'clubes':1,'participantes':2})
        b=base.obtener_borrador(self.engine,self.ident)
        self.assertEqual({p['club_original'] for p in b['participantes']},{'Club A'})
        self.assertEqual({p['id_club_identificado'] for p in b['participantes']},{2})
        self.assertTrue(all(p['dni_deportista_confirmado'] is None for p in b['participantes']))
        with self.engine.connect() as c:
            self.assertEqual(c.exec_driver_sql('SELECT DISTINCT id_club FROM deportista').all(),[(1,)])
        self.assertEqual(self.db.contar('alias_club'),0)

    def test_alias_recordado_reutilizable_y_repetible_sin_duplicar(self):
        decision = self.decision_club(recordar=True)
        s.confirmar_clubes(self.engine,self.ident,[decision],confirmar=True)
        self.assertEqual(self.resumen()['grupos_club'],[])
        with self.assertRaises(ConflictoError):
            s.confirmar_clubes(self.engine,self.ident,[decision],confirmar=True)
        self.assertEqual(self.db.contar('alias_club'),1)
        ident=self.db.crear()
        g=self.resumen(ident)['grupos_club'][0]
        self.assertEqual(g['id_club_propuesto'],1)
        self.assertIn('confirmada',g['motivo'])

    def test_alias_en_otro_contexto_no_se_aplica_globalmente(self):
        base.registrar_alias_club(self.engine,'Abreviatura especial',2,'Otra fuente')
        ident=self.db.crear(filas=[{**self.db.filas[0], 'participantes':[
            dict(nombre_original='Ana Pérez',club_original='Abreviatura especial')]}])
        self.assertIsNone(self.resumen(ident)['grupos_club'][0]['id_club_propuesto'])

    def test_alias_conflictivo_no_se_reemplaza_y_se_permite_decision_local(self):
        base.registrar_alias_club(self.engine,'Club A',1)
        with self.assertRaises(ConflictoError):
            s.confirmar_clubes(self.engine,self.ident,[self.decision_club(club=2,recordar=True)],confirmar=True)
        self.assertTrue(all(p['id_club_identificado'] is None for p in base.obtener_borrador(self.engine,self.ident)['participantes']))
        s.confirmar_clubes(self.engine,self.ident,[self.decision_club(club=2)],confirmar=True)
        with self.engine.connect() as c:
            self.assertEqual(c.exec_driver_sql('SELECT id_club FROM alias_club').scalar_one(),1)

    def test_club_explicito_prevalece_sobre_alias_global(self):
        base.registrar_alias_club(self.engine,'Club A',1)
        with self.engine.begin() as c:
            c.exec_driver_sql("INSERT INTO deportista(dni,nombre,apellidos,id_club) VALUES ('D3','Ana','Pérez',2)")
        s.confirmar_clubes(self.engine,self.ident,[self.decision_club(club=2)],confirmar=True)
        self.assertEqual(self.resumen()['propuestas'][0]['propuesta']['dni'],'D3')

    def test_grupo_obsoleto_y_fallo_tardio_revierten_alias_y_todo_el_lote(self):
        with self.engine.begin() as c:
            c.exec_driver_sql("UPDATE participante_importado SET club_original='Club B' WHERE nombre_original='Luis Lago'")
        grupos=self.resumen()['grupos_club']
        decisiones=[self.decision_club(grupos[0],recordar=True),self.decision_club(grupos[1],club=999)]
        with self.assertRaises(ValidacionError):
            s.confirmar_clubes(self.engine,self.ident,decisiones,confirmar=True)
        self.assertEqual(self.db.contar('alias_club'),0)
        self.assertTrue(all(p['id_club_identificado'] is None for p in base.obtener_borrador(self.engine,self.ident)['participantes']))
        d=self.decision_club(grupos[0])
        p=individual.cargar_revision(self.engine,self.ident)['participantes_revision'][0]
        individual.guardar_revision(self.engine,p['id_participante_importado'],'pendiente',{'nombre':'Ana María'},p['version'])
        with self.assertRaises(ConflictoError):
            s.confirmar_clubes(self.engine,self.ident,[d],confirmar=True)

    def test_sin_club_no_se_propaga_un_club_inventado(self):
        with self.engine.begin() as c:c.exec_driver_sql('UPDATE participante_importado SET club_original=NULL')
        self.assertEqual(self.resumen()['grupos_club'],[])
        self.assertEqual(len(self.resumen()['propuestas']),2)

    def test_excluidos_y_ya_confirmados_quedan_fuera(self):
        r=self.resumen(); d=self.decisiones(r)[:1]
        s.confirmar_vinculos(self.engine,self.ident,d,r['version'],confirmar=True)
        r=self.resumen()
        self.assertEqual(len(r['propuestas']),1)
        self.assertEqual(len(r['grupos_club'][0]['participantes']),1)
        with self.engine.begin() as c:
            c.exec_driver_sql("UPDATE fila_clasificacion_importada SET cumple_criterio=0,estado='excluida' WHERE numero_fila=2")
        self.assertEqual(self.resumen()['propuestas'],[])
        self.assertEqual(self.resumen()['grupos_club'],[])

    def test_vincular_lote_prepara_resultados_sin_recrear_deportistas(self):
        r=self.resumen()
        total=s.confirmar_vinculos(self.engine,self.ident,self.decisiones(r),r['version'],confirmar=True)
        self.assertEqual(total,{'vinculados':2,'resultados_preparados':2})
        self.assertEqual(self.db.contar('deportista'),2)
        self.assertEqual(self.db.contar('unidad_competitiva'),0)
        self.assertEqual(self.db.contar('participa_en'),0)
        self.assertEqual({p['dni_deportista_confirmado'] for p in base.obtener_borrador(self.engine,self.ident)['participantes']},{'D1','D2'})

    def test_abreviaturas_de_clubes_apuntan_al_catalogo(self):
        pares=[('M.R.C.Y.B.','Monte Real Club de Yates de Baiona'),
               ('CM Canido','Club Marítimo de Canido'),
               ('C.V.F As Pontes','Club de Vela Fluvial de As Pontes'),
               ('C.V.F. As Pontes','Club Vela Fluvial As Pontes')]
        for origen,nombre in pares:
            with self.subTest(origen=origen,nombre=nombre):
                g=dict(normalizado=individual.normalizar(origen),textos=[origen],participantes=[{'id_club_identificado':None}])
                self.assertEqual(s._sugerir_club(g,[dict(id_club=7,nombre=nombre)],[])[0],7)
                self.assertIsNone(s._sugerir_club(g,[dict(id_club=7,nombre=nombre),dict(id_club=8,nombre=nombre)],[])[0])

    def test_vincular_e_incorporar_resultados_en_una_transaccion(self):
        from services import resultados_importados as resultados
        # La clase de prueba contiene el mismo SQL que PostgreSQL, adaptado a SQLite.
        event.listen(self.engine,'before_cursor_execute',lambda c,cu,q,p,ctx,m:(q.replace(' FOR UPDATE',''),p),retval=True)
        r=self.resumen()
        campos=dict(nombre='Vigo',fecha_inicio=date(2026,10,3),fecha_fin=date(2026,10,4),localidad='Vigo',tipo_clasificacion='definitiva')
        salida=s.confirmar_vinculos(self.engine,self.ident,self.decisiones(r),r['version'],confirmar=True,datos_resultado=campos)
        self.assertEqual(salida['resultados_incorporados'],2)
        self.assertEqual(self.db.contar('participa_en'),2)
        self.assertEqual(self.db.contar('deportista'),2)
        self.assertEqual(base.obtener_borrador(self.engine,self.ident)['importacion']['estado'],'completada')

    def test_fallo_de_resultados_revierte_todas_las_vinculaciones(self):
        from services import resultados_importados as resultados
        r=self.resumen()
        with patch.object(resultados,'incorporar_en_conexion',side_effect=ConflictoError('Equipo incompatible')):
            with self.assertRaises(ConflictoError):
                s.confirmar_vinculos(self.engine,self.ident,self.decisiones(r),r['version'],confirmar=True,datos_resultado=dict(
                    nombre='Vigo',fecha_inicio=date(2026,10,3),fecha_fin=date(2026,10,4),localidad='Vigo',tipo_clasificacion='definitiva'))
        self.assertTrue(all(p['dni_deportista_confirmado'] is None for p in base.obtener_borrador(self.engine,self.ident)['participantes']))
        self.assertEqual(self.db.contar('coincidencia_propuesta'),0)
        self.assertEqual(self.db.contar('participa_en'),0)

    def test_vinculos_agrupados_evitan_consultas_individuales_repetidas(self):
        r=self.resumen(); consultas=[]
        event.listen(self.engine,'before_cursor_execute',lambda c,cu,q,p,ctx,m:consultas.append(q))
        s.confirmar_vinculos(self.engine,self.ident,self.decisiones(r),r['version'],confirmar=True)
        self.assertLessEqual(len(consultas),16)
        self.assertEqual(sum('UPDATE public.participante_importado' in q or 'UPDATE participante_importado' in q for q in consultas),1)

    def preparar_altas(self, nombres=('Zacarías Velázquez Taboada','Úrsula Abad Montoro')):
        with self.engine.begin() as c:
            for numero,nombre in enumerate(nombres,1):
                c.execute(text('UPDATE participante_importado SET nombre_original=:n,id_club_identificado=1 WHERE id_fila IN (SELECT id_fila FROM fila_clasificacion_importada WHERE id_importacion=:i AND numero_fila=:f)'),
                          {'n':nombre,'i':self.ident,'f':numero})
        r=self.resumen()
        decisiones=[]
        for p in r['propuestas']:
            nombre,apellidos=p['participante']['nombre_original'].split(' ',1)
            decisiones.append(dict(participante=p['participante']['id_participante_importado'],version=p['version'],campos=dict(
                nombre=nombre,apellidos=apellidos,id_club=1,rol_propuesto='Patron',fecha_nacimiento=None,sexo=None)))
        return r,decisiones

    def test_altas_por_lote_sin_dni_y_actualizacion_con_historial(self):
        from services import deportistas
        event.listen(self.engine,'before_cursor_execute',lambda c,cu,q,p,ctx,m:(q.replace(' FOR UPDATE',''),p),retval=True)
        r,decisiones=self.preparar_altas()
        campos=dict(nombre='Vigo nuevas',fecha_inicio=date(2026,10,3),fecha_fin=date(2026,10,4),localidad='Vigo',tipo_clasificacion='definitiva')
        salida=s.crear_nuevos(self.engine,self.ident,decisiones,r['version'],campos,confirmar=True)
        self.assertEqual(salida,dict(creados=2,resultados_incorporados=2))
        b=base.obtener_borrador(self.engine,self.ident)
        for p in b['participantes']:self.assertRegex(p['dni_deportista_confirmado'],r'^TEMP-[A-F0-9]{12}$')
        with self.engine.connect() as c:original=dict(c.execute(text('SELECT * FROM deportista WHERE dni=:d'),{'d':b['participantes'][0]['dni_deportista_confirmado']}).mappings().one())
        deportistas.actualizar_deportista(self.engine,{**original,'dni':'12345678Z'},original)
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text("SELECT COUNT(*) FROM forma_parte WHERE dni_deportista='12345678Z'")).scalar_one(),1)
            self.assertEqual(c.execute(text("SELECT COUNT(*) FROM participante_importado WHERE dni_deportista_confirmado='12345678Z'")).scalar_one(),1)
            self.assertEqual(c.execute(text('SELECT COUNT(*) FROM participa_en')).scalar_one(),2)

    def test_altas_por_lote_con_identidad_similar_no_crea_duplicados(self):
        r,decisiones=self.preparar_altas(('Zacarías Velázquez Taboada','Ana Pérez'))
        campos=dict(nombre='Vigo nuevas',fecha_inicio=date(2026,10,3),fecha_fin=date(2026,10,4),localidad='Vigo',tipo_clasificacion='definitiva')
        with self.assertRaises(ConflictoError):s.crear_nuevos(self.engine,self.ident,decisiones,r['version'],campos,confirmar=True)
        self.assertEqual(self.db.contar('deportista'),2)
        self.assertTrue(all(p['dni_deportista_confirmado'] is None for p in base.obtener_borrador(self.engine,self.ident)['participantes']))

    def test_consentimiento_y_seleccion_explicitos(self):
        r=self.resumen()
        with self.assertRaises(ValidacionError):s.confirmar_vinculos(self.engine,self.ident,self.decisiones(r),r['version'])
        with self.assertRaises(ValidacionError):s.confirmar_clubes(self.engine,self.ident,[self.decision_club()])
        with self.assertRaises(ValidacionError):s.confirmar_vinculos(self.engine,self.ident,[],r['version'],confirmar=True)
        self.assertTrue(all(p['dni_deportista_confirmado'] is None for p in base.obtener_borrador(self.engine,self.ident)['participantes']))

    def test_borrador_obsoleto_y_ficha_modificada_no_se_vinculan(self):
        r=self.resumen()
        with self.engine.begin() as c:c.exec_driver_sql("UPDATE deportista SET apellidos='Pérez García' WHERE dni='D1'")
        with self.assertRaises(ConflictoError):
            s.confirmar_vinculos(self.engine,self.ident,self.decisiones(r),r['version'],confirmar=True)
        r=self.resumen()
        s.confirmar_clubes(self.engine,self.ident,[self.decision_club()],confirmar=True)
        with self.assertRaises(ConflictoError):
            s.confirmar_vinculos(self.engine,self.ident,self.decisiones(r),r['version'],confirmar=True)

    def test_homonimos_no_producen_propuesta_arbitraria(self):
        with self.engine.begin() as c:
            c.exec_driver_sql("INSERT INTO deportista(dni,nombre,apellidos,id_club) VALUES ('D3','Ana','Pérez',1)")
        r=self.resumen()
        self.assertIsNone(r['propuestas'][0]['propuesta'])
        self.assertIn('ambiguas',r['propuestas'][0]['motivo'])

    def test_misma_ficha_en_dos_posiciones_se_rechaza_antes_de_guardar(self):
        with self.engine.begin() as c:c.exec_driver_sql("UPDATE participante_importado SET nombre_original='Ana Pérez'")
        r=self.resumen()
        self.assertTrue(all(p['propuesta'] is None for p in r['propuestas']))
        decisiones=[dict(participante=p['participante']['id_participante_importado'],dni='D1',version_ficha='obsoleta',rol='Patron') for p in r['propuestas']]
        with self.assertRaises(ConflictoError):
            s.confirmar_vinculos(self.engine,self.ident,decisiones,r['version'],confirmar=True)
        self.assertEqual(self.db.contar('coincidencia_propuesta'),0)

    def test_repeticion_del_lote_no_sobrescribe_ni_duplica(self):
        r=self.resumen(); ds=self.decisiones(r)
        s.confirmar_vinculos(self.engine,self.ident,ds,r['version'],confirmar=True)
        with self.assertRaises(ConflictoError):s.confirmar_vinculos(self.engine,self.ident,ds,r['version'],confirmar=True)
        self.assertEqual(self.db.contar('deportista'),2)

    def test_dobles_roles_completos_obligatorios_y_reversion_del_lote(self):
        ident=self.db.crear(campos={**self.db.campos,'id_clase':2},filas=[{**self.db.filas[0], 'participantes':[
            dict(nombre_original='Ana Pérez'),dict(nombre_original='Luis Lago')]}])
        r=self.resumen(ident)
        with self.assertRaises(ValidacionError):
            s.confirmar_vinculos(self.engine,ident,self.decisiones(r,['Patron','Patron']),r['version'],confirmar=True)
        self.assertTrue(all(p['dni_deportista_confirmado'] is None for p in base.obtener_borrador(self.engine,ident)['participantes']))
        self.assertEqual(self.db.contar('coincidencia_propuesta'),0)
        total=s.confirmar_vinculos(self.engine,ident,self.decisiones(r,['Patron','Tripulante']),r['version'],confirmar=True)
        self.assertEqual(total,{'vinculados':2,'resultados_preparados':1})

    def test_nacimiento_incompatible_revierte_vinculaciones_anteriores(self):
        with self.engine.begin() as c:
            c.exec_driver_sql("UPDATE importacion_clasificacion SET fecha_inicio_propuesta='2026-10-01' WHERE id_importacion=1")
            c.exec_driver_sql("UPDATE deportista SET fecha_nacimiento='2026-10-05' WHERE dni='D2'")
        r=self.resumen()
        with self.assertRaises(ValidacionError):
            s.confirmar_vinculos(self.engine,self.ident,self.decisiones(r),r['version'],confirmar=True)
        self.assertTrue(all(p['dni_deportista_confirmado'] is None for p in base.obtener_borrador(self.engine,self.ident)['participantes']))

    def test_importacion_cerrada_no_admite_lotes(self):
        r=self.resumen()
        with self.engine.begin() as c:c.exec_driver_sql("UPDATE importacion_clasificacion SET estado='cancelada'")
        with self.assertRaises(ConflictoError):
            s.confirmar_vinculos(self.engine,self.ident,self.decisiones(r),r['version'],confirmar=True)
