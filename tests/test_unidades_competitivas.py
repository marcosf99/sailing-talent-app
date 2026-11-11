"""Pruebas transaccionales locales; SQLite adapta bloqueos de PostgreSQL."""
from datetime import date,timedelta
import unittest
from sqlalchemy import create_engine,event,text
from services import unidades_competitivas as s
from services import edad_clases as edades

class PruebasUnidades(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite:///:memory:')
        @event.listens_for(self.engine,'before_cursor_execute',retval=True)
        def adaptar(c,cur,sql,params,ctx,many):
            return sql.replace('public.','').replace(' FOR UPDATE','').replace(' FOR SHARE',''),params
        with self.engine.begin() as c:
            c.exec_driver_sql('PRAGMA foreign_keys=ON')
            for sql in [
                'CREATE TABLE clase(id_clase INTEGER PRIMARY KEY,nombre TEXT,numero_tripulantes INTEGER)',
                "INSERT INTO clase VALUES (1,'Optimist',1),(2,'420',2),(3,'ILCA 4',1),(4,'Otro',3)",
                'CREATE TABLE deportista(dni TEXT PRIMARY KEY,nombre TEXT,apellidos TEXT,fecha_nacimiento DATE)',
                "INSERT INTO deportista VALUES ('D1','Ana','Lago','2012-01-01'),('D2','Brais','Rey','2011-02-01'),('D3','Iago','Vidal',NULL)",
                'CREATE TABLE unidad_competitiva(id_unidad INTEGER PRIMARY KEY,fecha_inicio DATE NOT NULL,fecha_fin DATE,id_clase INTEGER REFERENCES clase)',
                'CREATE TABLE forma_parte(dni_deportista TEXT REFERENCES deportista,id_unidad INTEGER REFERENCES unidad_competitiva,rol TEXT,PRIMARY KEY(dni_deportista,id_unidad))',
                'CREATE TABLE competicion(id_competicion INTEGER PRIMARY KEY,fecha_fin DATE)',
                'CREATE TABLE participa_en(id_unidad INTEGER REFERENCES unidad_competitiva,id_competicion INTEGER REFERENCES competicion,posicion_general INTEGER,PRIMARY KEY(id_unidad,id_competicion))',
            ]:c.exec_driver_sql(sql)
        self.campos=dict(id_clase=1,fecha_inicio=date(2026,1,1),patron='D1',tripulante=None)
        self.addCleanup(self.engine.dispose)
    def consulta(self,sql):
        with self.engine.connect() as c:return [dict(r) for r in c.execute(text(sql)).mappings()]
    def test_crear_individual(self):
        ident=s.crear_unidad(self.engine,self.campos)
        self.assertEqual(self.consulta('SELECT * FROM forma_parte'),[dict(dni_deportista='D1',id_unidad=ident,rol='Patron')])
    def test_crear_doble(self):
        s.crear_unidad(self.engine,{**self.campos,'id_clase':2,'tripulante':'D2'})
        self.assertEqual({r['rol'] for r in self.consulta('SELECT * FROM forma_parte')},{'Patron','Tripulante'})
    def test_doble_no_permite_mismo_miembro(self):
        with self.assertRaises(s.ValidacionError):s.crear_unidad(self.engine,{**self.campos,'id_clase':2,'tripulante':'D1'})
    def test_numero_tripulantes_exacto(self):
        for cambios in [dict(id_clase=2),dict(tripulante='D2'),dict(id_clase=4,tripulante='D2')]:
            with self.subTest(cambios=cambios),self.assertRaises(s.ValidacionError):s.crear_unidad(self.engine,{**self.campos,**cambios})
    def test_clase_o_deportista_inexistente(self):
        for cambios in [dict(id_clase=99),dict(patron='NOEXISTE'),dict(patron=None)]:
            with self.subTest(cambios=cambios),self.assertRaises(s.ValidacionError):s.crear_unidad(self.engine,{**self.campos,**cambios})
    def test_fecha_futura_o_anterior_nacimiento(self):
        for fecha in [date.today()+timedelta(days=1),date(2010,1,1),'2026-01-01',None]:
            with self.subTest(fecha=fecha),self.assertRaises(s.ValidacionError):s.crear_unidad(self.engine,{**self.campos,'fecha_inicio':fecha})
    def test_nacimiento_desconocido(self):
        s.crear_unidad(self.engine,{**self.campos,'patron':'D3'})
        self.assertEqual(len(self.consulta('SELECT * FROM unidad_competitiva')),1)
    def test_rechaza_solapamiento(self):
        s.crear_unidad(self.engine,self.campos)
        with self.assertRaises(s.ConflictoError):s.crear_unidad(self.engine,{**self.campos,'fecha_inicio':date(2026,5,1)})
        self.assertEqual(len(self.consulta('SELECT * FROM unidad_competitiva')),1)
    def test_fechas_inclusivas_y_nueva_unidad(self):
        ident=s.crear_unidad(self.engine,self.campos)
        s.finalizar_unidad(self.engine,ident,date(2026,2,1))
        with self.assertRaises(s.ConflictoError):s.crear_unidad(self.engine,{**self.campos,'fecha_inicio':date(2026,2,1)})
        s.crear_unidad(self.engine,{**self.campos,'fecha_inicio':date(2026,2,2)})
        self.assertEqual(len(self.consulta('SELECT * FROM unidad_competitiva')),2)
    def test_otras_clases_permitidas(self):
        s.crear_unidad(self.engine,self.campos)
        s.crear_unidad(self.engine,{**self.campos,'id_clase':3})
        self.assertEqual(len(self.consulta('SELECT * FROM unidad_competitiva')),2)
    def test_no_solapa_una_unidad_historica(self):
        ident=s.crear_unidad(self.engine,self.campos)
        s.finalizar_unidad(self.engine,ident,date(2026,3,1))
        with self.assertRaises(s.ConflictoError):s.crear_unidad(self.engine,{**self.campos,'fecha_inicio':date(2025,1,1)})
    def test_finalizar_conserva_miembros_y_resultados(self):
        ident=s.crear_unidad(self.engine,self.campos)
        with self.engine.begin() as c:
            c.exec_driver_sql("INSERT INTO competicion VALUES (1,'2026-05-03')")
            c.execute(text('INSERT INTO participa_en VALUES (:u,1,2)'),{'u':ident})
        with self.assertRaises(s.ValidacionError):s.finalizar_unidad(self.engine,ident,date(2026,5,2))
        s.finalizar_unidad(self.engine,ident,date(2026,5,3))
        self.assertEqual(len(self.consulta('SELECT * FROM participa_en')),1)
        self.assertEqual(len(self.consulta('SELECT * FROM forma_parte')),1)
        self.assertEqual(self.consulta('SELECT fecha_fin FROM unidad_competitiva')[0]['fecha_fin'],'2026-05-03')
    def test_finalizacion_invalida(self):
        ident=s.crear_unidad(self.engine,self.campos)
        for fecha in [date(2025,12,31),date.today()+timedelta(days=1),None]:
            with self.subTest(fecha=fecha),self.assertRaises(s.ValidacionError):s.finalizar_unidad(self.engine,ident,fecha)
        self.assertIsNone(self.consulta('SELECT fecha_fin FROM unidad_competitiva')[0]['fecha_fin'])
    def test_finalizacion_repetida_no_cambia_fecha(self):
        ident=s.crear_unidad(self.engine,self.campos)
        s.finalizar_unidad(self.engine,ident,date(2026,5,1))
        with self.assertRaises(s.ConflictoError):s.finalizar_unidad(self.engine,ident,date(2026,6,1))
        self.assertEqual(self.consulta('SELECT fecha_fin FROM unidad_competitiva')[0]['fecha_fin'],'2026-05-01')
    def test_finalizar_inexistente(self):
        with self.assertRaises(s.ConflictoError):s.finalizar_unidad(self.engine,99,date(2026,5,1))
    def test_rollback_equipo_incompleto(self):
        with self.engine.begin() as c:
            c.exec_driver_sql("CREATE TRIGGER falla BEFORE INSERT ON forma_parte WHEN NEW.dni_deportista='D2' BEGIN SELECT RAISE(ABORT,'fallo simulado'); END")
        with self.assertRaises(s.ConflictoError):s.crear_unidad(self.engine,{**self.campos,'id_clase':2,'tripulante':'D2'})
        self.assertEqual(self.consulta('SELECT * FROM unidad_competitiva'),[])
        self.assertEqual(self.consulta('SELECT * FROM forma_parte'),[])
    def test_listado_y_filtro(self):
        ident=s.crear_unidad(self.engine,{**self.campos,'id_clase':2,'tripulante':'D2'})
        filas=s.listar_unidades(self.engine,2)
        self.assertEqual(filas[0]['id_unidad'],ident)
        self.assertEqual(filas[0]['fecha_inicio'],date(2026,1,1))
        self.assertEqual(len(filas[0]['miembros']),2)
        self.assertEqual(s.listar_unidades(self.engine,1),[])

    def test_optimist_no_guarda_limite_futuro(self):
        s.crear_unidad(self.engine,self.campos)
        self.assertIsNone(self.consulta('SELECT fecha_fin FROM unidad_competitiva')[0]['fecha_fin'])
        self.assertEqual(edades.pendientes_por_edad(self.engine,date(2026,12,31)),[])

    def test_limite_es_ano_14_no_el_cumpleanos(self):
        self.assertEqual(edades.limite_edad('Optimist',date(2012,12,30)),date(2026,12,31))
        self.assertEqual(edades.limite_edad('Optimist',date(2012,1,1)),date(2026,12,31))
        self.assertEqual(edades.limite_edad('Optimist',date(2012,2,29)),date(2026,12,31))
        self.assertIsNone(edades.fin_vencido(date(2026,12,31),date(2026,12,31)))
        self.assertEqual(edades.fin_vencido(date(2026,12,31),date(2027,1,1)),date(2026,12,31))

    def test_cierre_por_edad_solo_cuando_ha_vencido(self):
        ident=s.crear_unidad(self.engine,self.campos)
        self.assertEqual(edades.cerrar_vencidas(self.engine,date(2026,11,11))['cerradas'],[])
        self.assertIsNone(self.consulta('SELECT fecha_fin FROM unidad_competitiva')[0]['fecha_fin'])
        resultado=edades.cerrar_vencidas(self.engine,date(2027,1,1))
        self.assertEqual(resultado['cerradas'],[ident])
        self.assertEqual(self.consulta('SELECT fecha_fin FROM unidad_competitiva')[0]['fecha_fin'],'2026-12-31')
        self.assertEqual(edades.cerrar_vencidas(self.engine,date(2027,1,2))['cerradas'],[])

    def test_cierre_manual_anterior_no_se_sobrescribe(self):
        ident=s.crear_unidad(self.engine,self.campos)
        s.finalizar_unidad(self.engine,ident,date(2026,5,1))
        self.assertEqual(edades.cerrar_vencidas(self.engine,date(2027,1,1))['cerradas'],[])
        self.assertEqual(self.consulta('SELECT fecha_fin FROM unidad_competitiva')[0]['fecha_fin'],'2026-05-01')

    def test_sin_nacimiento_y_otras_clases_no_cierran_por_edad(self):
        s.crear_unidad(self.engine,{**self.campos,'patron':'D3'})
        s.crear_unidad(self.engine,{**self.campos,'id_clase':3})
        self.assertEqual(edades.cerrar_vencidas(self.engine,date(2035,1,1))['cerradas'],[])
        self.assertTrue(all(u['fecha_fin'] is None for u in self.consulta('SELECT fecha_fin FROM unidad_competitiva')))

    def test_edad_incompatible_no_crea_unidad(self):
        with self.engine.begin() as c:
            c.exec_driver_sql("UPDATE deportista SET fecha_nacimiento='2011-12-30' WHERE dni='D1'")
        with self.assertRaisesRegex(s.ValidacionError,'Optimist'):
            s.crear_unidad(self.engine,self.campos)
        self.assertEqual(self.consulta('SELECT * FROM unidad_competitiva'),[])
        s.crear_unidad(self.engine,{**self.campos,'id_clase':3})
        self.assertIsNone(self.consulta('SELECT fecha_fin FROM unidad_competitiva')[0]['fecha_fin'])

    def test_unidad_historica_optimist_con_limite_ya_pasado(self):
        s.crear_unidad(self.engine,{**self.campos,'patron':'D2','fecha_inicio':date(2025,1,1)})
        self.assertEqual(self.consulta('SELECT fecha_fin FROM unidad_competitiva')[0]['fecha_fin'],'2025-12-31')

    def test_cierre_edad_preserva_resultados_incompatibles_y_avisa(self):
        ident=s.crear_unidad(self.engine,self.campos)
        with self.engine.begin() as c:
            c.exec_driver_sql("INSERT INTO competicion VALUES (1,'2027-01-03')")
            c.execute(text('INSERT INTO participa_en VALUES (:u,1,2)'),{'u':ident})
        resultado=edades.cerrar_vencidas(self.engine,date(2027,1,4))
        self.assertEqual(resultado['cerradas'],[])
        self.assertEqual(len(resultado['incidencias']),1)
        self.assertIsNone(self.consulta('SELECT fecha_fin FROM unidad_competitiva')[0]['fecha_fin'])
        self.assertEqual(len(self.consulta('SELECT * FROM participa_en')),1)

    def test_cierre_edad_no_deja_fin_anterior_inicio(self):
        with self.engine.begin() as c:
            c.exec_driver_sql("INSERT INTO unidad_competitiva VALUES (1,'2027-01-01',NULL,1)")
            c.exec_driver_sql("INSERT INTO forma_parte VALUES ('D1',1,'Patron')")
        resultado=edades.cerrar_vencidas(self.engine,date(2027,1,4))
        self.assertEqual(resultado['cerradas'],[])
        self.assertEqual(len(resultado['incidencias']),1)

if __name__=='__main__':unittest.main(verbosity=2)
