"""Presupuesto de consultas con datos ficticios; no mide latencia de proveedores."""
import time
import unittest
from datetime import date
from decimal import Decimal
from sqlalchemy import Numeric
from sqlalchemy import event,text
import test_importaciones as fixtures
from services import importaciones as base,resultados_importados as r

def medir(n,existentes):
 db=fixtures.PersistenciaImportaciones();db.setUp();e=db.engine
 event.listen(e,'before_cursor_execute',lambda c,cu,q,p,ctx,m:(q.replace(' FOR UPDATE',''),p),retval=True)
 filas=[dict(numero_fila=i+1,datos_originales={},numero_vela_original='ESP '+str(i+1),posicion_general=i+1,puntos=str(i+1)+'.25',participantes=[{'nombre_original':'Persona '+str(i)}]) for i in range(n)]
 ident=db.crear(campos={**db.campos,'nivel':'Internacional'},filas=filas)
 with e.begin() as c:
  for i in range(n):
   dni='REND-'+str(i)
   c.execute(text('INSERT INTO deportista(dni,nombre,apellidos) VALUES (:dni,:nombre,:apellido)'),{'dni':dni,'nombre':'Persona','apellido':str(i)})
   c.execute(text("UPDATE participante_importado SET dni_deportista_confirmado=:dni,estado='vinculado',confirmado_en=CURRENT_TIMESTAMP,rol_propuesto='Patron' WHERE id_fila=(SELECT id_fila FROM fila_clasificacion_importada WHERE id_importacion=:imp AND numero_fila=:fila)"),{'dni':dni,'imp':ident,'fila':i+1})
   if existentes:
    unidad=c.execute(text("INSERT INTO unidad_competitiva(fecha_inicio,id_clase) VALUES ('2026-01-01',1) RETURNING id_unidad")).scalar_one()
    c.execute(text("INSERT INTO forma_parte(dni_deportista,id_unidad,rol) VALUES (:dni,:u,'Patron')"),{'dni':dni,'u':unidad})
 b=base.obtener_borrador(e,ident);sql=[]
 event.listen(e,'before_cursor_execute',lambda c,cu,q,p,ctx,m:sql.append(q))
 t=time.perf_counter();cantidad=r.incorporar(e,ident,[f['id_fila'] for f in b['filas']],{'nombre':'Prueba rendimiento','fecha_inicio':date(2026,10,3),'fecha_fin':date(2026,10,4),'localidad':'Prueba','tipo_clasificacion':'definitiva'},r.version_resultados(b))
 segundos=time.perf_counter()-t;total_sql=len(sql)
 with e.connect() as c:
  assert c.execute(text('SELECT count(*) FROM participa_en')).scalar_one()==n
  puntos=list(c.execute(text('SELECT puntos FROM participa_en ORDER BY posicion_general').columns(puntos=Numeric(10,2))).scalars())
  assert puntos==[Decimal(i+1)+Decimal('.25') for i in range(n)]
 db.doCleanups()
 return dict(equipos=n,unidades_existentes=existentes,resultados=cantidad,consultas=total_sql,segundos=round(segundos,4))


class RendimientoImportacion(unittest.TestCase):
    def test_resultados_de_unidades_existentes_no_hacen_consultas_por_equipo(self):
        for n in (1,80):
            with self.subTest(equipos=n):
                self.assertLessEqual(medir(n,True)['consultas'],20)

    def test_unidades_nuevas_reutilizan_lecturas_y_agrupan_resultados(self):
        self.assertLessEqual(medir(80,False)['consultas'],180)

    def test_bloques_de_mas_de_doscientos_resultados(self):
        self.assertLessEqual(medir(201,True)['consultas'],22)
