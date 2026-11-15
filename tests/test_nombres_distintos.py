"""Los apellidos compartidos no compensan nombres propios incompatibles."""
import unittest
from services import revision_participantes as s, revision_lotes as lotes


PARES = [
    ('Miguel','Campos Muñoz de Cuena','Jesús','Campos Muñoz de Cuena'),
    ('Yoel','Hernández Peña','Carla','Fernández Peña'),
    ('Joaquín','Valero Ruiz','Alejandro','Valero Ruiz'),
    ('Marina','Borrás Ugarriza','Mercedes','Borrás Ugarriza'),
    ('Martina','Rahola Codina','Jana','Rahola Codina'),
]


def persona(nombre, apellidos, ident=1):
    return dict(id_participante_importado=ident,id_fila=ident,
        nombre_original=f'{apellidos.upper()}, {nombre}',nombre_propuesto=nombre,
        apellidos_propuestos=apellidos,club_original='Club A',id_club_identificado=1,
        dni_deportista_confirmado=None,fecha_nacimiento_propuesta=None,
        sexo_propuesto=None,rol_propuesto='Patron')


def ficha(nombre, apellidos):
    return dict(dni='D1',nombre=nombre,apellidos=apellidos,id_club=1,
                club='Club A',federacion='Federación A',fecha_nacimiento=None)


class NombresDistintos(unittest.TestCase):
    def test_ejemplos_no_sugieren_ni_bloquean_una_ficha_distinta(self):
        for nombre,apellidos,otro,otros in PARES:
            for a,aa,b,bb in [(nombre,apellidos,otro,otros),(otro,otros,nombre,apellidos)]:
                with self.subTest(origen=a,ficha=b):
                    self.assertEqual(s._candidatos(None,persona(a,aa),fichas=[ficha(b,bb)],aliases=[]),[])

    def test_la_ficha_exacta_no_se_bloquea_por_el_familiar_en_otra_posicion(self):
        for nombre,apellidos,otro,otros in PARES:
            with self.subTest(nombre=nombre):
                participantes=[persona(otro,otros,1),persona(nombre,apellidos,2)]
                contenido=dict(importacion=dict(nivel='Autonomico'),participantes=participantes,
                    filas=[dict(id_fila=i,cumple_criterio=True,estado='pendiente',
                                posicion_general=i,numero_vela_original=f'ESP {i}') for i in (1,2)])
                propuestas=lotes._propuestas(None,contenido,[ficha(otro,otros)],[])
                self.assertEqual(propuestas[0]['propuesta']['dni'],'D1')
                self.assertIsNone(propuestas[1]['propuesta'])
                self.assertEqual(propuestas[1]['coincidencias'],0)

    def test_erratas_acentos_iniciales_y_nombres_compuestos_siguen_compatibles(self):
        for a,b in [('Anna','Ana'),('Joaquin','Joaquín'),('José Luis','Luis'),
                    ('María','María del Mar'),('J.','Jesús'),('Mateo','Matteo')]:
            with self.subTest(a=a,b=b):
                self.assertTrue(s.nombres_propios_compatibles(a,b))
                self.assertTrue(s.nombres_propios_compatibles(b,a))
        self.assertFalse(s.nombres_propios_compatibles('José Luis','José Manuel'))

    def test_busqueda_manual_permanece_disponible(self):
        self.assertEqual(s._candidatos(None,persona('Miguel','Campos Muñoz de Cuena'),
            consulta='Jesús',fichas=[ficha('Jesús','Campos Muñoz de Cuena')],aliases=[])[0]['dni'],'D1')

    def test_documento_y_variante_confirmada_prevalecen_sobre_diferencia(self):
        p=persona('Miguel','Campos Muñoz de Cuena')
        f=ficha('Jesús','Campos Muñoz de Cuena')
        self.assertEqual(s._candidatos(None,{**p,'documento_propuesto':'D1'},fichas=[f],aliases=[])[0]['indice_similitud'],1)
        f['memoria_nombres']=[dict(id_club=1,nombre_normalizado=s.memoria.clave(p['nombre_original']),tipo='variante')]
        self.assertEqual(s._candidatos(None,p,fichas=[f],aliases=[])[0]['indice_similitud'],1)
