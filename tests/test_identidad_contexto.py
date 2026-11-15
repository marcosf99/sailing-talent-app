"""Reglas de apellido omitido con nombres y clubes ficticios."""
import unittest
from decimal import Decimal
from services import revision_participantes as s, revision_lotes as lotes


class IdentidadContexto(unittest.TestCase):
    def candidato(self, **cambios):
        p = dict(nombre_original='Ana Pérez', nombre_propuesto=None,
                 apellidos_propuestos=None, id_club_identificado=1,
                 club_original='Club A', federacion_original='Federación A')
        p.update(cambios)
        ficha = dict(dni='D1', nombre='Ana', apellidos='Pérez García',
                     id_club=1, club='Club A', federacion='Federación A',
                     fecha_nacimiento=None, memoria_nombres=[])
        return s._candidatos(None, p, fichas=[ficha], aliases=[])[0]

    def test_mismo_club_nombre_y_primer_apellido_refuerzan(self):
        r = self.candidato()
        self.assertGreaterEqual(r['indice_similitud'], Decimal('.95'))
        self.assertIn('primer apellido y club', r['motivos'])

    def test_apellidos_coma_acentos_y_particulas(self):
        self.assertEqual(self.candidato(nombre_original='PEREZ, Ana')['indice_similitud'], Decimal('.95'))

    def test_sin_federacion_se_puede_usar_club_confirmado(self):
        self.assertEqual(self.candidato(federacion_original=None)['indice_similitud'], Decimal('.95'))

    def test_alias_confirmado_equivale_a_club_identificado(self):
        p = dict(nombre_original='Ana Pérez', id_club_identificado=None,
                 club_original='C.A.', federacion_original=None)
        f = dict(dni='D1',nombre='Ana',apellidos='Pérez García',id_club=1,
                 club='Club A',federacion='Federación A')
        r = s._candidatos(None,p,fichas=[f],aliases=[dict(id_club=1,texto_normalizado=s.normalizar('C.A.'))])[0]
        self.assertEqual(r['indice_similitud'],Decimal('.95'))

    def test_distinta_federacion_y_club_reducen_coincidencia(self):
        r = self.candidato(id_club_identificado=2, federacion_original='Federación B')
        self.assertLess(r['indice_similitud'],Decimal('.65'))
        self.assertFalse(r['nombre_abreviado'])
        self.assertIn('federación indicada es distinta',r['motivos'])

    def test_mismo_club_prevalece_sobre_federacion_erronea_del_pdf(self):
        r = self.candidato(federacion_original='Federación B')
        self.assertFalse(r['conflicto_contexto'])
        self.assertGreaterEqual(r['indice_similitud'],Decimal('.95'))
        p = dict(id_participante_importado=1,id_fila=1,nombre_original='Ana Pérez',
                 id_club_identificado=1,club_original='Club A',federacion_original='Federación B',
                 dni_deportista_confirmado=None)
        ficha = dict(dni='D1',nombre='Ana',apellidos='Pérez García',id_club=1,
                     club='Club A',federacion='Federación A',fecha_nacimiento=None)
        contenido = dict(importacion=dict(nivel='Autonomico'),
            filas=[dict(id_fila=1,cumple_criterio=True,estado='pendiente',posicion_general=1,numero_vela_original='ESP 1')],
            participantes=[p])
        self.assertEqual(lotes._propuestas(None,contenido,[ficha],[])[0]['propuesta']['dni'],'D1')

    def test_segundos_apellidos_distintos_no_reciben_refuerzo(self):
        r = self.candidato(nombre_original='Ana Pérez López')
        self.assertNotIn('primer apellido y club',r['motivos'])
        self.assertFalse(r['nombre_abreviado'])

    def test_otro_primer_nombre_no_recibe_refuerzo(self):
        r = self.candidato(nombre_original='Anna Pérez')
        self.assertNotIn('primer apellido y club',r['motivos'])

    def test_documento_confirmado_prevalece_sobre_contexto(self):
        r = self.candidato(documento_propuesto='D1',id_club_identificado=2,
                           federacion_original='Federación B')
        self.assertEqual(r['indice_similitud'],Decimal(1))

    def test_misma_federacion_sin_club_no_es_refuerzo_fuerte(self):
        r = self.candidato(id_club_identificado=2)
        self.assertLess(r['indice_similitud'],Decimal('.95'))
        self.assertTrue(r['nombre_abreviado'])

    def test_federacion_del_club_confirmado_cuando_falta_en_pdf(self):
        r = self.candidato(federacion_original=None,id_club_identificado=2,
                           federacion_club_identificado='Federación B')
        self.assertLess(r['indice_similitud'],Decimal('.65'))
        self.assertFalse(r['nombre_abreviado'])
