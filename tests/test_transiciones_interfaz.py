"""Interacción con la nueva pantalla y la ficha individual, sin bases reales."""
from datetime import date
import json
import unittest
from unittest.mock import patch

import pyarrow as pa
from streamlit.testing.v1 import AppTest

from app import transiciones as ui
from test_transiciones import persona, FECHA


SCRIPT = '''
from datetime import date
from app import transiciones
def lectura(clave, funcion, *args):
    return funcion(*args)
transiciones.mostrar("supabase", date(2026,11,9), "motor", lectura)
'''


class InterfazTransiciones(unittest.TestCase):
    def setUp(self):
        self.personas = [persona(), persona('D2', 1)]
        p = patch.object(ui, 'cargar', side_effect=lambda *a:self.personas)
        self.cargar = p.start()
        self.addCleanup(p.stop)
        self.at = AppTest.from_string(SCRIPT, default_timeout=20)

    def iniciar_comparacion(self):
        self.at.run()
        self.at.multiselect(key='trans_seleccion').set_value(['D1', 'D2']).run()
        self.assertEqual(len(self.at.exception), 0)

    def puntos(self):
        return [r for grafico in self.at.get('arrow_vega_lite_chart') for conjunto in grafico.proto.datasets
                for r in pa.ipc.open_stream(conjunto.data.data).read_all().to_pylist()]

    def test_pantalla_inicial_con_recorrido_y_muestra(self):
        self.at.run()
        self.assertEqual(len(self.at.exception), 0)
        self.assertEqual(self.at.metric[0].value, '2')
        self.assertEqual(self.at.selectbox(key='trans_origen').value, 'Optimist')
        self.assertEqual(self.at.selectbox(key='trans_destino').value, 'ILCA 4')
        self.assertTrue(any('primeros 40' in c.value for c in self.at.caption))

    def test_filtrar_sexo_y_selecciones_incompatibles(self):
        self.iniciar_comparacion()
        self.at.selectbox(key='trans_sexo').set_value('Femenino').run()
        self.assertEqual(len(self.at.exception), 0)
        self.assertEqual(self.at.metric[0].value, '1')
        self.assertEqual(self.at.multiselect(key='trans_seleccion').value, ['D1'])

    def test_filtrar_generacion_y_federacion_clubes(self):
        self.at.run()
        self.at.multiselect(key='trans_generaciones').set_value([2011]).run()
        self.assertEqual(self.at.metric[0].value, '1')
        self.at.selectbox(key='trans_federacion').set_value('Galicia').run()
        self.assertTrue(any('No hay regatistas' in i.value for i in self.at.info))
        self.assertEqual(len(self.at.exception), 0)

    def test_edad_desconocida_excluida_solo_al_filtrar(self):
        self.personas[1]['fecha_nacimiento'] = None
        self.at.run()
        self.assertEqual(self.at.metric[0].value, '2')
        self.assertEqual(self.at.metric[1].value, '1')
        self.at.checkbox(key='trans_usar_edad').check().run()
        self.assertEqual(self.at.metric[0].value, '1')
        self.assertEqual(len(self.at.exception), 0)

    def test_cambiar_referencia_cambia_fechas_no_cierra_unidades(self):
        self.at.run()
        inicial=self.at.dataframe[0].value['Referencia'].iloc[0]
        self.at.selectbox(key='trans_criterio').set_value('unidades').run()
        self.assertNotEqual(self.at.dataframe[0].value['Referencia'].iloc[0], inicial)
        self.assertTrue(all(u['fecha_fin'] is None for p in self.personas for u in p['unidades']))

    def test_comparacion_alineada_mediciones_edad_colores_y_resultados(self):
        self.iniciar_comparacion()
        self.assertGreaterEqual(len(self.at.get('arrow_vega_lite_chart')), 4)
        puntos=self.puntos()
        self.assertEqual(len([r for r in puntos if 'Valor' in r]), 4)
        origenes=[r for r in puntos if r.get('Días') == 0 and 'Regata' in r]
        self.assertEqual(len(origenes),2)
        self.assertEqual(len({r['Fecha'] for r in origenes}),2)
        self.assertTrue(all('Edad al medir' in r for r in puntos if 'Valor' in r))
        specs=[json.loads(g.proto.spec) for g in self.at.get('arrow_vega_lite_chart')]
        fisico=next(s['layer'][0] for s in specs if s.get('layer') and s['layer'][0]['mark']['type']=='line')
        self.assertEqual(fisico['mark']['type'],'line')
        self.assertTrue(fisico['mark']['point'])
        self.assertEqual(fisico['encoding']['color']['scale']['domain'],['Ana Lago · perfil 1','Luis Lago · perfil 2'])
        self.assertTrue(any('tamaño completo' in c.value for c in self.at.caption))

    def test_cambio_medida_no_mezcla_unidades_y_conserva_colores(self):
        self.iniciar_comparacion()
        self.at.selectbox(key='trans_comparar_medida').set_value('peso').run()
        self.assertEqual(len(self.at.exception),0)
        self.assertEqual({r['Valor'] for r in self.puntos() if 'Valor' in r},{45,47})

    def test_nivel_y_ventana_recortan_sin_desplazar_referencia(self):
        self.iniciar_comparacion()
        self.at.selectbox(key='trans_comparar_nivel').set_value('Nacional').run()
        puntos=[r for r in self.puntos() if 'Regata' in r]
        self.assertTrue(all(r['Nivel']=='Nacional' and r['Días']<0 for r in puntos))
        self.at.selectbox(key='trans_comparar_ventana').set_value(6).run()
        self.assertEqual(len(self.at.exception),0)

    def test_sin_medidas_ni_informes_mantiene_resultados(self):
        for p in self.personas:
            p['mediciones']=[];p['informes']=[]
        self.iniciar_comparacion()
        self.assertTrue(any('No hay mediciones' in i.value for i in self.at.info))
        self.assertTrue(any('No hay informes' in i.value for i in self.at.info))
        self.assertTrue(any('Regata' in r for r in self.puntos()))

    def test_sin_transiciones(self):
        for p in self.personas:p['resultados']=[]
        self.at.run()
        self.assertEqual(len(self.at.exception),0)
        self.assertTrue(any('No hay transiciones' in i.value for i in self.at.info))

    def test_empates_sin_direccion_explicados(self):
        for p in self.personas:
            p['resultados'][1]['fecha_inicio']=p['resultados'][0]['fecha_inicio']
        self.at.run()
        self.assertEqual(len(self.at.exception),0)
        self.assertTrue(any('sin dirección' in c.value for c in self.at.caption))


class FichaTransiciones(unittest.TestCase):
    def test_linea_temporal_contexto_y_regatas_individuales(self):
        p=persona()
        contenido={'ficha':p, 'mediciones':p['mediciones'], 'resultados':p['resultados'], 'informes':p['informes'],
                   'trayectoria':[{**u,'dni_miembro':p['dni'],'nombre_miembro':p['nombre'],
                                   'apellidos_miembro':p['apellidos']} for u in p['unidades']]}
        script='''
from datetime import date
from app import transiciones
contenido=transiciones.cargar("ficha",date(2026,11,9))
transiciones.mostrar_individual(contenido,date(2026,11,9),'ficha_prueba')
'''
        with patch.object(ui,'cargar',return_value=contenido):
            at=AppTest.from_string(script,default_timeout=20).run()
            self.assertEqual(len(at.exception),0)
            self.assertGreaterEqual(len(at.get('arrow_vega_lite_chart')),4)
            self.assertTrue(any('Edad en la referencia: 14 años y 11 meses' in x.value for x in at.markdown))
            self.assertTrue(any('seguía abierta' in c.value for c in at.caption))
            self.assertTrue(any('no los vincula a una clase' in c.value for c in at.caption))
            self.assertEqual(at.dataframe[0].value['Valor'].iloc[0],150)
