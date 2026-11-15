"""Reutilización conservadora del catálogo en cargas nuevas."""
import unittest
from sqlalchemy import text
import test_importaciones as fixtures
from services import importaciones as s

class ClubesAutomaticos(unittest.TestCase):
    def setUp(self):
        self.db=fixtures.PersistenciaImportaciones();self.db.setUp();self.addCleanup(self.db.doCleanups)
    def cargar(self,texto):
        ident=self.db.crear(filas=[{**self.db.filas[0],'participantes':[{'nombre_original':'Ana Pérez','club_original':texto}]}])
        return s.obtener_borrador(self.db.engine,ident)['participantes'][0]
    def test_nombre_exacto_ignora_acentos_y_puntuacion(self):
        self.assertEqual(self.cargar('CLUB A')['id_club_identificado'],1)
    def test_alias_confirmado_se_aplica_sin_sustituir_texto_fuente(self):
        s.registrar_alias_club(self.db.engine,'Abreviatura de prueba',2)
        p=self.cargar('Abreviatura de prueba')
        self.assertEqual(p['id_club_identificado'],2)
        self.assertEqual(p['club_original'],'Abreviatura de prueba')
        self.assertIsNone(p['dni_deportista_confirmado'])
    def test_siglas_desconocidas_y_alias_contextuales_no_se_aplican(self):
        s.registrar_alias_club(self.db.engine,'CNA',1,'Otra fuente')
        self.assertIsNone(self.cargar('CNA')['id_club_identificado'])
    def test_nombre_duplicado_permanece_pendiente(self):
        with self.db.engine.begin() as c:c.exec_driver_sql("INSERT INTO club(nombre,id_federacion) VALUES ('Club A',1)")
        self.assertIsNone(self.cargar('Club A')['id_club_identificado'])
