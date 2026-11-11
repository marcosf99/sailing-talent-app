"""Pruebas locales con SQLite; se adapta FOR UPDATE, específico de PostgreSQL."""
from datetime import date, timedelta
from decimal import Decimal
import unittest

from sqlalchemy import create_engine, event, text
from services import antropometria as s


class PruebasAntropometria(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        @event.listens_for(self.engine, 'before_cursor_execute', retval=True)
        def adaptar(conn, cursor, sql, params, context, many):
            sql = sql.replace('public.', '').replace(' FOR UPDATE', '')
            params = tuple(float(v) if isinstance(v, Decimal) else v for v in params)
            return sql, params
        with self.engine.begin() as c:
            c.exec_driver_sql('PRAGMA foreign_keys=ON')
            c.exec_driver_sql('CREATE TABLE deportista(dni TEXT PRIMARY KEY, fecha_nacimiento DATE)')
            c.exec_driver_sql("INSERT INTO deportista VALUES ('DEMO001','2012-01-04'),('DEMO002',NULL)")
            c.exec_driver_sql('''CREATE TABLE registro_antropometrico(
                id_registro INTEGER PRIMARY KEY, fecha DATE NOT NULL,
                altura NUMERIC(5,2), peso NUMERIC(5,2), envergadura NUMERIC(5,2),
                porcentaje_graso NUMERIC(5,2), dni_deportista TEXT REFERENCES deportista(dni))''')
        self.campos = dict(dni_deportista='DEMO001', fecha=date(2026, 10, 15),
                           altura=148, peso=39, envergadura=151, porcentaje_graso=18)
        self.addCleanup(self.engine.dispose)

    def filas(self):
        with self.engine.connect() as c:
            return [dict(r) for r in c.execute(text('SELECT * FROM registro_antropometrico ORDER BY id_registro')).mappings()]

    def test_registro_completo(self):
        identificador = s.crear_registro(self.engine, self.campos)
        self.assertEqual(self.filas()[0]['id_registro'], identificador)
        self.assertEqual(self.filas()[0]['altura'], 148)

    def test_medicion_parcial(self):
        s.crear_registro(self.engine, {**self.campos, 'peso':None, 'envergadura':None, 'porcentaje_graso':None})
        self.assertIsNone(self.filas()[0]['peso'])

    def test_conserva_historial(self):
        primero=s.crear_registro(self.engine,self.campos)
        segundo=s.crear_registro(self.engine,{**self.campos,'fecha':date(2026,11,1),'altura':149})
        self.assertNotEqual(primero,segundo)
        self.assertEqual([r['altura'] for r in self.filas()],[148,149])

    def test_duplicado_exacto_rechazado(self):
        s.crear_registro(self.engine,self.campos)
        with self.assertRaises(s.ConflictoError):
            s.crear_registro(self.engine,{**self.campos,'altura':Decimal('148.00')})
        self.assertEqual(len(self.filas()),1)

    def test_duplicado_con_null_rechazado(self):
        campos={**self.campos,'altura':None,'envergadura':None,'porcentaje_graso':None}
        s.crear_registro(self.engine,campos)
        with self.assertRaises(s.ConflictoError):s.crear_registro(self.engine,campos)
        self.assertEqual(len(self.filas()),1)

    def test_misma_fecha_valores_distintos(self):
        s.crear_registro(self.engine,self.campos)
        s.crear_registro(self.engine,{**self.campos,'peso':40})
        self.assertEqual(len(self.filas()),2)

    def test_deportista_inexistente(self):
        with self.assertRaises(s.ValidacionError):
            s.crear_registro(self.engine,{**self.campos,'dni_deportista':'NOEXISTE'})
        self.assertEqual(self.filas(),[])

    def test_antes_del_nacimiento(self):
        with self.assertRaises(s.ValidacionError):
            s.crear_registro(self.engine,{**self.campos,'fecha':date(2011,1,1)})
        self.assertEqual(self.filas(),[])

    def test_nacimiento_desconocido(self):
        s.crear_registro(self.engine,{**self.campos,'dni_deportista':'DEMO002'})
        self.assertEqual(len(self.filas()),1)

    def test_fecha_futura_o_invalida(self):
        for fecha in [None,'2026-11-11',date.today()+timedelta(days=1)]:
            with self.subTest(fecha=fecha),self.assertRaises(s.ValidacionError):
                s.crear_registro(self.engine,{**self.campos,'fecha':fecha})
        self.assertEqual(self.filas(),[])

    def test_sin_medidas(self):
        with self.assertRaises(s.ValidacionError):
            s.crear_registro(self.engine,{**self.campos,**{k:None for k in s.MEDIDAS}})

    def test_rangos_y_precision(self):
        for campo,valor in [('altura',0),('peso',-1),('envergadura',1000),('porcentaje_graso',101),('porcentaje_graso',-1),('altura',True),('peso',float('inf')),('altura',float('nan')),('peso','texto'),('peso',Decimal('39.123'))]:
            with self.subTest(campo=campo,valor=valor),self.assertRaises(s.ValidacionError):
                s.crear_registro(self.engine,{**self.campos,campo:valor})
        self.assertEqual(self.filas(),[])

    def test_grasa_cero_y_dos_decimales(self):
        s.crear_registro(self.engine,{**self.campos,'porcentaje_graso':0,'peso':Decimal('39.25')})
        self.assertEqual(self.filas()[0]['porcentaje_graso'],0)
        self.assertEqual(self.filas()[0]['peso'],39.25)


if __name__=='__main__':unittest.main(verbosity=2)
