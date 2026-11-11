"""Líneas temporales comparadas, con datos ficticios y sin conexiones reales."""
from datetime import date
import copy
import json
import unittest
from unittest.mock import patch
import pyarrow as pa
from streamlit.testing.v1 import AppTest
from app import datos


PERSONAS=[dict(dni='D1',nombre='Ana',apellidos='Lago'),dict(dni='D2',nombre='Luis',apellidos='Rey'),
          dict(dni='D3',nombre='Eva',apellidos='Serra')]
SCRIPT='''
from datetime import date
from app import candidatos,datos
def lectura(clave,funcion,*args):
    return funcion(*args)
personas=datos.comparar("motor",["D1","D2","D3"],date(2026,10,20))
candidatos.mostrar_comparacion_fisica("supabase",date(2026,10,20),"motor",lectura,personas)
'''


class EvolucionComparada(unittest.TestCase):
    def setUp(self):
        self.personas=copy.deepcopy(PERSONAS)
        self.historiales={'D1':[dict(id_registro=1,fecha=date(2025,10,1),altura=150,peso=40,envergadura=154,porcentaje_graso=0),
                                dict(id_registro=2,fecha=date(2026,10,1),altura=155,peso=43,envergadura=158,porcentaje_graso=None)],
                         'D2':[dict(id_registro=3,fecha=date(2025,11,1),altura=148,peso=39,envergadura=150,porcentaje_graso=17),
                                dict(id_registro=4,fecha=date(2026,10,2),altura=160,peso=48,envergadura=164,porcentaje_graso=18)], 'D3':[]}
        p1=patch.object(datos,'comparar',side_effect=lambda *a:self.personas)
        p2=patch.object(datos,'cargar_historiales_comparacion',side_effect=lambda *a:self.historiales)
        self.m=[p1.start(),p2.start()]
        self.addCleanup(p1.stop);self.addCleanup(p2.stop)
        p3=patch.object(datos,'cargar_clases_comparacion',return_value={})
        p3.start();self.addCleanup(p3.stop)
        self.at=AppTest.from_string(SCRIPT,default_timeout=15)

    def spec(self):return json.loads(self.at.get('arrow_vega_lite_chart')[0].proto.spec)

    def puntos(self):
        proto=self.at.get('arrow_vega_lite_chart')[0].proto
        return [r for conjunto in proto.datasets for r in pa.ipc.open_stream(conjunto.data.data).read_all().to_pylist()]

    def test_lineas_con_puntos_fechas_colores_y_unidades(self):
        self.at.run();self.assertEqual(len(self.at.exception),0)
        spec=self.spec()
        self.assertEqual(spec['mark']['type'],'line')
        self.assertTrue(spec['mark']['point'])
        self.assertEqual(spec['encoding']['x']['type'],'temporal')
        self.assertEqual(spec['encoding']['y']['title'],'Altura (cm)')
        self.assertEqual(spec['encoding']['color']['scale']['domain'],['Ana Lago · D1','Luis Rey · D2','Eva Serra · D3'])
        self.assertEqual(len(self.puntos()),4)
        self.m[1].assert_called_once_with('motor',('D1','D2','D3'),date(2026,10,20))

    def test_cambio_indicador_conserva_colores_y_no_mezcla_unidades(self):
        self.at.run();colores=self.spec()['encoding']['color']
        self.at.selectbox(key='comparar_indicador').set_value('peso').run()
        self.assertEqual(self.spec()['encoding']['color'],colores)
        self.assertEqual(self.spec()['encoding']['y']['title'],'Peso (kg)')
        self.assertEqual({p['Valor'] for p in self.puntos()},{39,40,43,48})
        self.at.selectbox(key='comparar_indicador').set_value('envergadura').run()
        self.assertEqual(self.spec()['encoding']['y']['title'],'Envergadura (cm)')
        self.assertEqual(self.spec()['encoding']['color'],colores)

    def test_historial_completo_aunque_perfil_no_tenga_ultima_medida(self):
        self.at.run()
        self.assertEqual(len([p for p in self.puntos() if p['Regatista']=='Ana Lago · D1']),2)

    def test_una_medicion_muestra_punto_sin_inventar_evolucion(self):
        self.historiales['D1']=self.historiales['D1'][:1];self.historiales['D2']=[]
        self.at.run()
        self.assertEqual(len(self.puntos()),1)
        self.assertTrue(any('una sola fecha' in c.value for c in self.at.caption))
        self.assertTrue(any('Sin registros' in c.value and 'Luis Rey' in c.value for c in self.at.caption))

    def test_no_muestra_mediciones_posteriores_a_fecha_de_consulta(self):
        self.historiales['D1'].append(dict(id_registro=9,fecha=date(2026,10,21),altura=300))
        self.at.run()
        self.assertNotIn(300,[p['Valor'] for p in self.puntos()])

    def test_mismo_dia_ultima_medida_conocida_sin_promedio_ni_arrastre(self):
        self.historiales['D1'].extend([
            dict(id_registro=6,fecha=date(2026,10,1),altura=156),
            dict(id_registro=7,fecha=date(2026,10,1),altura=None,peso=45),
            dict(id_registro=8,fecha=date(2026,10,2),altura=None,peso=46)])
        self.at.run()
        puntos=[p for p in self.puntos() if p['Regatista']=='Ana Lago · D1']
        self.assertEqual([p['Valor'] for p in puntos],[150,156])

    def test_valores_ausentes_no_son_ceros_y_cero_graso_es_valido(self):
        self.at.run();self.at.selectbox(key='comparar_indicador').set_value('porcentaje_graso').run()
        ana=[p for p in self.puntos() if p['Regatista']=='Ana Lago · D1']
        self.assertEqual(len(ana),1)
        self.assertEqual(ana[0]['Valor'],0)

    def test_historial_vacio_no_muestra_grafico(self):
        self.historiales={d:[] for d in self.historiales}
        self.at.run()
        self.assertEqual(len(self.at.exception),0)
        self.assertEqual(len(self.at.get('arrow_vega_lite_chart')),0)
        self.assertTrue(any('No hay mediciones' in i.value for i in self.at.info))

    def test_indicador_obsoleto_se_reemplaza_por_disponible(self):
        self.at.run();self.at.selectbox(key='comparar_indicador').set_value('peso').run()
        self.historiales={'D1':[dict(id_registro=1,fecha=date(2026,10,1),altura=150)],'D2':[],'D3':[]}
        self.at.run()
        self.assertEqual(len(self.at.exception),0)
        self.assertEqual(self.at.selectbox(key='comparar_indicador').value,'altura')

    def test_error_lectura_mensaje_sin_secretos(self):
        self.m[1].side_effect=OSError('CONTRASEÑA_PRIVADA')
        self.at.run()
        self.assertEqual(len(self.at.exception),0)
        self.assertTrue(any('No se pudo consultar' in w.value for w in self.at.warning))
        self.assertNotIn('CONTRASEÑA_PRIVADA',str(self.at.warning))

    def test_tooltip_edad_en_cada_medicion_no_edad_actual(self):
        self.personas[0]['fecha_nacimiento']=date(2012,10,15)
        self.at.run()
        edades=[p['Edad al medir'] for p in self.puntos() if p['Regatista']=='Ana Lago · D1']
        self.assertEqual(edades,['12 años y 11 meses','13 años y 11 meses'])
        self.assertTrue(any(t['field']=='Edad al medir' for t in self.spec()['encoding']['tooltip']))
        self.at.selectbox(key='comparar_indicador').set_value('peso').run()
        self.assertEqual([p['Edad al medir'] for p in self.puntos() if p['Regatista']=='Ana Lago · D1'],edades)

    def test_sin_nacimiento_no_infiere_edad_ni_elimina_medicion(self):
        self.at.run()
        self.assertEqual(len(self.puntos()),4)
        self.assertEqual({p['Edad al medir'] for p in self.puntos()},{'Edad no disponible'})

    def test_edad_cumpleanos_meses_y_fechas_invalidas(self):
        from app.candidatos import edad_en_medicion
        nacimiento=date(2012,10,15)
        self.assertEqual(edad_en_medicion(nacimiento,date(2026,10,15)),'14 años')
        self.assertEqual(edad_en_medicion(nacimiento,date(2026,11,15)),'14 años y 1 mes')
        self.assertEqual(edad_en_medicion(nacimiento,date(2026,11,14)),'14 años')
        self.assertEqual(edad_en_medicion(nacimiento,date(2013,10,15)),'1 año')
        self.assertEqual(edad_en_medicion(nacimiento,date(2011,10,15)),'Edad no disponible')
        self.assertEqual(edad_en_medicion(date(2012,2,29),date(2026,3,1)),'14 años')
