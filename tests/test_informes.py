"""Pruebas locales; SQLite adapta los bloqueos específicos de PostgreSQL."""
from datetime import date,timedelta
import unittest
from sqlalchemy import create_engine,event,text
from services import informes as s

class PruebasInformes(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite:///:memory:')
        @event.listens_for(self.engine,'before_cursor_execute',retval=True)
        def adaptar(c,cur,sql,params,ctx,many):
            return sql.replace('public.','').replace(' FOR UPDATE','').replace(' FOR KEY SHARE',''),params
        with self.engine.begin() as c:
            c.exec_driver_sql('PRAGMA foreign_keys=ON')
            c.exec_driver_sql('CREATE TABLE deportista(dni TEXT PRIMARY KEY,fecha_nacimiento DATE)')
            c.exec_driver_sql("INSERT INTO deportista VALUES ('D1','2012-01-04'),('D2',NULL)")
            c.exec_driver_sql('CREATE TABLE tecnico(dni TEXT PRIMARY KEY,nombre TEXT,apellidos TEXT,titulacion TEXT)')
            c.exec_driver_sql("INSERT INTO tecnico VALUES ('T1','Eva','Lago','Técnico de vela'),('T2','Toni','Serra',NULL)")
            c.exec_driver_sql('''CREATE TABLE informe(id_informe INTEGER PRIMARY KEY,fecha DATE NOT NULL,
                estrategia INTEGER,tactica INTEGER,trimado INTEGER,tecnica INTEGER,
                fortalezas TEXT,debilidades TEXT,recomendaciones TEXT,
                dni_deportista TEXT REFERENCES deportista,dni_tecnico TEXT REFERENCES tecnico)''')
        self.campos=dict(fecha=date(2026,10,20),estrategia=4,tactica=3,trimado=5,tecnica=4,
                         fortalezas=' Buena preparación. ',debilidades=' Salidas. ',recomendaciones=' Practicar maniobras. ',dni_deportista='D1',dni_tecnico='T1')
        self.addCleanup(self.engine.dispose)
    def filas(self):
        with self.engine.connect() as c:return [dict(r) for r in c.execute(text('SELECT * FROM informe ORDER BY id_informe')).mappings()]
    def test_informe_completo(self):
        ident=s.crear_informe(self.engine,self.campos)
        f=self.filas()[0]
        self.assertEqual(f['id_informe'],ident)
        self.assertEqual(f['estrategia'],4)
        self.assertEqual(f['fortalezas'],'Buena preparación.')
        self.assertEqual(f['dni_tecnico'],'T1')
    def test_campos_opcionales(self):
        s.crear_informe(self.engine,{**self.campos,**{k:None for k in s.VALORACIONES},**{k:'  ' for k in s.TEXTOS}})
        for k in s.VALORACIONES+s.TEXTOS:self.assertIsNone(self.filas()[0][k])
    def test_escalas_invalidas(self):
        for campo in s.VALORACIONES:
            for valor in [0,6,-1,1.5,True,'4']:
                with self.subTest(campo=campo,valor=valor),self.assertRaises(s.ValidacionError):
                    s.crear_informe(self.engine,{**self.campos,campo:valor})
        self.assertEqual(self.filas(),[])
    def test_limites_validos(self):
        s.crear_informe(self.engine,{**self.campos,'estrategia':1,'tecnica':5})
        self.assertEqual(self.filas()[0]['estrategia'],1)
        self.assertEqual(self.filas()[0]['tecnica'],5)
    def test_texto_invalido(self):
        with self.assertRaises(s.ValidacionError):s.crear_informe(self.engine,{**self.campos,'fortalezas':3})
    def test_fechas_invalidas(self):
        for fecha in [None,'2026-10-20',date.today()+timedelta(days=1),date(2010,1,1)]:
            with self.subTest(fecha=fecha),self.assertRaises(s.ValidacionError):s.crear_informe(self.engine,{**self.campos,'fecha':fecha})
        self.assertEqual(self.filas(),[])
    def test_referencias_inexistentes(self):
        for campo in ['dni_deportista','dni_tecnico']:
            with self.subTest(campo=campo),self.assertRaises(s.ValidacionError):s.crear_informe(self.engine,{**self.campos,campo:'NOEXISTE'})
        self.assertEqual(self.filas(),[])
    def test_referencias_obligatorias(self):
        for campo in ['dni_deportista','dni_tecnico']:
            for valor in [None,' ','X'*21]:
                with self.subTest(campo=campo,valor=valor),self.assertRaises(s.ValidacionError):s.crear_informe(self.engine,{**self.campos,campo:valor})
    def test_duplicado_no_se_inserta(self):
        s.crear_informe(self.engine,self.campos)
        with self.assertRaises(s.ConflictoError):s.crear_informe(self.engine,self.campos)
        self.assertEqual(len(self.filas()),1)
    def test_duplicado_campos_null(self):
        campos={**self.campos,**{k:None for k in s.VALORACIONES+s.TEXTOS}}
        s.crear_informe(self.engine,campos)
        with self.assertRaises(s.ConflictoError):s.crear_informe(self.engine,campos)
        self.assertEqual(len(self.filas()),1)
    def test_diferentes_informes_mismo_dia_conservados(self):
        primero=s.crear_informe(self.engine,self.campos)
        segundo=s.crear_informe(self.engine,{**self.campos,'recomendaciones':'Nuevo objetivo.'})
        tercero=s.crear_informe(self.engine,{**self.campos,'dni_tecnico':'T2'})
        self.assertEqual(len({primero,segundo,tercero}),3)
        self.assertEqual(len(self.filas()),3)
    def test_listados_y_filtro_deportista(self):
        s.crear_informe(self.engine,self.campos)
        tecnicos=s.listar_tecnicos(self.engine)
        self.assertEqual({r['dni'] for r in tecnicos},{'T1','T2'})
        informes=s.listar_informes(self.engine,'D1')
        self.assertEqual(informes[0]['nombre_tecnico'],'Eva')
        self.assertEqual(informes[0]['fecha'],date(2026,10,20))
        self.assertEqual(s.listar_informes(self.engine,'D2'),[])
    def test_nacimiento_desconocido(self):
        s.crear_informe(self.engine,{**self.campos,'dni_deportista':'D2'})
        self.assertEqual(len(self.filas()),1)

if __name__=='__main__':unittest.main(verbosity=2)
