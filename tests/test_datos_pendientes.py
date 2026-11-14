"""Datos incompletos sin confundir documentos provisionales con DNIs conocidos."""
import unittest
from unittest.mock import patch
from sqlalchemy import text
from streamlit.testing.v1 import AppTest
from services import deportistas
from app import datos_pendientes as vista
import test_importaciones as fixtures


class DatosPendientes(unittest.TestCase):
    def setUp(self):
        self.db=fixtures.PersistenciaImportaciones();self.db.setUp();self.addCleanup(self.db.doCleanups)
        with self.db.engine.begin() as c:
            c.exec_driver_sql('DELETE FROM deportista')
            c.exec_driver_sql("INSERT INTO federacion_autonomica(nombre) VALUES ('Otra federación')")
            c.exec_driver_sql('UPDATE club SET id_federacion=2 WHERE id_club=2')
            c.exec_driver_sql("""INSERT INTO deportista(dni,nombre,apellidos,fecha_nacimiento,id_club) VALUES
                ('TEMP-ABC','Ana','Pérez',NULL,1),('12345678Z','Luis','Lago',NULL,1),
                ('TEST-ABC','Berta','Pita','2012-01-01',2),('87654321X','Mario','Ríos','2011-01-01',2),
                ('STDEMO1','Sin','Club',NULL,NULL)""")
        self.filas=deportistas.datos_pendientes(self.db.engine)

    def test_solo_fichas_incompletas_y_motivos_por_separado(self):
        self.assertEqual(len(self.filas),4)
        por_id={f['dni']:f for f in self.filas}
        self.assertEqual((por_id['12345678Z']['sin_dni'],por_id['12345678Z']['sin_nacimiento']),(False,True))
        self.assertEqual((por_id['TEST-ABC']['sin_dni'],por_id['TEST-ABC']['sin_nacimiento']),(True,False))
        self.assertEqual(por_id['TEMP-ABC']['nombre'],'Ana')

    def test_filtros_grupos_y_fichas_sin_club_sin_duplicados(self):
        self.assertEqual(len(vista.filtrar(self.filas,federacion=1,club=1)),2)
        self.assertEqual(len(vista.filtrar(self.filas,dato='Sin DNI')),3)
        self.assertEqual(len(vista.filtrar(self.filas,dato='Ambos datos')),2)
        self.assertEqual(len(vista.filtrar(self.filas,club=-1)),1)
        grupos=vista.agrupar(self.filas)
        self.assertEqual(sum(g['Deportistas'] for g in grupos),4)
        self.assertEqual(len(grupos),3)

    def test_interfaz_filtra_y_no_escribe(self):
        script='''from app import datos_pendientes
def lectura(clave,funcion,*args):return funcion(*args)
datos_pendientes.mostrar('supabase','motor',lectura)
'''
        with patch.object(deportistas,'datos_pendientes',return_value=self.filas),patch.object(deportistas,'guardar_en_proveedor') as guardar:
            app=AppTest.from_string(script).run()
            self.assertEqual(len(app.exception),0)
            self.assertEqual(len(app.dataframe[1].value),4)
            app.selectbox(key='pendientes_fed_supabase').set_value(2).run()
            self.assertEqual(len(app.dataframe[1].value),1)
            self.assertIn('Berta',app.dataframe[1].value.iloc[0]['Regatista'])
            guardar.assert_not_called()
