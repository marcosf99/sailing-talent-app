"""Altas masivas ficticias: presupuesto de consultas y coherencia final."""
import time,json,hashlib
import unittest
from datetime import date
from sqlalchemy import event,text
import test_importaciones as fixtures
from services import importaciones as base,resultados_importados as resultados,revision_participantes as revision,revision_lotes as lotes

def medir(equipos,tripulantes):
 db=fixtures.PersistenciaImportaciones();db.setUp();motor=db.engine
 event.listen(motor,'before_cursor_execute',lambda c,cu,q,p,ctx,m:(q.replace(' FOR UPDATE',''),p),retval=True)
 filas=[]
 for i in range(equipos):
  miembros=[]
  for j in range(tripulantes):
   h=hashlib.sha256(f'ficticio-{i}-{j}'.encode()).hexdigest()
   miembros.append({'nombre_original':h[:10]+' '+h[10:22],'nombre_propuesto':h[:10],'apellidos_propuestos':h[10:22],'club_original':'Club A','rol_propuesto':('Patron','Tripulante')[j]})
  filas.append(dict(numero_fila=i+1,datos_originales={},numero_vela_original='ESP '+str(i+1),posicion_general=i+1,puntos=str(i+1)+'.25',participantes=miembros))
 ident=db.crear(campos={**db.campos,'nivel':'Internacional','id_clase':tripulantes},filas=filas)
 b=base.obtener_borrador(motor,ident)
 decisiones=[dict(participante=p['id_participante_importado'],version=revision.version_participante(p),confirmar_distinto_lote=True,campos=dict(nombre=p['nombre_propuesto'],apellidos=p['apellidos_propuestos'],id_club=1,rol_propuesto=p['rol_propuesto'],fecha_nacimiento=None,sexo=None)) for p in b['participantes']]
 sql=[];event.listen(motor,'before_cursor_execute',lambda c,cu,q,p,ctx,m:sql.append(q))
 t=time.perf_counter();salida=lotes.crear_nuevos(motor,ident,decisiones,resultados.version_resultados(b),dict(nombre='Prueba altas',fecha_inicio=date(2026,10,3),fecha_fin=date(2026,10,4),localidad='Prueba',tipo_clasificacion='definitiva'),confirmar=True)
 segundos=time.perf_counter()-t;numero=len(sql)
 assert salida==dict(creados=equipos*tripulantes,resultados_incorporados=equipos)
 with motor.connect() as c:
  assert c.execute(text('SELECT count(*) FROM deportista')).scalar_one()==2+equipos*tripulantes
  assert c.execute(text('SELECT count(*) FROM participa_en')).scalar_one()==equipos
  dnis=list(c.execute(text("SELECT dni FROM deportista WHERE dni LIKE 'TEMP-%'")).scalars())
  assert len(set(dnis))==equipos*tripulantes
 db.doCleanups()
 return dict(equipos=equipos,deportistas=equipos*tripulantes,consultas=numero,segundos=round(segundos,3))


class RendimientoAltas(unittest.TestCase):
    def test_cuarenta_altas_y_sus_resultados(self):
        self.assertLessEqual(medir(40,1)['consultas'],115)

    def test_ciento_sesenta_altas_de_dobles_y_resultados(self):
        self.assertLessEqual(medir(80,2)['consultas'],200)

    def test_mas_de_doscientas_altas_se_dividen_en_bloques(self):
        self.assertLessEqual(medir(101,2)['consultas'],240)
