"""Cambios de clase sobre curvas y comparación por edad; datos ficticios."""
from datetime import date
import json
import unittest
from unittest.mock import patch

import pyarrow as pa
from sqlalchemy import create_engine, event
from streamlit.testing.v1 import AppTest

from app import datos
from services import antropometria
from services.transiciones import incorporaciones


FECHA = date(2026, 10, 20)


class Marcas(unittest.TestCase):
    def test_misma_clase_repetida_no_genera_cambio_ni_futuro(self):
        unidades = [dict(clase='Optimist', fecha_inicio=date(2020, 1, 1)),
                    dict(clase='Optimist', fecha_inicio=date(2021, 1, 1)),
                    dict(clase='ILCA 4', fecha_inicio=date(2025, 1, 1)),
                    dict(clase='ILCA 4', fecha_inicio=date(2026, 1, 1)),
                    dict(clase='ILCA 6', fecha_inicio=date(2027, 1, 1))]
        self.assertEqual(incorporaciones(unidades, FECHA), [{'fecha': date(2025, 1, 1), 'clase': 'ILCA 4'}])

    def test_inicios_simultaneos_no_imponen_orden(self):
        unidades = [dict(clase=c, fecha_inicio=d) for c,d in (
            ('Optimist',date(2020,1,1)), ('420',date(2020,1,1)),
            ('ILCA 4',date(2025,1,1)), ('29er',date(2025,1,1)))]
        marcas=incorporaciones(unidades,FECHA)
        self.assertEqual({m['clase'] for m in marcas},{'ILCA 4','29er'})
        self.assertEqual({m['fecha'] for m in marcas},{date(2025,1,1)})

    def test_inicios_anteriores_al_nacimiento_y_corte_historico(self):
        unidades=[dict(clase='Optimist',fecha_inicio=date(2000,1,1)),
                  dict(clase='ILCA 4',fecha_inicio=date(2024,1,1)),
                  dict(clase='ILCA 6',fecha_inicio=date(2026,1,1))]
        self.assertEqual(incorporaciones(unidades,date(2025,1,1),date(2010,1,1)),[])


SCRIPT = '''
from datetime import date
from app import candidatos,datos
def lectura(clave,funcion,*args):return funcion(*args)
candidatos.mostrar_comparacion_fisica('supabase',date(2026,10,20),'motor',lectura,
    datos.comparar('motor',['D1','D2'],date(2026,10,20)))
'''


class CurvasConClases(unittest.TestCase):
    def setUp(self):
        self.personas=[dict(dni='D1',nombre='Ana',apellidos='Lago',fecha_nacimiento=date(2010,10,1)),
                       dict(dni='D2',nombre='Luis',apellidos='Rey',fecha_nacimiento=date(2012,11,1))]
        self.historiales={d:[dict(id_registro=i+1,fecha=f,altura=150+i*3,peso=40+i,envergadura=None,porcentaje_graso=None)
                             for i,f in enumerate((date(2025,11,1),date(2026,10,1)))] for d in ('D1','D2')}
        self.clases={d:[dict(clase='Optimist',fecha_inicio=date(2020,1,1)),
                        dict(clase='ILCA 4',fecha_inicio=date(2026,1,1))] for d in ('D1','D2')}
        parches=[patch.object(datos,'comparar',side_effect=lambda *a:self.personas),
                 patch.object(datos,'cargar_historiales_comparacion',side_effect=lambda *a:self.historiales),
                 patch.object(datos,'cargar_clases_comparacion',side_effect=lambda *a:self.clases)]
        self.m=[p.start() for p in parches]
        self.addCleanup(lambda:[p.stop() for p in reversed(parches)])
        self.at=AppTest.from_string(SCRIPT,default_timeout=15)

    def spec(self):return json.loads(self.at.get('arrow_vega_lite_chart')[0].proto.spec)
    def filas(self):
        return [r for conjunto in self.at.get('arrow_vega_lite_chart')[0].proto.datasets
                for r in pa.ipc.open_stream(conjunto.data.data).read_all().to_pylist()]

    def test_edad_inicial_y_marcas_en_edad_correcta_por_persona(self):
        self.at.run();self.assertEqual(len(self.at.exception),0)
        self.assertEqual(self.at.selectbox(key='comparar_eje').value,'edad')
        spec=self.spec();self.assertEqual(spec['layer'][0]['encoding']['x']['field'],'Edad (meses)')
        self.assertIn('12',spec['layer'][0]['encoding']['x']['axis']['labelExpr'])
        puntos=[r for r in self.filas() if 'Valor' in r]
        self.assertEqual(len(puntos),4)
        marcas=[r for r in self.filas() if 'Clase' in r]
        self.assertEqual({r['Clase'] for r in marcas},{'ILCA 4'})
        ana=next(r for r in marcas if r['Regatista']=='Ana Lago · D1')
        luis=next(r for r in marcas if r['Regatista']=='Luis Rey · D2')
        self.assertEqual(ana['Edad (meses)'],183)
        self.assertEqual(luis['Edad (meses)'],158)
        self.assertEqual(ana['Fecha'],luis['Fecha'])
        for capa in spec['layer']:
            self.assertEqual(capa['encoding']['color']['scale']['domain'],['Ana Lago · D1','Luis Rey · D2'])
        self.assertTrue(any('mism' in c.value and 'edad' in c.value for c in self.at.caption))

    def test_calendario_preserva_fechas_y_edad_en_tooltip(self):
        self.at.run();self.at.selectbox(key='comparar_eje').set_value('fecha').run()
        spec=self.spec();self.assertEqual(spec['layer'][0]['encoding']['x']['type'],'temporal')
        self.assertEqual(spec['layer'][1]['mark']['type'],'rule')
        self.assertEqual(spec['layer'][1]['encoding']['x']['field'],'Fecha')
        self.assertTrue(any(t['field']=='Edad al inicio' for t in spec['layer'][1]['encoding']['tooltip']))
        self.assertEqual({r['Valor'] for r in self.filas() if 'Valor' in r},{150,153})

    def test_medida_y_fecha_historica_no_crean_puntos_en_el_cambio(self):
        self.at.run();self.at.selectbox(key='comparar_indicador').set_value('peso').run()
        puntos=[r for r in self.filas() if 'Valor' in r]
        self.assertEqual(len(puntos),4)
        self.assertEqual({r['Valor'] for r in puntos},{40,41})
        self.assertFalse(any('2026-01-01' in str(r['Fecha']) for r in puntos))

    def test_sin_nacimiento_usa_calendario_y_no_inventa_edad(self):
        self.personas[1]['fecha_nacimiento']=None
        self.at.run();self.assertEqual(self.at.selectbox(key='comparar_eje').value,'fecha')
        self.at.selectbox(key='comparar_eje').set_value('edad').run()
        self.assertEqual(len(self.at.exception),0)
        self.assertEqual({r['Regatista'] for r in self.filas() if 'Valor' in r},{'Ana Lago · D1'})
        self.assertTrue(any('Luis Rey' in i.value and 'nacimiento' in i.value for i in self.at.info))

    def test_fallo_de_clases_conserva_mediciones_y_no_filtra_secretos(self):
        self.m[2].side_effect=OSError('SECRETO_PRIVADO')
        self.at.run();self.assertEqual(len(self.at.exception),0)
        self.assertEqual(len([r for r in self.filas() if 'Valor' in r]),4)
        self.assertTrue(any('incorporación' in w.value for w in self.at.warning))
        self.assertNotIn('SECRETO_PRIVADO',str(self.at.warning))


class ConsultaClases(unittest.TestCase):
    def test_una_consulta_parametrizada_agrupa_y_filtra(self):
        motor=create_engine('sqlite://');self.addCleanup(motor.dispose)
        with motor.begin() as c:
            for sql in ["ATTACH DATABASE ':memory:' AS public",
                'CREATE TABLE public.deportista(dni TEXT,fecha_nacimiento DATE)',
                'CREATE TABLE public.clase(id_clase INT,nombre TEXT)',
                'CREATE TABLE public.unidad_competitiva(id_unidad INT,id_clase INT,fecha_inicio DATE)',
                'CREATE TABLE public.forma_parte(dni_deportista TEXT,id_unidad INT)',
                "INSERT INTO public.deportista VALUES ('D1','2010-01-01'),('D2',NULL)",
                "INSERT INTO public.clase VALUES (1,'Optimist'),(2,'ILCA 4')",
                "INSERT INTO public.unidad_competitiva VALUES (1,1,'2020-01-01'),(2,2,'2024-01-01'),(3,2,'2025-01-01'),(4,1,'2000-01-01'),(5,2,'2027-01-01')",
                "INSERT INTO public.forma_parte VALUES ('D1',1),('D1',2),('D1',3),('D1',4),('D1',5),('D2',1)"]:
                c.exec_driver_sql(sql)
        ejecutadas=[]
        event.listen(motor,'before_cursor_execute',lambda c,cu,s,p,ctx,m:ejecutadas.append(s))
        salida=antropometria.clases_para_comparar(motor,['D1','D2','D1'],FECHA)
        self.assertEqual(len(ejecutadas),1)
        self.assertEqual(len(salida['D1']),2)
        self.assertEqual(salida['D1'][0]['fecha_inicio'],date(2020,1,1))
        self.assertEqual(salida['D1'][1]['fecha_inicio'],date(2024,1,1))
        self.assertEqual(len(salida['D2']),1)
        with self.assertRaises(antropometria.ValidacionError):
            antropometria.clases_para_comparar(motor,[],FECHA)
