"""Identidades y alta/vinculación atómicas, sin conexiones a bases reales."""
from datetime import date, timedelta
import unittest
from sqlalchemy import text

import test_importaciones as fixtures
from services import revision_participantes as s
from services import importaciones as base
from services.deportistas import ValidacionError, ConflictoError


class RevisionParticipantes(unittest.TestCase):
    def setUp(self):
        self.db = fixtures.PersistenciaImportaciones()
        self.db.setUp()
        self.addCleanup(self.db.doCleanups)
        self.engine = self.db.engine
        self.ident = self.db.crear()
        self.nueva = dict(dni='D3', nombre='Persona', apellidos='Nueva', fecha_nacimiento=None,
                          sexo=None, id_club=2, rol_propuesto=None, observaciones_revision='Revisado')

    def persona(self, ident=None, indice=0):
        return s.cargar_revision(self.engine, ident or self.ident)['participantes_revision'][indice]

    def guardar(self, accion, campos=None, **extras):
        p = self.persona()
        return s.guardar_revision(self.engine, p['id_participante_importado'], accion,
                                  self.nueva if campos is None else campos, p['version'], **extras)

    def test_sugerencias_acentos_apellido_incompleto_y_contexto(self):
        with self.engine.begin() as c:
            c.exec_driver_sql("INSERT INTO deportista(dni,nombre,apellidos,id_club) VALUES ('D4','Ana','Perez García',2)")
        p = self.persona()
        encontrados = s.buscar_coincidencias(self.engine, p['id_participante_importado'])
        self.assertEqual(encontrados[0]['dni'], 'D1')
        self.assertIn('D4', [f['dni'] for f in encontrados])
        self.assertIn('nombre', encontrados[0]['motivos'])
        self.assertEqual(self.db.contar('coincidencia_propuesta'), 0)
        self.assertIsNone(self.persona()['dni_deportista_confirmado'])

    def test_busqueda_manual_por_documento_y_nombre(self):
        p = self.persona()
        self.assertEqual(s.buscar_coincidencias(self.engine, p['id_participante_importado'], 'd2')[0]['dni'], 'D2')
        self.assertEqual(s.buscar_coincidencias(self.engine, p['id_participante_importado'], 'Luis Lago')[0]['dni'], 'D2')
        self.assertEqual(s.buscar_coincidencias(self.engine, p['id_participante_importado'], "'; DROP TABLE deportista; --"), [])
        self.assertEqual(self.db.contar('deportista'), 2)

    def test_alias_confirmado_apoya_coincidencia(self):
        base.registrar_alias_club(self.engine, 'Club A', 1)
        p = self.persona()
        r = s.buscar_coincidencias(self.engine, p['id_participante_importado'])[0]
        self.assertIn('alias confirmado', r['motivos'])

    def test_creacion_vincula_sin_crear_resultados(self):
        self.guardar('crear', confirmar_nuevo_distinto=True)
        p = self.persona()
        self.assertEqual(p['dni_deportista_confirmado'], 'D3')
        self.assertEqual(p['estado'], 'nuevo_confirmado')
        self.assertEqual(p['nombre_original'], 'Ana Pérez')
        self.assertEqual(p['nombre_propuesto'], 'Persona')
        self.assertEqual(self.db.contar('deportista'), 3)
        self.assertEqual(self.db.contar('participa_en'), 0)
        self.assertEqual(self.db.contar('unidad_competitiva'), 0)
        self.assertEqual(p['fila']['estado'], 'lista')
        propuestas = base.obtener_borrador(self.engine, self.ident)['coincidencias']
        self.assertTrue(all(c['estado_revision'] == 'rechazada' for c in propuestas))

    def test_no_inventa_fecha_sexo_ni_documento(self):
        self.guardar('pendiente', {'nombre': 'Ana', 'id_club': 1})
        p = self.persona()
        self.assertEqual(p['estado'], 'pendiente_datos')
        for campo in ['documento_propuesto', 'fecha_nacimiento_propuesta', 'sexo_propuesto', 'dni_deportista_confirmado']:
            self.assertIsNone(p[campo])
        self.assertEqual(self.db.contar('deportista'), 2)

    def test_individual_asigna_patron_en_todas_las_decisiones(self):
        for accion in ('crear', 'vincular', 'pendiente'):
            with self.subTest(accion=accion):
                ident = self.db.crear()
                p = self.persona(ident)
                s.guardar_revision(self.engine, p['id_participante_importado'], accion,
                                   {**self.nueva, 'rol_propuesto': 'Tripulante'}, p['version'],
                                   dni_existente='D1', confirmar_nuevo_distinto=True)
                self.assertEqual(self.persona(ident)['rol_propuesto'], 'Patron')

    def test_documento_duplicado_no_crea_ficha(self):
        for dni, error in [('d1', ConflictoError)]:
            with self.assertRaises(error):
                self.guardar('crear', {**self.nueva, 'dni': dni}, confirmar_nuevo_distinto=True)
        self.assertEqual(self.db.contar('deportista'), 2)
        self.assertIsNone(self.persona()['dni_deportista_confirmado'])

    def test_documento_ausente_asigna_provisional(self):
        self.guardar('crear', {**self.nueva,'dni':''}, confirmar_nuevo_distinto=True)
        self.assertRegex(self.persona()['dni_deportista_confirmado'],r'^TEMP-[A-F0-9]{12}$')

    def test_coincidencias_exigen_confirmar_persona_distinta(self):
        with self.assertRaises(ValidacionError):
            self.guardar('crear')
        self.assertEqual(self.db.contar('deportista'), 2)
        self.assertEqual(self.db.contar('coincidencia_propuesta'), 0)

    def test_vinculo_no_modifica_ficha_y_guarda_decision(self):
        self.guardar('vincular', {'id_club': 2}, dni_existente='d1')
        p = self.persona()
        self.assertEqual(p['dni_deportista_confirmado'], 'D1')
        self.assertEqual(p['id_club_identificado'], 2)
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text("SELECT id_club FROM deportista WHERE dni='D1'")).scalar_one(), 1)
        coincidencias = base.obtener_borrador(self.engine, self.ident)['coincidencias']
        self.assertEqual(next(c for c in coincidencias if c['dni_deportista'] == 'D1')['estado_revision'], 'aceptada')
        self.assertEqual(self.db.contar('deportista'), 2)

    def test_no_permite_ficha_o_club_inexistente(self):
        with self.assertRaises(ValidacionError):
            self.guardar('vincular', {}, dni_existente='NO')
        with self.assertRaises(ValidacionError):
            self.guardar('crear', {**self.nueva, 'id_club': 99}, confirmar_nuevo_distinto=True)
        self.assertEqual(self.db.contar('deportista'), 2)

    def test_fallo_posterior_al_alta_revierte_todo(self):
        with self.engine.begin() as c:
            c.exec_driver_sql("""CREATE TRIGGER rechazar_alta BEFORE UPDATE ON participante_importado
                WHEN NEW.estado='nuevo_confirmado' BEGIN SELECT RAISE(ABORT,'fallo simulado'); END""")
        with self.assertRaises(ConflictoError):
            self.guardar('crear', confirmar_nuevo_distinto=True)
        self.assertEqual(self.db.contar('deportista'), 2)
        self.assertEqual(self.db.contar('coincidencia_propuesta'), 0)
        self.assertIsNone(self.persona()['dni_deportista_confirmado'])

    def test_edicion_pendiente_obsoleta_no_se_sobrescribe(self):
        p = self.persona()
        self.guardar('pendiente', {'nombre': 'Ana', 'observaciones_revision': 'Datos comprobados'})
        with self.assertRaises(ConflictoError):
            s.guardar_revision(self.engine, p['id_participante_importado'], 'crear', self.nueva,
                               p['version'], confirmar_nuevo_distinto=True)
        self.assertEqual(self.persona()['observaciones_revision'], 'Datos comprobados')
        self.assertEqual(self.db.contar('deportista'), 2)

    def test_confirmada_no_se_recrea_ni_vuelve_pendiente_por_accidente(self):
        self.guardar('vincular', {}, dni_existente='D1')
        for accion in ['crear', 'pendiente']:
            with self.assertRaises(ConflictoError):
                self.guardar(accion, confirmar_nuevo_distinto=True)
        self.assertEqual(self.db.contar('deportista'), 2)

    def test_se_puede_corregir_vinculo_y_propuestas(self):
        self.guardar('vincular', {}, dni_existente='D1')
        self.guardar('vincular', {}, dni_existente='D2')
        self.assertEqual(self.persona()['dni_deportista_confirmado'], 'D2')
        propuestas = base.obtener_borrador(self.engine, self.ident)['coincidencias']
        aceptadas = [p for p in propuestas if p['estado_revision'] == 'aceptada']
        self.assertEqual([p['dni_deportista'] for p in aceptadas], ['D2'])

    def test_excluidos_no_se_muestran_ni_se_confirman(self):
        ident = self.db.crear(filas=[{**self.db.filas[0], 'posicion_general': 81}])
        revision = s.cargar_revision(self.engine, ident)
        self.assertEqual(revision['participantes_revision'], [])
        p = revision['participantes'][0]
        with self.assertRaises(ValidacionError):
            s.guardar_revision(self.engine, p['id_participante_importado'], 'crear', self.nueva,
                               s.version_participante(p), confirmar_nuevo_distinto=True)
        self.assertEqual(self.db.contar('deportista'), 2)

    def test_importacion_cerrada_impide_guardar(self):
        with self.engine.begin() as c:
            c.execute(text("UPDATE importacion_clasificacion SET estado='cancelada' WHERE id_importacion=:id"), {'id': self.ident})
        with self.assertRaises(ConflictoError):
            self.guardar('crear', confirmar_nuevo_distinto=True)

    def test_completa_doble_y_controla_roles_y_documentos_repetidos(self):
        ident = self.db.crear(campos={**self.db.campos, 'id_clase': 2})
        p = self.persona(ident)
        s.agregar_miembro(self.engine, p['id_fila'], 'Luis Lago', 2)
        with self.assertRaises(ConflictoError):
            s.agregar_miembro(self.engine, p['id_fila'], 'Otra persona', 2)
        with self.assertRaises(ValidacionError):
            s.agregar_miembro(self.engine, p['id_fila'], 'Otro', 3)
        personas = s.cargar_revision(self.engine, ident)['participantes_revision']
        s.guardar_revision(self.engine, personas[0]['id_participante_importado'], 'vincular',
                           {'rol_propuesto': 'Patron'}, personas[0]['version'], dni_existente='D1')
        segundo = self.persona(ident, 1)
        with self.assertRaises(ConflictoError):
            s.guardar_revision(self.engine, segundo['id_participante_importado'], 'vincular',
                               {'rol_propuesto': 'Tripulante'}, segundo['version'], dni_existente='D1')
        s.guardar_revision(self.engine, segundo['id_participante_importado'], 'vincular',
                           {'rol_propuesto': 'Tripulante'}, segundo['version'], dni_existente='D2')
        self.assertEqual(self.persona(ident)['fila']['estado'], 'lista')
        self.assertEqual(self.db.contar('deportista'), 2)

    def test_no_cambia_caracter_deportivo_de_la_clasificacion(self):
        ident = self.db.crear(campos={**self.db.campos, 'tipo_clasificacion': 'provisional'})
        p = self.persona(ident)
        s.guardar_revision(self.engine, p['id_participante_importado'], 'vincular', {}, p['version'], dni_existente='D1')
        self.assertEqual(s.cargar_revision(self.engine, ident)['importacion']['tipo_clasificacion'], 'provisional')

    def test_fecha_posterior_a_la_regata_revierte_el_alta(self):
        inicio = date.today() - timedelta(days=30)
        ident = self.db.crear(campos={**self.db.campos, 'fecha_inicio_propuesta': inicio})
        p = self.persona(ident)
        with self.assertRaises(ValidacionError):
            s.guardar_revision(self.engine, p['id_participante_importado'], 'crear',
                               {**self.nueva, 'fecha_nacimiento': date.today() - timedelta(days=10)},
                               p['version'], confirmar_nuevo_distinto=True)
        self.assertEqual(self.db.contar('deportista'), 2)

    def test_fecha_oficial_prevalece_sobre_fecha_propuesta(self):
        oficial = date.today() - timedelta(days=30)
        with self.engine.begin() as c:
            c.execute(text('UPDATE competicion SET fecha_inicio=:fecha,fecha_fin=:fecha WHERE id_competicion=1'), {'fecha': oficial})
        ident = self.db.crear(campos={**self.db.campos, 'id_competicion': 1,
                                     'fecha_inicio_propuesta': date.today() - timedelta(days=20)})
        p = self.persona(ident)
        with self.assertRaises(ValidacionError):
            s.guardar_revision(self.engine, p['id_participante_importado'], 'crear',
                               {**self.nueva, 'fecha_nacimiento': date.today() - timedelta(days=25)},
                               p['version'], confirmar_nuevo_distinto=True)
        self.assertEqual(self.db.contar('deportista'), 2)

    def test_version_distingue_texto_none_y_campo_vacio(self):
        p = self.persona()
        self.assertNotEqual(s.version_participante(p), s.version_participante({**p, 'nombre_propuesto': 'None'}))

    def test_texto_no_se_interpreta_como_sql(self):
        nota = "'); DROP TABLE deportista; --"
        self.guardar('pendiente', {'observaciones_revision': nota})
        self.assertEqual(self.persona()['observaciones_revision'], nota)
        self.assertEqual(self.db.contar('deportista'), 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
