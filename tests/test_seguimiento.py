"""Exploración en una consulta, sin multiplicar resultados por equipos o clases."""
from datetime import date
import unittest
from sqlalchemy import event
from services import seguimiento as s
import test_importaciones as fixtures


class Seguimiento(unittest.TestCase):
    def setUp(self):
        self.db=fixtures.PersistenciaImportaciones();self.db.setUp();self.addCleanup(self.db.doCleanups)
        self.engine=self.db.engine
        # Solo el agregado de textos cambia de sintaxis en SQLite.
        event.listen(self.engine,'before_cursor_execute',lambda c,cu,q,p,ctx,m:(
            q.replace("STRING_AGG(DISTINCT cl.nombre, ', ' ORDER BY cl.nombre)",
                      'GROUP_CONCAT(DISTINCT cl.nombre)'),p),retval=True)
        with self.engine.begin() as c:
            c.exec_driver_sql("UPDATE deportista SET fecha_nacimiento='2012-01-04' WHERE dni='D1'")
            c.exec_driver_sql("UPDATE deportista SET id_club=2,fecha_nacimiento=NULL WHERE dni='D2'")
            c.exec_driver_sql("INSERT INTO unidad_competitiva(id_unidad,id_clase,fecha_inicio,fecha_fin) VALUES (1,1,'2025-01-01','2025-12-31'),(2,2,'2026-01-01',NULL),(3,2,'2026-02-01',NULL)")
            c.exec_driver_sql("INSERT INTO forma_parte(dni_deportista,id_unidad,rol) VALUES ('D1',1,'Patron'),('D1',2,'Patron'),('D2',2,'Tripulante'),('D1',3,'Patron')")
            c.exec_driver_sql("INSERT INTO competicion(id_competicion,nombre,fecha_inicio,fecha_fin,nivel,id_clase) VALUES (2,'Anterior','2025-06-01','2025-06-02','Nacional',1),(3,'Internacional','2026-10-10','2026-10-11','Internacional',2),(4,'Futura','2027-01-01','2027-01-02','Nacional',2)")
            c.exec_driver_sql("INSERT INTO participa_en(id_unidad,id_competicion,posicion_general,puntos) VALUES (1,2,3,10),(2,1,8,12),(3,1,10,14),(2,3,5,20),(2,4,1,2)")

    def leer(self,**filtros):return s.listar_regatistas(self.engine,fecha=date(2026,11,1),**filtros)

    def test_una_fila_por_persona_y_competicion_sin_duplicados(self):
        sql=[]
        event.listen(self.engine,'before_cursor_execute',lambda c,cu,q,p,ctx,m:sql.append(q))
        filas={r['dni']:r for r in self.leer()}
        self.assertEqual(len(sql),1)
        self.assertEqual(len(filas),2)
        a=filas['D1']
        self.assertEqual((a['participaciones'],a['nacionales'],a['internacionales']),(3,2,1))
        self.assertEqual((a['mejor_nacional'],a['mejor_internacional']),(3,5))
        self.assertEqual(a['ultima_regata'],date(2026,10,10))
        self.assertEqual(a['clases_activas'],'420')
        self.assertEqual(a['fecha_nacimiento'],date(2012,1,4))

    def test_historia_hasta_fecha_sin_regatas_ni_clases_futuras(self):
        filas=s.listar_regatistas(self.engine,fecha=date(2025,12,1))
        a=next(r for r in filas if r['dni']=='D1')
        b=next(r for r in filas if r['dni']=='D2')
        self.assertEqual(a['participaciones'],1)
        self.assertEqual(a['clases_activas'],'Optimist')
        self.assertIsNone(a['mejor_internacional'])
        self.assertEqual(b['participaciones'],0)

    def test_filtros_nacimiento_cohorte_clase_nivel_y_club(self):
        self.assertEqual([r['dni'] for r in self.leer(nacimiento='Pendiente')],['D2'])
        self.assertEqual([r['dni'] for r in self.leer(anio_min=2012,anio_max=2012)],['D1'])
        self.assertEqual(self.leer(anio_min=2013),[])
        self.assertEqual(len(self.leer(clase='420',nivel='Internacional')),2)
        self.assertEqual(self.leer(clase='Optimist'),[])
        self.assertEqual([r['dni'] for r in self.leer(id_club=2)],['D2'])
        self.assertEqual(len(self.leer(limite=1)),1)

    def test_busqueda_literal_e_invalidos(self):
        self.assertEqual(self.leer(busqueda="'; DROP TABLE deportista; --"),[])
        self.assertEqual(self.leer(busqueda='%'),[])
        self.assertEqual(len(self.leer(busqueda='ana')),1)
        for cambios in (dict(nacimiento='otro'),dict(nivel='x'),dict(anio_min=2020,anio_max=2010),dict(anio_min=True),dict(anio_max=2030)):
            with self.subTest(cambios=cambios),self.assertRaises(ValueError):self.leer(**cambios)

    def test_resumen_no_suma_puntos_ni_mezcla_clases_niveles_o_futuro(self):
        base=dict(id_competicion=1,competicion='Copa',fecha_inicio=date(2026,5,1),clase='420',nivel='Nacional',posicion_general=3,puntos=10)
        filas=s.resumen_deportivo([base,{**base,'id_unidad':99},
            {**base,'id_competicion':2,'nivel':'Internacional','posicion_general':20},
            {**base,'id_competicion':3,'clase':'470','posicion_general':None},
            {**base,'id_competicion':4,'fecha_inicio':date(2027,1,1)}],date(2026,12,31))
        self.assertEqual(len(filas),3)
        self.assertEqual(sum(r['regatas'] for r in filas),3)
        self.assertEqual(sum(r['podios'] for r in filas),1)
        self.assertNotIn('puntos',filas[0])
