"""Casos históricos y consultas reales sobre una base local, sin credenciales."""
import copy
from datetime import date
import unittest

from sqlalchemy import create_engine, event

from database import transiciones as db
from services import transiciones as s


FECHA = date(2026, 11, 9)


def persona(dni='D1', desfase=0):
    p = dict(dni=dni, nombre='Ana' if dni == 'D1' else 'Luis', apellidos='Lago',
             fecha_nacimiento=date(2010+desfase, 6, 1), sexo='Femenino' if dni == 'D1' else 'Masculino',
             id_club=1 if dni == 'D1' else 2, club='Club A' if dni == 'D1' else 'Club B',
             id_federacion=1 if dni == 'D1' else 2, federacion='Galicia' if dni == 'D1' else 'Cataluña')
    p['unidades'] = [dict(id_unidad=1, id_clase=1, clase='Optimist', fecha_inicio=date(2023+desfase, 1, 1), fecha_fin=None),
                     dict(id_unidad=2, id_clase=2, clase='ILCA 4', fecha_inicio=date(2024+desfase, 12, 1), fecha_fin=None)]
    p['resultados'] = [dict(id_unidad=1, id_clase=1, clase='Optimist', id_competicion=1, competicion='Regata origen',
                           fecha_inicio=date(2024+desfase, 11, 1), fecha_fin=date(2024+desfase, 11, 2),
                           nivel='Nacional', posicion_general=2, puntos=10),
                      dict(id_unidad=2, id_clase=2, clase='ILCA 4', id_competicion=2, competicion='Regata destino',
                           fecha_inicio=date(2025+desfase, 5, 1), fecha_fin=date(2025+desfase, 5, 2),
                           nivel='Autonómico', posicion_general=5, puntos=21)]
    p['mediciones'] = [dict(id_registro=i+1, fecha=date(2024+desfase+i, 11, 1), altura=150+i*5,
                           peso=45+i*2, envergadura=155+i*5, porcentaje_graso=None) for i in range(2)]
    p['informes'] = [dict(id_informe=1, fecha=date(2025+desfase, 6, 1), nombre_tecnico='Técnica',
                         apellidos_tecnico='Prueba', estrategia=3, tactica=4, trimado=None, tecnica=5,
                         fortalezas='Salida', debilidades=None, recomendaciones='Entrenar')]
    return p


class Transiciones(unittest.TestCase):
    def setUp(self):
        self.p = persona()

    def evento(self, criterio='regatas'):
        return s.detectar(self.p, FECHA, criterio)[0][0]

    def test_referencias_separadas(self):
        self.assertEqual(self.evento()['fecha'], date(2025, 5, 1))
        self.assertEqual(self.evento('unidades')['fecha'], date(2024, 12, 1))
        self.assertEqual(self.evento()['edad_meses'], 179)

    def test_unidades_abiertas_no_se_cierran_y_no_prueban_regatas(self):
        antes = copy.deepcopy(self.p)
        e = self.evento()
        self.assertTrue(e['origen_abierto'])
        self.assertEqual(e['regatas_origen_posteriores'], 0)
        self.assertEqual(self.p, antes)

    def test_regatas_en_origen_despues_del_cambio(self):
        self.p['resultados'].append({**self.p['resultados'][0], 'id_competicion': 3,
                                    'fecha_inicio': date(2026, 1, 1), 'fecha_fin': date(2026, 1, 2)})
        self.assertEqual(self.evento()['regatas_origen_posteriores'], 1)

    def test_otro_equipo_misma_clase_no_es_transicion(self):
        self.p['unidades'].append({**self.p['unidades'][0], 'id_unidad': 3, 'fecha_inicio': date(2026, 1, 1)})
        self.assertEqual(len(s.detectar(self.p, FECHA, 'unidades')[0]), 1)

    def test_returnos_no_se_inventan_como_nuevas_entradas(self):
        self.p['resultados'].append({**self.p['resultados'][0], 'id_competicion': 3,
                                    'fecha_inicio': date(2026, 1, 1), 'fecha_fin': date(2026, 1, 2)})
        self.assertEqual(len(s.detectar(self.p, FECHA)[0]), 1)

    def test_empate_de_fechas_sin_direccion_ni_salto(self):
        self.p['unidades'].append(dict(id_unidad=3, id_clase=3, clase='420', fecha_inicio=date(2024, 12, 1), fecha_fin=None))
        self.p['unidades'].append(dict(id_unidad=4, id_clase=4, clase='470', fecha_inicio=date(2026, 1, 1), fecha_fin=None))
        eventos, ambiguas = s.detectar(self.p, FECHA, 'unidades')
        self.assertEqual(eventos, [])
        self.assertEqual(ambiguas, 1)

    def test_tres_clases_producen_solo_pares_consecutivos(self):
        self.p['unidades'].append(dict(id_unidad=3, id_clase=3, clase='ILCA 6', fecha_inicio=date(2026, 1, 1), fecha_fin=None))
        eventos, _ = s.detectar(self.p, FECHA, 'unidades')
        self.assertEqual([(e['origen'], e['destino']) for e in eventos], [('Optimist', 'ILCA 4'), ('ILCA 4', 'ILCA 6')])

    def test_regata_no_finalizada_no_define_referencia(self):
        self.p['resultados'][1]['fecha_fin'] = date(2027, 1, 1)
        self.assertEqual(s.detectar(self.p, FECHA)[0], [])

    def test_clase_sin_regatas_no_se_mezcla_con_unidades(self):
        self.p['resultados'] = self.p['resultados'][:1]
        self.assertEqual(s.detectar(self.p, FECHA)[0], [])
        self.assertEqual(len(s.detectar(self.p, FECHA, 'unidades')[0]), 1)

    def test_fecha_historica_excluye_nuevas_clases(self):
        self.assertEqual(s.detectar(self.p, date(2025, 1, 1))[0], [])

    def test_edad_desconocida_o_antes_de_nacer(self):
        self.p['fecha_nacimiento'] = None
        self.assertIsNone(self.evento()['edad'])
        self.assertIsNone(s.edad_meses(date(2030, 1, 1), FECHA))
        self.assertEqual(s.edad_texto(None, FECHA), 'Sin nacimiento válido')
        self.assertEqual(s.edad_texto(date(2025, 10, 9), FECHA), '1 año y 1 mes')

    def test_contexto_sin_futuro_por_indicador_y_desempate(self):
        self.p['mediciones'].extend([
            dict(id_registro=3, fecha=date(2025, 5, 1), altura=154, peso=None),
            dict(id_registro=4, fecha=date(2025, 5, 1), altura=156, peso=None)])
        c = {r['Indicador']: r for r in s.contexto(self.p, self.evento())}
        self.assertEqual(c['Altura (cm)']['Valor'], 156)
        self.assertEqual(c['Altura (cm)']['Antigüedad (días)'], 0)
        self.assertEqual(c['Peso (kg)']['Valor'], 45)
        self.assertEqual(c['Peso (kg)']['Fecha de medición'], date(2024, 11, 1))
        self.assertIsNone(c['Grasa corporal (%)']['Valor'])

    def test_sin_mediciones_no_se_inventan_valores(self):
        self.p['mediciones'] = []
        self.assertTrue(all(r['Valor'] is None for r in s.contexto(self.p, self.evento())))

    def test_ventanas_de_meses_respetan_fin_de_mes_y_bisiesto(self):
        self.assertEqual(s.desplazar_meses(date(2024, 3, 31), -1), date(2024, 2, 29))
        self.assertEqual(s.desplazar_meses(date(2024, 2, 29), 12), date(2025, 2, 28))

    def test_alineacion_y_limite_historico(self):
        h = s.entorno(self.p, self.evento(), date(2025, 7, 1), 12)
        self.assertTrue(all(r['fecha'] <= date(2025, 7, 1) for r in h['mediciones']))
        self.assertEqual(h['resultados'][1]['dias'], 0)
        self.assertEqual(h['resultados'][1]['meses'], 0)
        self.assertEqual(len(h['informes']), 1)

    def test_nivel_no_cambia_ancla(self):
        e = self.evento()
        h = s.entorno(self.p, e, FECHA, 12, 'Nacional')
        self.assertEqual(len(h['resultados']), 1)
        self.assertEqual(e['fecha'], date(2025, 5, 1))

    def test_resumen_separa_clase_nivel_y_no_suma_puntos(self):
        e = self.evento()
        h = s.entorno(self.p, e, FECHA)
        filas = h['resultados'] + [h['resultados'][1]]
        resumen = s.resumen_resultados(self.p, e, filas)
        self.assertEqual(len(resumen), 2)
        self.assertEqual(sum(r['Participaciones'] for r in resumen), 2)
        self.assertFalse(any('Puntos' in r for r in resumen))

    def test_validacion(self):
        with self.assertRaises(ValueError): s.detectar(self.p, FECHA, 'inventado')
        with self.assertRaises(ValueError): s.entorno(self.p, self.evento(), FECHA, 0)

    def test_preparar_no_multiplica_por_miembros_ni_resultados(self):
        datos = {'unidades': [{**self.p, **u} for u in self.p['unidades'] for _ in range(2)]}
        datos.update({k: [{**r, 'dni': 'D1'} for r in self.p[k]] for k in ('resultados', 'mediciones', 'informes')})
        datos['resultados'] += [datos['resultados'][0]]
        datos['mediciones'].append(dict(dni='D1', id_registro=99, fecha=date(2027, 1, 1), altura=999))
        salida = s.preparar(datos, FECHA)
        self.assertEqual(len(salida), 1)
        self.assertEqual(len(salida[0]['unidades']), 2)
        self.assertEqual(len(salida[0]['resultados']), 2)
        self.assertEqual(len(salida[0]['mediciones']), 2)


class ConsultasTransiciones(unittest.TestCase):
    def setUp(self):
        self.motor = create_engine('sqlite://')
        self.addCleanup(self.motor.dispose)
        with self.motor.begin() as c:
            c.exec_driver_sql("ATTACH DATABASE ':memory:' AS public")
            for sentencia in [
                'CREATE TABLE public.federacion_autonomica (id_federacion INT, nombre TEXT)',
                'CREATE TABLE public.club (id_club INT, nombre TEXT, id_federacion INT)',
                'CREATE TABLE public.deportista (dni TEXT, nombre TEXT, apellidos TEXT, sexo TEXT, fecha_nacimiento DATE, id_club INT)',
                'CREATE TABLE public.clase (id_clase INT, nombre TEXT)',
                'CREATE TABLE public.unidad_competitiva (id_unidad INT, id_clase INT, fecha_inicio DATE, fecha_fin DATE)',
                'CREATE TABLE public.forma_parte (dni_deportista TEXT, id_unidad INT, rol TEXT)',
                'CREATE TABLE public.competicion (id_competicion INT, nombre TEXT, fecha_inicio DATE, fecha_fin DATE, nivel TEXT, localidad TEXT, id_clase INT)',
                'CREATE TABLE public.participa_en (id_unidad INT, id_competicion INT, posicion_general INT, posicion_categoria INT, puntos NUMERIC)',
                'CREATE TABLE public.registro_antropometrico (id_registro INT, dni_deportista TEXT, fecha DATE, altura NUMERIC, peso NUMERIC, envergadura NUMERIC, porcentaje_graso NUMERIC)',
                'CREATE TABLE public.tecnico (dni TEXT, nombre TEXT, apellidos TEXT)',
                'CREATE TABLE public.informe (id_informe INT, dni_deportista TEXT, dni_tecnico TEXT, fecha DATE, estrategia INT, tactica INT, trimado INT, tecnica INT, fortalezas TEXT, debilidades TEXT, recomendaciones TEXT)',
                "INSERT INTO public.deportista VALUES ('D1','Ana','Lago','Femenino','2010-01-01',NULL),('D2','Luis','Rey','Masculino',NULL,NULL)",
                "INSERT INTO public.clase VALUES (1,'420')",
                "INSERT INTO public.unidad_competitiva VALUES (1,1,'2025-01-01',NULL),(2,1,'2027-01-01',NULL)",
                "INSERT INTO public.forma_parte VALUES ('D1',1,'Patron'),('D2',1,'Tripulante'),('D1',2,'Patron')",
                "INSERT INTO public.competicion VALUES (1,'Finalizada','2025-05-01','2025-05-02','Nacional','Vigo',1),(2,'En curso','2026-11-09','2026-11-10','Nacional','Vigo',1)",
                'INSERT INTO public.participa_en VALUES (1,1,3,NULL,10),(1,2,1,NULL,5)',
                "INSERT INTO public.registro_antropometrico VALUES (1,'D1','2025-01-01',150,40,155,NULL),(2,'D1','2027-01-01',999,999,999,NULL)",
                "INSERT INTO public.tecnico VALUES ('T1','Técnica','Prueba')",
                "INSERT INTO public.informe VALUES (1,'D1','T1','2025-01-01',3,4,NULL,5,'Texto',NULL,NULL)",
            ]:
                c.exec_driver_sql(sentencia)

    def test_lecturas_constantes_equipo_doble_sin_producto_cartesiano(self):
        sentencias=[]
        event.listen(self.motor, 'before_cursor_execute', lambda c,cu,s,p,ctx,m:sentencias.append(s))
        datos=db.cargar_datos(self.motor, FECHA)
        self.assertEqual(len(sentencias),4)
        self.assertTrue(all(s.lstrip().startswith('SELECT') for s in sentencias))
        self.assertEqual(len(datos['unidades']),2)
        self.assertEqual(len(datos['resultados']),2)
        self.assertEqual({r['dni'] for r in datos['resultados']},{'D1','D2'})
        self.assertEqual({r['id_competicion'] for r in datos['resultados']},{1})
        self.assertIsInstance(datos['unidades'][0]['fecha_inicio'],date)
        self.assertEqual(len(datos['mediciones']),1)
        self.assertEqual(len(datos['informes']),1)
        self.assertIsNone(datos['unidades'][0]['club'])

    def test_fecha_validada_antes_de_consultar(self):
        with self.assertRaises(ValueError): db.cargar_datos(self.motor, '2026; DROP TABLE club')
