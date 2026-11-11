"""Pruebas sin credenciales: servicio real y esquema SQL adaptado a SQLite.

Solo se adaptan funciones/tipos y bloqueos propios de PostgreSQL. La migración
original se validó por separado en PostgreSQL temporal; aquí no se comprueba RLS
ni la concurrencia real de dos conexiones PostgreSQL.
"""
import copy
import json
import re
import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, event, text

from services import importaciones as s
from services.deportistas import ConflictoError, ValidacionError


class CriteriosSeleccion(unittest.TestCase):
    def test_cortes_y_empates(self):
        for nivel, corte in [('Autonomico', 40), ('Nacional', 80)]:
            for posicion, esperado in [(1, True), (corte, True), (corte, True), (corte + 1, False)]:
                self.assertIs(s.evaluar_seleccion(nivel, posicion)['cumple_criterio'], esperado)

    def test_internacional_numero_vela_no_nacionalidad(self):
        for vela in ['ESP 123', 'esp123', 'ESP-123', '123 ESP']:
            self.assertTrue(s.evaluar_seleccion('Internacional', 200, vela)['cumple_criterio'])
        for vela in ['GBR 123', 'DESP123', 'ESPECIAL', 'FRA 1']:
            self.assertFalse(s.evaluar_seleccion('Internacional', 1, vela)['cumple_criterio'])

    def test_dato_faltante_no_es_exclusion(self):
        self.assertIsNone(s.evaluar_seleccion('Nacional')['cumple_criterio'])
        self.assertIsNone(s.evaluar_seleccion('Internacional', 1)['cumple_criterio'])

    def test_argumentos_invalidos(self):
        for posicion in [True, 0, -1, '40', 1.5]:
            with self.assertRaises(ValidacionError):
                s.evaluar_seleccion('Nacional', posicion)
        with self.assertRaises(ValidacionError):
            s.evaluar_seleccion('Regional', 1)

    def test_preparacion_preserva_original_y_no_infiere_identidad(self):
        filas = [{'datos_originales': {'Nombre': 'Ana Pérez', 'Categoría': 'S13'},
                  'numero_vela_original': 'ESP 123', 'posicion_general': 1, 'puntos': '12,50',
                  'participantes': [{'nombre_original': 'Ana Pérez'}]}]
        antes = copy.deepcopy(filas)
        salida = s.preparar_filas(filas, 'Autonomico', 1)[0]
        self.assertEqual(filas, antes)
        self.assertEqual(salida['fila']['puntos'], Decimal('12.50'))
        self.assertEqual(salida['fila']['datos_originales'], antes[0]['datos_originales'])
        for campo in ['fecha_nacimiento_propuesta', 'documento_propuesto', 'sexo_propuesto']:
            self.assertIsNone(salida['participantes'][0][campo])
        self.assertNotIn('dni_deportista_confirmado', salida['participantes'][0])

    def test_equipo_esp_incluye_toda_la_tripulacion(self):
        fila = {'datos_originales': {}, 'numero_vela_original': 'ESP 1',
                'posicion_general': 120, 'puntos': 80,
                'participantes': [{'nombre_original': 'Ana'}, {'nombre_original': 'John'}]}
        preparado = s.preparar_filas([fila], 'Internacional', 2)[0]
        self.assertTrue(preparado['fila']['cumple_criterio'])
        self.assertEqual(len(preparado['participantes']), 2)
        self.assertEqual(preparado['fila']['estado'], 'pendiente')

    def test_pais_separado_no_sustituye_numero_vela(self):
        fila = {'datos_originales': {}, 'codigo_pais_vela': 'ESP',
                'numero_vela_original': 'GBR 1', 'posicion_general': 1, 'puntos': 0}
        self.assertFalse(s.preparar_filas([fila], 'Internacional', 1)[0]['fila']['cumple_criterio'])

    def test_incompletos_se_conservan_para_corregir(self):
        fila = {'datos_originales': {'posicion': 'DNF'}, 'numero_vela_original': 'ESP 12',
                'participantes': [{'nombre_original': 'Ana'}]}
        preparado = s.preparar_filas([fila], 'Internacional', 2)[0]['fila']
        self.assertEqual(preparado['estado'], 'requiere_correccion')
        for parte in ['posición', 'puntuación', '2 tripulantes']:
            self.assertIn(parte, preparado['incidencias'])

    def test_no_redondea_puntos_ni_admite_no_finitos(self):
        for puntos in [-1, True, 'NaN', 'Infinity', '1.234', '1.234,56', '100000000']:
            with self.subTest(puntos=puntos), self.assertRaises(ValidacionError):
                s.preparar_filas([{'datos_originales': {}, 'puntos': puntos}], 'Nacional', 1)

    def test_original_json_invalido(self):
        for original in [[], {'puntos': float('nan')}, {'fecha': date.today()}]:
            with self.assertRaises(ValidacionError):
                s.preparar_filas([{'datos_originales': original}], 'Nacional', 1)

    def test_no_acepta_confirmaciones_inyectadas(self):
        fila = {'datos_originales': {}, 'participantes': [{'nombre_original': 'Ana',
                                                        'dni_deportista_confirmado': 'D1'}]}
        with self.assertRaises(ValidacionError):
            s.preparar_filas([fila], 'Nacional', 1)
        with self.assertRaises(ValidacionError):
            s.preparar_filas([{'datos_originales': {}, 'cumple_criterio': True}], 'Nacional', 1)

    def test_numeros_fila_duplicados(self):
        with self.assertRaises(ValidacionError):
            s.preparar_filas([{'numero_fila': 1, 'datos_originales': {}},
                             {'numero_fila': 1, 'datos_originales': {}}], 'Nacional', 1)


class PersistenciaImportaciones(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        self.addCleanup(self.engine.dispose)

        @event.listens_for(self.engine, 'connect')
        def funciones(dbapi, _):
            dbapi.execute('PRAGMA foreign_keys=ON')
            dbapi.create_function('btrim', 1, lambda v: v.strip() if v is not None else None, deterministic=True)
            dbapi.create_function('jsonb_typeof', 1, lambda v: None if v is None else ('object' if isinstance(json.loads(v), dict) else 'array'))
            dbapi.create_function('regexp', 2, lambda patron, v: None if v is None else re.search(patron, v) is not None)

        @event.listens_for(self.engine, 'before_cursor_execute', retval=True)
        def adaptar(c, cursor, sql, parametros, contexto, many):
            return sql.replace('public.', '').replace(' FOR UPDATE OF i', ''), parametros

        # El DDL del proyecto es la fuente; no mantenemos otro modelo de tablas.
        esquema = (Path(__file__).resolve().parents[1] / 'sql/create_tables.sql').read_text()
        esquema = re.sub(r'SET LOCAL search_path[^;]+;', '', esquema)
        esquema = esquema.replace('INTEGER GENERATED ALWAYS AS IDENTITY', 'INTEGER')
        esquema = esquema.replace("'{}'::JSONB", "'{}'")
        esquema = re.sub(r'ALTER TABLE competicion\s+ADD CONSTRAINT uq_competicion_id_clase\s+UNIQUE \(id_competicion, id_clase\);',
                         'CREATE UNIQUE INDEX uq_competicion_id_clase ON competicion(id_competicion,id_clase);', esquema)
        esquema = re.sub(r'CREATE FUNCTION actualizar_fecha_importacion_clasificacion\(\).*?\$\$;', '', esquema, flags=re.S)
        esquema = re.sub(r'CREATE TRIGGER trg_importacion_actualizado_en.*?\(\);', '', esquema, flags=re.S)
        esquema = re.sub(r"COMMENT ON COLUMN\s+\S+\s+IS\s+'(?:''|[^'])*';", '', esquema, flags=re.S)
        esquema = re.sub(r'ALTER TABLE \w+ ENABLE ROW LEVEL SECURITY;', '', esquema)
        esquema = re.sub(r"(\w+) ~ ('[^']*')", r'REGEXP(\2, \1)', esquema)
        raw = self.engine.raw_connection()
        try:
            raw.executescript(esquema)
        finally:
            raw.close()
        with self.engine.begin() as c:
            c.exec_driver_sql("INSERT INTO federacion_autonomica(nombre) VALUES ('Federación')")
            c.exec_driver_sql("INSERT INTO club(nombre,id_federacion) VALUES ('Club A',1),('Club B',1)")
            c.exec_driver_sql("INSERT INTO clase(nombre,numero_tripulantes,es_olimpica) VALUES ('Optimist',1,0),('420',2,0)")
            c.exec_driver_sql("INSERT INTO deportista(dni,nombre,apellidos,id_club) VALUES ('D1','Ana','Pérez',1),('D2','Luis','Lago',1)")
            c.exec_driver_sql("INSERT INTO competicion(nombre,fecha_inicio,fecha_fin,nivel,id_clase) VALUES ('Regata','2026-10-01','2026-10-02','Nacional',1)")
        self.campos = dict(tipo_fuente='pdf', nombre_archivo='resultado.pdf',
                           referencia_documento='fuentes/resultado.pdf',
                           huella_documento=s.calcular_huella(b'%PDF-prueba'), id_clase=1,
                           nivel='Nacional', mapeo_columnas={'posicion_general': 'Pos', 'puntos': 'Total'})
        self.filas = [dict(numero_fila=1, datos_originales={'Nombre': 'Ana Pérez', 'Pos': '1'},
                           numero_vela_original='ESP 100', posicion_general=1, puntos='15,50',
                           participantes=[{'nombre_original': 'Ana Pérez', 'club_original': 'Club A'}])]

    def contar(self, tabla):
        permitidas = {'importacion_clasificacion', 'fila_clasificacion_importada', 'participante_importado',
                      'coincidencia_propuesta', 'alias_club', 'deportista', 'participa_en', 'unidad_competitiva'}
        assert tabla in permitidas
        with self.engine.connect() as c:
            return c.execute(text('SELECT COUNT(*) FROM ' + tabla)).scalar_one()

    def crear(self, campos=None, filas=None):
        return s.crear_borrador(self.engine, self.campos if campos is None else campos,
                               self.filas if filas is None else filas)

    def participante(self, identificador):
        return s.obtener_borrador(self.engine, identificador)['participantes'][0]['id_participante_importado']

    def test_crear_y_recuperar_sin_alterar_datos_definitivos(self):
        ident = self.crear()
        borrador = s.obtener_borrador(self.engine, ident)
        self.assertEqual(borrador['importacion']['estado'], 'en_revision')
        self.assertEqual(borrador['importacion']['mapeo_columnas'], self.campos['mapeo_columnas'])
        self.assertEqual(borrador['importacion']['criterio_inclusion']['posicion_maxima'], 80)
        self.assertEqual(borrador['filas'][0]['datos_originales'], self.filas[0]['datos_originales'])
        self.assertEqual(borrador['filas'][0]['puntos'], Decimal('15.50'))
        self.assertIs(borrador['filas'][0]['cumple_criterio'], True)
        self.assertIsNone(borrador['participantes'][0]['dni_deportista_confirmado'])
        self.assertEqual(self.contar('deportista'), 2)
        self.assertEqual(self.contar('participa_en'), 0)
        self.assertEqual(self.contar('unidad_competitiva'), 0)

    def test_filas_fuera_corte_y_pendientes_se_conservan(self):
        filas = [self.filas[0], {**self.filas[0], 'numero_fila': 2, 'posicion_general': 81},
                 {'numero_fila': 3, 'datos_originales': {}}]
        b = s.obtener_borrador(self.engine, self.crear(filas=filas))
        self.assertEqual([f['estado'] for f in b['filas']], ['pendiente', 'excluida', 'requiere_correccion'])
        self.assertEqual(len(b['filas']), 3)

    def test_fallo_tardio_revierte_importacion_y_todas_sus_filas(self):
        mala = {**self.filas[0], 'numero_fila': 2,
                'participantes': [{'nombre_original': 'Luis', 'id_club_identificado': 999}]}
        with self.assertRaises(ConflictoError):
            self.crear(filas=[self.filas[0], mala])
        for tabla in ['importacion_clasificacion', 'fila_clasificacion_importada', 'participante_importado']:
            self.assertEqual(self.contar(tabla), 0)

    def test_fallo_de_guardado_conserva_borrador_previo(self):
        ident = s.crear_borrador(self.engine, self.campos)
        malas = [self.filas[0], {**self.filas[0], 'numero_fila': 2,
                                'participantes': [{'nombre_original': 'Luis', 'id_club_identificado': 999}]}]
        with self.assertRaises(ConflictoError):
            s.guardar_filas(self.engine, ident, malas)
        b = s.obtener_borrador(self.engine, ident)
        self.assertEqual(b['importacion']['estado'], 'recibida')
        self.assertEqual(b['filas'], [])

    def test_no_sobrescribe_revision(self):
        ident = self.crear()
        with self.assertRaises(ConflictoError):
            s.guardar_filas(self.engine, ident, self.filas)
        self.assertEqual(self.contar('fila_clasificacion_importada'), 1)

    def test_propuestas_no_confirman_y_usuario_vincula(self):
        ident = self.crear()
        p = self.participante(ident)
        s.proponer_coincidencias(self.engine, p, [dict(dni_deportista='D1', indice_similitud='0.9', motivos='Nombre y club'),
                                                 dict(dni_deportista='D2', indice_similitud='0.5')])
        self.assertIsNone(s.obtener_borrador(self.engine, ident)['participantes'][0]['dni_deportista_confirmado'])
        s.vincular_participante(self.engine, p, 'D1')
        b = s.obtener_borrador(self.engine, ident)
        self.assertEqual(b['participantes'][0]['dni_deportista_confirmado'], 'D1')
        self.assertEqual(b['coincidencias'][0]['estado_revision'], 'aceptada')
        self.assertEqual(self.contar('deportista'), 2)

    def test_vinculo_con_club_historico_no_modifica_ficha(self):
        filas = [{**self.filas[0], 'participantes': [{'nombre_original': 'Ana', 'id_club_identificado': 2}]}]
        ident = self.crear(filas=filas)
        s.vincular_participante(self.engine, self.participante(ident), 'D1')
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text("SELECT id_club FROM deportista WHERE dni='D1'")).scalar_one(), 1)

    def test_identidad_concurrente_no_se_sobrescribe(self):
        ident = self.crear()
        p = self.participante(ident)
        s.vincular_participante(self.engine, p, 'D1')
        with self.assertRaises(ConflictoError):
            s.vincular_participante(self.engine, p, 'D2')
        s.vincular_participante(self.engine, p, 'D2', documento_anterior='D1')
        self.assertEqual(s.obtener_borrador(self.engine, ident)['participantes'][0]['dni_deportista_confirmado'], 'D2')

    def test_fila_excluida_no_admite_vinculo(self):
        ident = self.crear(filas=[{**self.filas[0], 'posicion_general': 81}])
        with self.assertRaises(ValidacionError):
            s.vincular_participante(self.engine, self.participante(ident), 'D1')

    def test_doble_no_admite_mismo_deportista_dos_veces(self):
        filas = [{**self.filas[0], 'participantes': [{'nombre_original': 'Ana'}, {'nombre_original': 'Luis'}]}]
        ident = self.crear(campos={**self.campos, 'id_clase': 2}, filas=filas)
        participantes = s.obtener_borrador(self.engine, ident)['participantes']
        s.vincular_participante(self.engine, participantes[0]['id_participante_importado'], 'D1')
        with self.assertRaises(ConflictoError):
            s.vincular_participante(self.engine, participantes[1]['id_participante_importado'], 'D1')
        self.assertIsNone(s.obtener_borrador(self.engine, ident)['participantes'][1]['dni_deportista_confirmado'])

    def test_candidato_inexistente_revierte_todas_las_propuestas(self):
        ident = self.crear()
        with self.assertRaises(ValidacionError):
            s.proponer_coincidencias(self.engine, self.participante(ident), [dict(dni_deportista='D1'), dict(dni_deportista='NO')])
        self.assertEqual(self.contar('coincidencia_propuesta'), 0)

    def test_estado_final_no_admite_edicion(self):
        ident = self.crear()
        with self.engine.begin() as c:
            c.execute(text("UPDATE importacion_clasificacion SET estado='cancelada' WHERE id_importacion=:id"), {'id': ident})
        with self.assertRaises(ConflictoError):
            s.vincular_participante(self.engine, self.participante(ident), 'D1')

    def test_alias_normaliza_acentos_y_controla_contexto(self):
        s.registrar_alias_club(self.engine, ' Náutico ', 1)
        with self.assertRaises(ConflictoError):
            s.registrar_alias_club(self.engine, 'NAUTICO', 2)
        s.registrar_alias_club(self.engine, 'Náutico', 2, 'Otra fuente')
        self.assertEqual(self.contar('alias_club'), 2)

    def test_sql_inyectado_permanece_como_texto(self):
        malicioso = "Ana'); DROP TABLE deportista; --"
        ident = self.crear(filas=[{**self.filas[0], 'participantes': [{'nombre_original': malicioso}]}])
        self.assertEqual(s.obtener_borrador(self.engine, ident)['participantes'][0]['nombre_original'], malicioso)
        self.assertEqual(self.contar('deportista'), 2)

    def test_completar_metadatos_antes_de_cargar(self):
        campos = {**self.campos, 'nivel': None}
        ident = s.crear_borrador(self.engine, campos)
        b = s.obtener_borrador(self.engine, ident)
        s.actualizar_borrador(self.engine, ident, self.campos, b['importacion']['actualizado_en'])
        s.guardar_filas(self.engine, ident, self.filas)
        self.assertEqual(len(s.obtener_borrador(self.engine, ident)['filas']), 1)

    def test_metadatos_no_cambian_despues_de_guardar_filas(self):
        ident = self.crear()
        b = s.obtener_borrador(self.engine, ident)
        with self.assertRaises(ConflictoError):
            s.actualizar_borrador(self.engine, ident, self.campos, b['importacion']['actualizado_en'])

    def test_no_sustituye_fuente_de_un_borrador(self):
        ident = s.crear_borrador(self.engine, self.campos)
        b = s.obtener_borrador(self.engine, ident)
        with self.assertRaises(ValidacionError):
            s.actualizar_borrador(self.engine, ident, {**self.campos, 'huella_documento': 'b' * 64}, b['importacion']['actualizado_en'])

    def test_metadatos_referencias_invalidas(self):
        for extra in [{'id_clase': 999}, {'id_clase': 2, 'id_competicion': 1}, {'id_competicion': 1, 'nivel': 'Autonomico'}]:
            with self.assertRaises(ValidacionError):
                self.crear(campos={**self.campos, **extra})
        self.assertEqual(self.contar('importacion_clasificacion'), 0)

    def test_metadatos_no_validos(self):
        for extra in [{'huella_documento': 'abc'}, {'id_clase': True}, {'tipo_fuente': 'csv'},
                      {'nombre_archivo': ''}, {'estado': 'completada'}, {'mapeo_columnas': []},
                      {'fecha_inicio_propuesta': date(2026, 2, 2), 'fecha_fin_propuesta': date(2026, 1, 1)},
                      {'fecha_actualizacion_fuente': datetime(2026, 1, 1)}]:
            with self.subTest(extra=extra), self.assertRaises(ValidacionError):
                s.crear_borrador(self.engine, {**self.campos, **extra})

    def test_actualizacion_metadatos_obsoleta_no_se_guarda(self):
        ident = s.crear_borrador(self.engine, self.campos)
        b = s.obtener_borrador(self.engine, ident)
        anterior = b['importacion']['actualizado_en'] - timedelta(seconds=1)
        with self.assertRaises(ConflictoError):
            s.actualizar_borrador(self.engine, ident, {**self.campos, 'nivel': 'Autonomico'}, anterior)
        self.assertEqual(s.obtener_borrador(self.engine, ident)['importacion']['nivel'], 'Nacional')

    def test_cambiar_identidad_actualiza_propuestas_sin_doble_aceptacion(self):
        ident = self.crear()
        p = self.participante(ident)
        s.proponer_coincidencias(self.engine, p, [{'dni_deportista': 'D1'}, {'dni_deportista': 'D2'}])
        s.vincular_participante(self.engine, p, 'd1')
        s.vincular_participante(self.engine, p, 'D2', documento_anterior='D1')
        estados = {c['dni_deportista']: c['estado_revision'] for c in s.obtener_borrador(self.engine, ident)['coincidencias']}
        self.assertEqual(estados, {'D1': 'rechazada', 'D2': 'aceptada'})

    def test_similitud_invalida_no_deja_propuestas(self):
        ident = self.crear()
        p = self.participante(ident)
        for indice in [True, 'NaN', -1, 2, '0.123456']:
            with self.assertRaises(ValidacionError):
                s.proponer_coincidencias(self.engine, p, [{'dni_deportista': 'D1', 'indice_similitud': indice}])
        self.assertEqual(self.contar('coincidencia_propuesta'), 0)

    def test_alias_vacio_tras_normalizar_no_se_guarda(self):
        for alias in ['___', '---', 'ß' * 250]:
            with self.assertRaises(ValidacionError):
                s.registrar_alias_club(self.engine, alias, 1)
        self.assertEqual(self.contar('alias_club'), 0)

    def test_listados_paginados_y_ausentes(self):
        uno = s.crear_borrador(self.engine, self.campos)
        dos = s.crear_borrador(self.engine, self.campos)
        self.assertEqual(s.listar_borradores(self.engine, 1)[0]['id_importacion'], dos)
        self.assertEqual(s.listar_borradores(self.engine, 1, 1)[0]['id_importacion'], uno)
        self.assertIsNone(s.obtener_borrador(self.engine, 999))
        with self.assertRaises(ValidacionError):
            s.listar_borradores(self.engine, 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
