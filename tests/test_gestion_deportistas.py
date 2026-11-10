from datetime import date,timedelta
import unittest
from sqlalchemy import create_engine,event,text
from services import deportistas as s

class PruebasServicio(unittest.TestCase):
    def setUp(self):
        self.e=create_engine('sqlite:///:memory:')
        @event.listens_for(self.e,'before_cursor_execute',retval=True)
        def traducir(conn,cursor,sql,params,ctx,many):return sql.replace('public.',''),params
        with self.e.begin() as c:
            c.exec_driver_sql('PRAGMA foreign_keys=ON')
            c.exec_driver_sql('CREATE TABLE club(id_club INTEGER PRIMARY KEY)')
            c.exec_driver_sql('INSERT INTO club VALUES (9)')
            c.exec_driver_sql('CREATE TABLE deportista(dni TEXT PRIMARY KEY,nombre TEXT NOT NULL,apellidos TEXT NOT NULL,fecha_nacimiento DATE,sexo TEXT,id_club INTEGER REFERENCES club(id_club))')
            c.exec_driver_sql('CREATE TABLE historial(dni TEXT REFERENCES deportista(dni),dato TEXT)')
        self.base=dict(dni=' prueba-001 ',nombre=' Ana ',apellidos=' Lago ',fecha_nacimiento=date(2012,1,4),sexo='Femenino',id_club=9)
        self.addCleanup(self.e.dispose)
    def leer(self):
        with self.e.connect() as c:return dict(c.execute(text('SELECT * FROM deportista')).mappings().one())
    def original(self):
        fila=self.leer()
        if fila['fecha_nacimiento']:fila['fecha_nacimiento']=date.fromisoformat(fila['fecha_nacimiento'])
        return fila
    def test_alta_normalizada(self):
        self.assertEqual(s.crear_deportista(self.e,self.base),'PRUEBA-001')
        self.assertEqual(self.leer()['nombre'],'Ana')
    def test_campos_opcionales(self):
        s.crear_deportista(self.e,{**self.base,'fecha_nacimiento':None,'sexo':None,'id_club':None})
        self.assertIsNone(self.leer()['fecha_nacimiento'])
    def test_duplicado_no_modifica(self):
        s.crear_deportista(self.e,self.base)
        with self.assertRaises(s.ConflictoError):s.crear_deportista(self.e,{**self.base,'nombre':'Otra'})
        self.assertEqual(self.leer()['nombre'],'Ana')
    def test_invalidos_no_insertan(self):
        for cambios in [dict(dni=''),dict(nombre=' '),dict(apellidos='x'*151),dict(fecha_nacimiento=date.today()+timedelta(days=1)),dict(fecha_nacimiento='2012-01-04'),dict(sexo='otro'),dict(id_club=-1)]:
            with self.subTest(cambios=cambios),self.assertRaises(s.ValidacionError):s.crear_deportista(self.e,{**self.base,**cambios})
        with self.e.connect() as c:self.assertEqual(c.execute(text('SELECT COUNT(*) FROM deportista')).scalar_one(),0)
    def test_club_inexistente(self):
        with self.assertRaises(s.ValidacionError):s.crear_deportista(self.e,{**self.base,'id_club':99})
    def test_editar_conserva_relaciones(self):
        s.crear_deportista(self.e,self.base);original=self.original()
        with self.e.begin() as c:c.execute(text("INSERT INTO historial VALUES ('PRUEBA-001','dato')"))
        s.actualizar_deportista(self.e,{**original,'nombre':'Ana María','id_club':None},original)
        self.assertEqual(self.leer()['nombre'],'Ana María')
        with self.e.connect() as c:self.assertEqual(c.execute(text('SELECT dni FROM historial')).scalar_one(),'PRUEBA-001')
    def test_conflicto_optimista(self):
        s.crear_deportista(self.e,self.base);original=self.original()
        s.actualizar_deportista(self.e,{**original,'nombre':'Otra persona'},original)
        with self.assertRaises(s.ConflictoError):s.actualizar_deportista(self.e,{**original,'apellidos':'Cambio tardío'},original)
        self.assertEqual(self.leer()['nombre'],'Otra persona')
        self.assertEqual(self.leer()['apellidos'],'Lago')
    def test_documento_inmutable(self):
        s.crear_deportista(self.e,self.base);original=self.original()
        with self.assertRaises(s.ValidacionError):s.actualizar_deportista(self.e,{**original,'dni':'OTRO'},original)
    def test_actualizacion_opcionales_null(self):
        s.crear_deportista(self.e,{**self.base,'sexo':None,'fecha_nacimiento':None,'id_club':None})
        original=self.original()
        s.actualizar_deportista(self.e,{**original,'nombre':'Actualizado'},original)
        self.assertEqual(self.leer()['nombre'],'Actualizado')

if __name__=='__main__':unittest.main(verbosity=2)
