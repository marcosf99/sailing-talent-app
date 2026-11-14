"""Comparación técnica real de la interfaz con lecturas simuladas."""
from datetime import date
import copy
import json
import unittest
import pyarrow as pa
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from app import datos
from services import informes as s
from test_consulta_informes_interfaz import HISTORIAL


PERSONAS=[dict(dni='D1',nombre='Ana',apellidos='Lago',club='Club A',edad=14,sexo='Femenino',participaciones=2),
          dict(dni='D2',nombre='Luis',apellidos='Rey',club='Club B',edad=15,sexo='Masculino',participaciones=3),
          dict(dni='D3',nombre='Eva',apellidos='Serra',club=None,edad=None,sexo=None,participaciones=0)]
SCRIPT='''
from datetime import date
from app import candidatos
def lectura(clave,funcion,*args):
    return funcion(*args)
candidatos.mostrar("supabase",date(2026,10,20),"motor",lectura)
'''


class ComparacionInformes(unittest.TestCase):
    def setUp(self):
        self.personas=copy.deepcopy(PERSONAS)
        self.informes={'D1':copy.deepcopy(HISTORIAL), 'D2':[{**HISTORIAL[0], 'id_informe':21,
            'fecha':date(2026,10,19), 'dni_deportista':'D2', 'nombre_tecnico':'Toni',
            'apellidos_tecnico':'Serra','estrategia':3,'tactica':5,'trimado':None,'tecnica':4}], 'D3':[]}
        self.mediciones={p['dni']:[] for p in self.personas}
        parches=[patch.object(datos,'cargar_clases',return_value=[dict(id_clase=1,nombre='Optimist')]),
                 patch.object(datos,'cargar_candidatos',side_effect=lambda *a:self.personas),
                 patch.object(datos,'comparar',side_effect=lambda motor,dnis,fecha:[p for d in dnis for p in self.personas if p['dni']==d]),
                 patch.object(s,'informes_para_comparar',side_effect=lambda motor,dnis,fecha:{d:self.informes[d] for d in dnis}),
                 patch.object(s,'guardar_en_proveedor'),
                 patch.object(datos,'cargar_historiales_comparacion',side_effect=lambda motor,dnis,fecha:{d:self.mediciones[d] for d in dnis})]
        self.m=[p.start() for p in parches]
        self.addCleanup(lambda:[p.stop() for p in reversed(parches)])
        self.at=AppTest.from_string(SCRIPT,default_timeout=15)
        p=patch.object(datos,'cargar_clases_comparacion',return_value={})
        p.start();self.addCleanup(p.stop)

    def seleccionar(self,dnis):
        self.at.run();self.at.multiselect(key='comparar_seleccion').set_value(dnis).run()
        self.assertEqual(len(self.at.exception),0)

    def especificacion(self,indice=0):
        return json.loads(self.at.get('arrow_vega_lite_chart')[indice].proto.spec)

    def barras(self):
        proto=self.at.get('arrow_vega_lite_chart')[0].proto
        return [fila for conjunto in proto.datasets
                for fila in pa.ipc.open_stream(conjunto.data.data).read_all().to_pylist()]

    def test_sin_seleccion_no_consulta_informes_ni_escribe(self):
        self.at.run();self.m[3].assert_not_called();self.m[4].assert_not_called()

    def test_grafico_tecnico_sin_mediciones_fisicas(self):
        self.seleccionar(['D1','D2'])
        self.assertEqual(len(self.at.get('arrow_vega_lite_chart')),1)
        spec=self.especificacion()
        self.assertEqual(spec['encoding']['y']['scale']['domain'],[0,5])
        self.assertIn('xOffset',spec['encoding'])
        valores=self.barras()
        self.assertEqual(len(valores),6)
        self.assertTrue(all(1<=v['Valoración']<=5 for v in valores))
        self.assertEqual({v['Técnico'] for v in valores},{'Eva Lago','Toni Serra'})
        self.m[3].assert_called_once_with('motor',('D1','D2'),date(2026,10,20))
        self.m[4].assert_not_called()

    def test_elige_informe_mas_antiguo_y_actualiza_grafico_y_tabla(self):
        self.seleccionar(['D1','D2'])
        self.at.selectbox(key='comparar_informe_supabase_D1_2026-10-20').set_value(10).run()
        valores=[v for v in self.barras() if v['Regatista']=='Ana Lago · D1']
        self.assertEqual({v['Fecha'] for v in valores},{'01/09/2026'})
        self.assertEqual(next(v['Valoración'] for v in valores if v['Dimensión']=='Estrategia'),2)
        self.assertTrue(any('2026-09-01' in str(m.value) for m in self.at.dataframe))

    def test_sin_informe_permanece_en_tabla_sin_ceros(self):
        self.seleccionar(['D1','D3'])
        tabla=self.at.dataframe[-1].value
        eva=tabla[tabla['Regatista']=='Eva Serra · D3'].iloc[0]
        self.assertEqual(eva['Técnico'],'Sin informe')
        self.assertTrue(tabla.loc[tabla['Regatista']=='Eva Serra · D3','Estrategia'].isna().all())
        self.assertEqual(len(self.at.get('arrow_vega_lite_chart')),0)

    def test_informe_todo_sin_valorar_no_se_convierte_en_cero(self):
        self.informes['D2']=[{**self.informes['D2'][0],**{campo:None for campo in s.VALORACIONES}}]
        self.seleccionar(['D1','D2'])
        self.assertEqual(len(self.at.get('arrow_vega_lite_chart')),0)
        self.assertTrue(any('al menos dos candidatos' in m.value for m in self.at.info))

    def test_grafico_fisico_y_tecnico_conviven(self):
        self.mediciones['D1']=[dict(id_registro=1,fecha=date(2026,10,1),altura=160)]
        self.mediciones['D2']=[dict(id_registro=2,fecha=date(2026,10,2),altura=170)]
        self.seleccionar(['D1','D2'])
        self.assertEqual(len(self.at.get('arrow_vega_lite_chart')),2)

    def test_error_tecnico_preserva_comparacion_de_perfiles_sin_secretos(self):
        self.m[3].side_effect=OSError('CONTRASEÑA_PRIVADA')
        self.seleccionar(['D1','D2'])
        self.assertTrue(any('No se pudieron consultar los informes' in m.value for m in self.at.warning))
        self.assertNotIn('CONTRASEÑA_PRIVADA',str(self.at.warning))
        self.assertEqual(len(self.at.dataframe),2)

    def test_un_solo_candidato_muestra_informe_sin_grafico(self):
        self.seleccionar(['D1'])
        self.assertEqual(self.at.selectbox(key='comparar_informe_supabase_D1_2026-10-20').value,11)
        self.assertEqual(len(self.at.get('arrow_vega_lite_chart')),0)

    def test_filtros_eliminan_selecciones_y_sus_informes(self):
        self.seleccionar(['D1','D2'])
        self.personas=self.personas[1:]
        self.at.run()
        self.assertEqual(self.at.multiselect(key='comparar_seleccion').value,['D2'])
        self.assertFalse(any('Ana Lago' in c.label for c in self.at.selectbox))

    def test_tres_candidatos_no_ocultan_ausencias(self):
        self.seleccionar(['D1','D2','D3'])
        self.assertEqual(len(self.at.dataframe[-1].value),3)
        self.assertEqual({v['Regatista'] for v in self.barras()},{'Ana Lago · D1','Luis Rey · D2'})
