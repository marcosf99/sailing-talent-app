"""Resultado visible en ficha, importación parcial y conflictos sin bases reales."""
from datetime import date
import unittest
from sqlalchemy import event, text

import test_importaciones as fixtures
from database import queries
from services import importaciones as base
from services import revision_participantes as revision
from services import resultados_importados as s
from services.deportistas import ValidacionError, ConflictoError


class ResultadosImportados(unittest.TestCase):
    def setUp(self):
        self.db = fixtures.PersistenciaImportaciones()
        self.db.setUp()
        self.addCleanup(self.db.doCleanups)
        self.engine = self.db.engine
        @event.listens_for(self.engine, 'before_cursor_execute', retval=True)
        def bloqueos(c, cursor, sql, parametros, contexto, many):
            return sql.replace(' FOR UPDATE', ''), parametros
        self.campos = dict(nombre='Vigo', fecha_inicio=date(2026, 10, 3), fecha_fin=date(2026, 10, 4),
                           localidad='Vigo', tipo_clasificacion='definitiva')
        self.ident = self.db.crear()

    def contenido(self, ident=None):
        return base.obtener_borrador(self.engine, ident or self.ident)

    def confirmar(self, indice=0, dni='D1', ident=None, rol=None):
        p = self.contenido(ident)['participantes'][indice]
        revision.guardar_revision(self.engine, p['id_participante_importado'], 'vincular',
                                   {'rol_propuesto': rol}, revision.version_participante(p), dni_existente=dni)

    def aplicar(self, filas=None, campos=None, ident=None, version=None):
        b = self.contenido(ident)
        ids = [f['id_fila'] for f in b['filas']] if filas is None else filas
        return s.incorporar(self.engine, ident or self.ident, ids,
                            self.campos if campos is None else campos,
                            s.version_resultados(b) if version is None else version)

    def contar(self, tabla):
        assert tabla in ('competicion', 'unidad_competitiva', 'forma_parte', 'participa_en', 'deportista')
        with self.engine.connect() as c:
            return c.execute(text('SELECT COUNT(*) FROM ' + tabla)).scalar_one()

    def test_ficha_muestra_resultado_y_no_recrea_deportista(self):
        self.confirmar()
        self.assertEqual(self.aplicar(), 1)
        filas = queries.consultar_resultados_deportista(self.engine, 'D1', fecha_referencia=date(2026, 11, 11))
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]['competicion'], 'Vigo')
        self.assertEqual(filas[0]['posicion_general'], 1)
        self.assertEqual(filas[0]['rol'], 'Patron')
        self.assertEqual(self.contar('deportista'), 2)
        b = self.contenido()
        self.assertEqual(b['importacion']['estado'], 'completada')
        self.assertEqual(b['filas'][0]['estado'], 'importada')
        self.assertEqual(b['filas'][0]['id_competicion_confirmada'], filas[0]['id_competicion'])
        with self.engine.connect() as c:
            u = c.execute(text('SELECT * FROM unidad_competitiva')).mappings().one()
            self.assertEqual(u['fecha_inicio'], '2026-10-03')
            self.assertIsNone(u['fecha_fin'])

    def test_reintento_y_borrador_duplicado_no_duplican_resultado(self):
        self.confirmar(); self.aplicar()
        self.assertEqual(self.aplicar(), 0)
        otro = self.db.crear()
        self.confirmar(ident=otro)
        self.assertEqual(self.aplicar(ident=otro), 1)
        self.assertEqual(self.contar('competicion'), 2)
        self.assertEqual(self.contar('unidad_competitiva'), 1)
        self.assertEqual(self.contar('participa_en'), 1)

    def test_identidades_confirmadas_antes_del_nuevo_paso_son_recuperables(self):
        p = self.contenido()['participantes'][0]
        base.vincular_participante(self.engine, p['id_participante_importado'], 'D1')
        self.assertIsNone(self.contenido()['participantes'][0]['rol_propuesto'])
        self.assertEqual(len(s.filas_preparadas(self.contenido())), 1)
        self.aplicar()
        self.assertEqual(queries.consultar_resultados_deportista(self.engine, 'D1')[0]['rol'], 'Patron')

    def test_competicion_asociada_se_reutiliza(self):
        ident = self.db.crear(campos={**self.db.campos, 'id_competicion': 1})
        self.confirmar(ident=ident)
        self.aplicar(ident=ident, campos={**self.campos, 'nombre': 'Regata', 'localidad': None,
                     'fecha_inicio': date(2026, 10, 1), 'fecha_fin': date(2026, 10, 2)})
        self.assertEqual(self.contar('competicion'), 1)
        self.assertEqual(self.contenido(ident)['filas'][0]['id_competicion_confirmada'], 1)

    def test_lote_con_puestos_o_deportistas_repetidos_no_se_guarda(self):
        for dni, puesto in [('D2', 1), ('D1', 2)]:
            with self.subTest(dni=dni, puesto=puesto):
                ident = self.db.crear(filas=[self.db.filas[0], {**self.db.filas[0],
                    'numero_fila': 2, 'posicion_general': puesto}])
                self.confirmar(ident=ident); self.confirmar(1, dni, ident)
                with self.assertRaises(ConflictoError): self.aplicar(ident=ident)
                self.assertEqual(self.contar('participa_en'), 0)
                self.assertEqual(self.contar('competicion'), 1)

    def test_pendiente_y_excluida_no_se_incorporan(self):
        self.assertEqual(s.filas_preparadas(self.contenido()), [])
        with self.assertRaises(ValidacionError): self.aplicar()
        otro = self.db.crear(filas=[{**self.db.filas[0], 'posicion_general': 81}])
        with self.assertRaises(ValidacionError): self.aplicar(ident=otro)
        self.assertEqual(self.contar('participa_en'), 0)

    def test_parcial_permite_revisar_e_incorporar_las_restantes(self):
        filas = [self.db.filas[0], {**self.db.filas[0], 'numero_fila': 2, 'posicion_general': 2,
                                  'participantes': [{'nombre_original': 'Luis Lago'}]}]
        ident = self.db.crear(filas=filas)
        self.confirmar(ident=ident)
        ids = [f['id_fila'] for f in self.contenido(ident)['filas']]
        self.aplicar(filas=ids[:1], ident=ident)
        self.assertEqual(self.contenido(ident)['importacion']['estado'], 'parcialmente_importada')
        self.confirmar(1, 'D2', ident)
        self.assertEqual(self.contenido(ident)['importacion']['estado'], 'parcialmente_importada')
        self.aplicar(filas=ids[1:], ident=ident)
        self.assertEqual(self.contenido(ident)['importacion']['estado'], 'completada')
        self.assertEqual(self.contar('participa_en'), 2)

    def test_reutiliza_unidad_compatible_sin_cambiar_fechas(self):
        with self.engine.begin() as c:
            c.exec_driver_sql("INSERT INTO unidad_competitiva VALUES (1,'2026-01-01',NULL,1)")
            c.exec_driver_sql("INSERT INTO forma_parte VALUES ('D1',1,'Patron')")
        self.confirmar();self.aplicar()
        self.assertEqual(self.contar('unidad_competitiva'), 1)
        with self.engine.connect() as c:
            self.assertIsNone(c.execute(text('SELECT fecha_fin FROM unidad_competitiva')).scalar_one())

    def test_solapamiento_incompatible_revierte_competicion_y_resultados(self):
        with self.engine.begin() as c:
            c.exec_driver_sql("INSERT INTO unidad_competitiva VALUES (1,'2026-10-04',NULL,1)")
            c.exec_driver_sql("INSERT INTO forma_parte VALUES ('D1',1,'Patron')")
        self.confirmar()
        with self.assertRaises(ConflictoError): self.aplicar()
        self.assertEqual(self.contar('competicion'), 1)
        self.assertIsNone(self.contenido()['importacion']['id_competicion'])

    def test_puestos_duplicados_bloqueados_tambien_en_lotes_distintos(self):
        self.confirmar();self.aplicar()
        otro = self.db.crear()
        self.confirmar(dni='D2', ident=otro)
        with self.assertRaises(ConflictoError): self.aplicar(ident=otro)
        self.assertEqual(self.contar('participa_en'), 1)
        self.assertEqual(self.contar('unidad_competitiva'), 1)
        self.assertIsNone(self.contenido(otro)['importacion']['id_competicion'])

    def test_puntos_conflictivos_no_sobrescriben_resultado(self):
        self.confirmar();self.aplicar()
        otro = self.db.crear(filas=[{**self.db.filas[0], 'puntos': 30}])
        self.confirmar(ident=otro)
        with self.assertRaises(ConflictoError): self.aplicar(ident=otro)
        resultado = queries.consultar_resultados_deportista(self.engine, 'D1')[0]
        self.assertEqual(float(resultado['puntos']), 15.5)

    def test_fallo_tardio_revierte_resultados_y_vinculos_pero_conserva_altas(self):
        self.confirmar()
        with self.engine.begin() as c:
            c.exec_driver_sql("""CREATE TRIGGER fallo BEFORE UPDATE ON fila_clasificacion_importada
                              WHEN NEW.estado='importada' BEGIN SELECT RAISE(ABORT,'fallo'); END""")
        with self.assertRaises(ConflictoError): self.aplicar()
        for tabla in ('unidad_competitiva', 'forma_parte', 'participa_en'):
            self.assertEqual(self.contar(tabla), 0)
        self.assertEqual(self.contar('competicion'), 1)
        self.assertEqual(self.contar('deportista'), 2)
        self.assertEqual(self.contenido()['participantes'][0]['dni_deportista_confirmado'], 'D1')
        self.assertIsNone(self.contenido()['importacion']['id_competicion'])

    def test_revision_obsoleta_no_incorpora(self):
        version = s.version_resultados(self.contenido())
        self.confirmar()
        with self.assertRaises(ConflictoError): self.aplicar(version=version)
        self.assertEqual(self.contar('participa_en'), 0)

    def test_metadatos_obligatorios_y_cancelacion(self):
        self.confirmar()
        for cambio in ({'nombre': ''}, {'fecha_inicio': None}, {'fecha_fin': date(2026, 1, 1)},
                       {'tipo_clasificacion': 'sin_confirmar'}, {'fecha_fin': date(2099, 1, 1)}):
            with self.subTest(cambio=cambio), self.assertRaises(ValidacionError):
                self.aplicar(campos={**self.campos, **cambio})
        with self.engine.begin() as c:
            c.execute(text("UPDATE importacion_clasificacion SET estado='cancelada' WHERE id_importacion=:id"), {'id': self.ident})
        with self.assertRaises(ConflictoError): self.aplicar()

    def test_equipo_doble_solo_con_ambos_confirmados_y_roles(self):
        filas = [{**self.db.filas[0], 'participantes': [{'nombre_original': 'Ana'}, {'nombre_original': 'Luis'}]}]
        ident = self.db.crear(campos={**self.db.campos, 'id_clase': 2}, filas=filas)
        self.confirmar(ident=ident, rol='Patron')
        with self.assertRaises(ValidacionError): self.aplicar(ident=ident)
        self.confirmar(1, 'D2', ident, 'Patron')
        with self.assertRaises(ValidacionError): self.aplicar(ident=ident)
        self.confirmar(1, 'D2', ident, 'Tripulante')
        self.aplicar(ident=ident)
        for dni in ('D1', 'D2'):
            self.assertEqual(len(queries.consultar_resultados_deportista(self.engine, dni)), 1)
        self.assertEqual(self.contar('participa_en'), 1)

    def test_competicion_existente_no_cambia_y_sql_es_literal(self):
        self.confirmar()
        with self.assertRaises(ConflictoError):
            self.aplicar(campos={**self.campos, 'nombre': 'Regata', 'fecha_inicio': date(2026, 10, 1),
                                 'fecha_fin': date(2026, 10, 2)})
        nombre = "Vigo'); DROP TABLE deportista; --"
        self.aplicar(campos={**self.campos, 'nombre': nombre})
        self.assertEqual(queries.consultar_resultados_deportista(self.engine, 'D1')[0]['competicion'], nombre)
        self.assertEqual(self.contar('deportista'), 2)

    def test_identidad_no_se_modifica_tras_incorporar_resultado(self):
        self.confirmar();self.aplicar()
        with self.assertRaises((ValidacionError, ConflictoError)):
            self.confirmar(dni='D2')

    def alta_con_resultado(self, indice=0, ident=None, dni='D3', rol=None, accion='crear',
                          metadatos=None, version_importacion=None):
        b = self.contenido(ident)
        p = b['participantes'][indice]
        return s.guardar_con_resultado(self.engine, p['id_participante_importado'], accion,
            dict(dni=dni, nombre='Persona', apellidos='Nueva', rol_propuesto=rol),
            revision.version_participante(p), dni, True,
            self.campos if metadatos is None else metadatos,
            s.version_resultados(b) if version_importacion is None else version_importacion)

    def test_alta_y_resultado_en_una_accion(self):
        resultado = self.alta_con_resultado()
        self.assertTrue(resultado['resultado_incorporado'])
        self.assertEqual(resultado['dni'], 'D3')
        self.assertEqual(self.contar('deportista'), 3)
        consulta = queries.consultar_resultados_deportista(self.engine, 'D3')
        self.assertEqual(consulta[0]['posicion_general'], 1)
        self.assertEqual(consulta[0]['competicion'], 'Vigo')

    def test_resultado_fallido_revierte_tambien_alta(self):
        with self.engine.begin() as c:
            c.exec_driver_sql("""CREATE TRIGGER fallo BEFORE INSERT ON participa_en
                              BEGIN SELECT RAISE(ABORT,'fallo'); END""")
        with self.assertRaises(ConflictoError): self.alta_con_resultado()
        self.assertEqual(self.contar('deportista'), 2)
        self.assertEqual(self.contar('competicion'), 1)
        self.assertEqual(self.contar('unidad_competitiva'), 0)
        self.assertIsNone(self.contenido()['participantes'][0]['dni_deportista_confirmado'])

    def test_puesto_ocupado_revierte_alta_automatica(self):
        self.confirmar();self.aplicar()
        otro = self.db.crear()
        with self.assertRaises(ConflictoError): self.alta_con_resultado(ident=otro)
        self.assertEqual(self.contar('deportista'), 2)
        self.assertEqual(self.contar('participa_en'), 1)
        self.assertIsNone(self.contenido(otro)['participantes'][0]['dni_deportista_confirmado'])

    def test_doble_nuevo_espera_y_ultimo_alta_incorpora_ambos(self):
        ident = self.db.crear(campos={**self.db.campos, 'id_clase': 2}, filas=[{
            **self.db.filas[0], 'participantes': [{'nombre_original': 'Persona Nueva'}, {'nombre_original': 'Otra Persona'}]}])
        primero = self.alta_con_resultado(ident=ident, rol='Patron')
        self.assertTrue(primero['pendiente_equipo'])
        self.assertEqual(self.contar('participa_en'), 0)
        self.assertEqual(self.contar('competicion'), 1)
        self.assertEqual(self.contenido(ident)['importacion']['nombre_competicion_propuesto'], 'Vigo')
        segundo = self.alta_con_resultado(1, ident, 'D4', 'Tripulante')
        self.assertTrue(segundo['resultado_incorporado'])
        self.assertEqual(self.contar('participa_en'), 1)
        for dni in ('D3', 'D4'):
            self.assertEqual(len(queries.consultar_resultados_deportista(self.engine, dni)), 1)

    def test_doble_mixto_incorpora_al_confirmar_el_segundo_miembro(self):
        ident = self.db.crear(campos={**self.db.campos, 'id_clase': 2}, filas=[{
            **self.db.filas[0], 'participantes': [{'nombre_original': 'Persona Nueva'}, {'nombre_original': 'Luis Lago'}]}])
        self.alta_con_resultado(ident=ident, rol='Patron')
        resultado = self.alta_con_resultado(1, ident, 'D2', 'Tripulante', accion='vincular')
        self.assertTrue(resultado['resultado_incorporado'])
        self.assertEqual(self.contar('deportista'), 3)
        for dni in ('D3', 'D2'):
            self.assertEqual(len(queries.consultar_resultados_deportista(self.engine, dni)), 1)

    def test_vinculo_existente_conserva_proceso_manual(self):
        resultado = self.alta_con_resultado(dni='D1', accion='vincular')
        self.assertFalse(resultado['resultado_incorporado'])
        self.assertFalse(resultado['pendiente_equipo'])
        self.assertEqual(self.contar('participa_en'), 0)
        self.assertEqual(len(s.filas_preparadas(self.contenido())), 1)

    def test_metadatos_invalidos_o_revision_obsoleta_no_crean_ficha(self):
        with self.assertRaises(ValidacionError):
            self.alta_con_resultado(metadatos={**self.campos, 'fecha_inicio': None})
        with self.assertRaises(ConflictoError):
            self.alta_con_resultado(version_importacion='obsoleta')
        self.assertEqual(self.contar('deportista'), 2)
        self.assertIsNone(self.contenido()['participantes'][0]['dni_deportista_confirmado'])

    def test_regatas_sucesivas_reutilizan_unidad_abierta(self):
        self.confirmar();self.aplicar()
        otro=self.db.crear()
        self.confirmar(ident=otro)
        self.aplicar(ident=otro,campos={**self.campos,'nombre':'Segunda regata',
                     'fecha_inicio':date(2026,10,20),'fecha_fin':date(2026,10,21)})
        self.assertEqual(self.contar('unidad_competitiva'),1)
        self.assertEqual(self.contar('participa_en'),2)
        with self.engine.connect() as c:
            unidad=c.execute(text('SELECT fecha_inicio,fecha_fin FROM unidad_competitiva')).mappings().one()
            self.assertEqual(unidad['fecha_inicio'],'2026-10-03')
            self.assertIsNone(unidad['fecha_fin'])

    def test_nueva_unidad_abierta_no_solapa_equipo_posterior_a_la_regata(self):
        with self.engine.begin() as c:
            c.exec_driver_sql("INSERT INTO unidad_competitiva VALUES (1,'2026-10-20',NULL,1)")
            c.exec_driver_sql("INSERT INTO forma_parte VALUES ('D1',1,'Patron')")
        self.confirmar()
        with self.assertRaisesRegex(ConflictoError,'posterior'):
            self.aplicar()
        self.assertEqual(self.contar('participa_en'),0)

    def test_optimist_limite_14_y_edad_desconocida(self):
        with self.engine.begin() as c:
            c.exec_driver_sql("UPDATE deportista SET fecha_nacimiento='2011-12-30' WHERE dni='D1'")
        self.confirmar()
        with self.assertRaisesRegex(ValidacionError,'Optimist'):
            self.aplicar()
        self.assertEqual(self.contar('participa_en'),0)
        with self.engine.begin() as c:
            c.exec_driver_sql("UPDATE deportista SET fecha_nacimiento='2012-12-30' WHERE dni='D1'")
        self.aplicar()
        with self.engine.connect() as c:
            self.assertIsNone(c.execute(text('SELECT fecha_fin FROM unidad_competitiva')).scalar_one())

    def test_edad_incompatible_revierte_alta_con_resultado(self):
        b=self.contenido();p=b['participantes'][0]
        with self.assertRaisesRegex(ValidacionError,'Optimist'):
            s.guardar_con_resultado(self.engine,p['id_participante_importado'],'crear',
                dict(dni='D3',nombre='Nueva',apellidos='Persona',fecha_nacimiento=date(2011,1,1)),
                revision.version_participante(p),None,True,self.campos,s.version_resultados(b))
        self.assertEqual(self.contar('deportista'),2)
        self.assertEqual(self.contar('participa_en'),0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
