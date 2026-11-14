from pathlib import Path
from datetime import date
from decimal import Decimal
import os
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from app import datos
from services import edad_clases

CLUBES=[dict(id_club=1,nombre='Portosín',federacion='Galicia'),dict(id_club=2,nombre='Vigo',federacion='Galicia')]
PERSONAS=[dict(dni='STDEMO0001',nombre='Alba',apellidos='Lago Varela',club='Portosín'),dict(dni='STDEMO0004',nombre='Iago',apellidos='Rey Blanco',club='Vigo')]

def buscar(motor,texto,club):
    return [] if texto=='no existe' else PERSONAS

def ficha(motor,dni,fecha):
    sin=dni.endswith('4');p=PERSONAS[1 if sin else 0]
    return dict(
        ficha={**p,'federacion':'Galicia','fecha_nacimiento':None if sin else date(2012,1,4),'sexo':'Masculino' if sin else 'Femenino','edad':13 if sin else 14,'clases_activas':'Optimist','participaciones':0 if sin else 2,'mejor_puesto':None if sin else 1,'altura':None if sin else Decimal('148.00'),'fecha_medicion':None if sin else date(2026,10,15)},
        mediciones=[] if sin else [dict(fecha=date(2025,10,15),altura=Decimal('146'),peso=Decimal('38'),envergadura=Decimal('149'),porcentaje_graso=None),dict(fecha=date(2026,10,15),altura=Decimal('148'),peso=Decimal('39'),envergadura=Decimal('151'),porcentaje_graso=Decimal('18'))],
        resultados=[] if sin else [dict(competicion='Encuentro DEMO',fecha_inicio=date(2026,5,2),fecha_fin=date(2026,5,3),clase='Optimist',nivel='Nacional',localidad='Valencia',posicion_general=1,posicion_categoria=None,puntos=Decimal('10'))],
        trayectoria=[] if sin else [dict(id_unidad=1,clase='Optimist',fecha_inicio=date(2025,1,1),fecha_fin=None,activa=True,dni_miembro=dni,nombre_miembro='Alba',apellidos_miembro='Lago Varela',rol='Patron')],
    )

class TestInterfaz(unittest.TestCase):
    def setUp(self):
        self.patches=[patch.dict(os.environ,{'DB_PROVIDER':'supabase'}),patch.object(datos,'crear_motor_lectura',side_effect=lambda p:p),patch.object(datos,'cargar_clubes',return_value=CLUBES),patch.object(datos,'buscar',side_effect=buscar),patch.object(datos,'cargar_ficha',side_effect=ficha)]
        for p in self.patches:p.start()
        edad = patch.object(edad_clases, 'pendientes_por_edad', return_value=[])
        self.edad = edad.start()
        self.addCleanup(edad.stop)
        self.addCleanup(lambda:[p.stop() for p in reversed(self.patches)])
        self.app=AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app' / 'main.py'),default_timeout=15)

    def test_ficha_tablas_y_grafico(self):
        at=self.app.run()
        self.assertEqual(len(at.exception),0)
        self.assertEqual(at.title[0].value,'Sailing Talent')
        self.assertEqual([x.label for x in at.tabs],['Resultados deportivos','Evolución física','Trayectoria y equipos','Informes técnicos'])
        self.assertEqual(at.metric[0].value,'2')
        self.assertEqual(len(at.dataframe),3)
        self.assertEqual(len(at.get('arrow_vega_lite_chart')),2)

    def test_sin_mediciones_o_resultados(self):
        at=self.app.run()
        at.selectbox(key='regatista').set_value('STDEMO0004').run()
        self.assertEqual(len(at.exception),0)
        self.assertEqual(at.metric[1].value,'—')
        self.assertTrue(any('No hay mediciones' in i.value for i in at.info))
        self.assertTrue(any('No hay resultados' in i.value for i in at.info))

    def test_busqueda_sin_resultados(self):
        at=self.app.run()
        at.text_input[0].set_value('no existe')
        # El primer botón de main es submit; el de sidebar es Actualizar datos.
        next(b for b in at.button if b.label=='Buscar').click().run()
        self.assertEqual(len(at.exception),0)
        self.assertTrue(any('No se han encontrado' in i.value for i in at.info))
        self.assertEqual(len(at.metric),0)

    def test_cambio_proveedor_y_actualizacion(self):
        at=self.app.run()
        at.selectbox(key='regatista').set_value('STDEMO0004').run()
        at.selectbox(key='proveedor').set_value('cloudsql').run()
        self.assertEqual(len(at.exception),0)
        self.assertEqual(at.selectbox(key='regatista').value,'STDEMO0001')
        next(b for b in at.button if b.label=='Actualizar datos').click().run()
        self.assertEqual(len(at.exception),0)

    def test_error_conexion_sin_credenciales(self):
        with patch.object(datos,'cargar_clubes',side_effect=KeyError('CONTRASEÑA_PRIVADA')):
            at=self.app.run()
        self.assertEqual(len(at.exception),0)
        self.assertIn('No se pudo conectar',at.error[0].value)
        self.assertNotIn('CONTRASEÑA_PRIVADA',at.error[0].value)

    def test_cambio_indicador(self):
        at=self.app.run()
        at.selectbox(key='indicador').set_value('Peso (kg)').run()
        self.assertEqual(len(at.exception),0)
        self.assertEqual(len(at.get('arrow_vega_lite_chart')),2)

    def test_marcas_de_clase_sobre_mediciones_conservando_trayectoria(self):
        import json
        def con_cambio(motor,dni,fecha):
            c=ficha(motor,dni,fecha)
            c['trayectoria'].append({**c['trayectoria'][0], 'id_unidad':2,
                                     'clase':'ILCA 4', 'fecha_inicio':date(2026,1,4)})
            return c
        with patch.object(datos,'cargar_ficha',side_effect=con_cambio):
            at=self.app.run()
        self.assertEqual(len(at.exception),0)
        self.assertIn('Trayectoria y equipos',[t.label for t in at.tabs])
        spec=json.loads(at.get('arrow_vega_lite_chart')[0].proto.spec)
        self.assertEqual(spec['layer'][0]['mark']['type'],'line')
        self.assertEqual(spec['layer'][1]['mark']['type'],'rule')
        self.assertTrue(any('inicio registrado' in c.value for c in at.caption))
        self.assertFalse(any(s.label=='Referencia del cambio' for s in at.selectbox))


    def test_anio_nacimiento_visible(self):
        at=self.app.run()
        self.assertTrue(any('Año de nacimiento: 2012' in c.value for c in at.caption))
        self.assertEqual(len(at.exception),0)
    def test_nacimiento_desconocido(self):
        at=self.app.run();at.selectbox(key='regatista').set_value('STDEMO0004').run()
        self.assertTrue(any('Año de nacimiento: Sin registrar' in c.value for c in at.caption))
        self.assertEqual(len(at.exception),0)

    def test_cierres_edad_solo_si_vencidos_y_una_vez_por_dia(self):
        self.edad.return_value = [{'id_unidad': 7}]
        with patch.object(edad_clases, 'cerrar_en_proveedor', return_value={'cerradas': [7], 'incidencias': []}) as cerrar:
            self.app.run()
            self.app.run()
            cerrar.assert_called_once_with('supabase')
            self.edad.assert_called_once()

    def test_no_se_escribe_para_programar_cierres_futuros(self):
        with patch.object(edad_clases, 'cerrar_en_proveedor') as cerrar:
            self.app.run()
            cerrar.assert_not_called()

    def test_informes_en_ficha_y_cambio_de_regatista_sin_mezclar(self):
        from test_consulta_informes_interfaz import HISTORIAL
        def ficha_con_informes(motor,dni,fecha):
            return {**ficha(motor,dni,fecha),'informes':HISTORIAL if dni=='STDEMO0001' else []}
        with patch.object(datos,'cargar_ficha',side_effect=ficha_con_informes):
            self.app.run()
            self.assertTrue(any(t.value=='Practicar salidas.' for t in self.app.text))
            self.assertTrue(any(s.label=='Informe técnico para consultar' for s in self.app.selectbox))
            self.app.selectbox(key='regatista').set_value('STDEMO0004').run()
            self.assertTrue(any('No hay informes técnicos' in i.value for i in self.app.info))
            self.assertFalse(any(t.value=='Practicar salidas.' for t in self.app.text))

    def test_fecha_de_consulta_limita_informes_y_no_mantiene_detalle_futuro(self):
        from test_consulta_informes_interfaz import HISTORIAL
        def ficha_con_informes(motor,dni,fecha):
            return {**ficha(motor,dni,fecha),'informes':[r for r in HISTORIAL if r['fecha']<=fecha]}
        with patch.object(datos,'cargar_ficha',side_effect=ficha_con_informes):
            self.app.run()
            next(d for d in self.app.date_input if d.label=='Fecha de consulta').set_value(date(2026,9,1)).run()
            self.assertTrue(any(t.value=='Trabajo por parejas.' for t in self.app.text))
            self.assertFalse(any(t.value=='Practicar salidas.' for t in self.app.text))

if __name__=='__main__':unittest.main(verbosity=2)
