"""Pantalla de revisión con lecturas y guardados simulados, sin proveedores reales."""
import copy
from datetime import date
from decimal import Decimal
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from app import datos
from services import importaciones as base
from services import revision_participantes as s
from services import resultados_importados as resultados
from services import revision_lotes
from services import deportistas

SCRIPT = '''
from app import revision_participantes
def lectura(clave, funcion, *args):
    return funcion(*args)
revision_participantes.mostrar("supabase", "motor", lectura)
'''
CLUBES = [dict(id_club=1, nombre='Club A', id_federacion=1, federacion='Galicia'),
          dict(id_club=2, nombre='Club B', id_federacion=2, federacion='Baleares')]
FEDS = [dict(id_federacion=1, nombre='Galicia'), dict(id_federacion=2, nombre='Baleares')]


def persona(ident, fila, nombre):
    return dict(id_participante_importado=ident, id_fila=fila, nombre_original=nombre,
                orden_en_tripulacion=1, nombre_propuesto=None, apellidos_propuestos=None,
                documento_propuesto=None, fecha_nacimiento_propuesta=None, sexo_propuesto=None,
                club_original='Club A', federacion_original=None, id_club_identificado=None,
                rol_propuesto=None, estado='pendiente_revision', observaciones_revision=None,
                dni_deportista_confirmado=None, confirmado_en=None)


def fila(ident, puesto, seleccionada=True):
    return dict(id_fila=ident, id_importacion=1, numero_fila=puesto, pagina_origen=1,
                posicion_general=puesto, puntos=Decimal('20'), numero_vela_original=f'ESP {puesto}',
                cumple_criterio=seleccionada, estado='pendiente' if seleccionada else 'excluida', incidencias=None,
                datos_originales={'columnas': {'c0': 'Pos', 'c1': 'Patrón'},
                                  'celdas': {'c0': str(puesto), 'c1': 'Nombre de la fuente'}})


class PantallaRevision(unittest.TestCase):
    def setUp(self):
        self.personas = [persona(10, 1, 'Ana Pérez'), persona(11, 2, 'Luis Lago'), persona(12, 3, 'Persona excluida')]
        self.filas = [fila(1, 1), fila(2, 2), fila(3, 41, False)]
        self.candidatos = [dict(dni='D1', nombre='Ana', apellidos='Pérez', club='Club A',
                                federacion='Galicia', indice_similitud=Decimal('.98'), motivos='Nombre y club similares')]
        lista = [dict(id_importacion=1, nombre_archivo='regata.pdf', url_origen=None, nombre_clase='Optimist')]
        self.patches = [patch.object(base, 'listar_borradores', return_value=lista),
                        patch.object(s, 'cargar_revision', side_effect=self.contenido),
                        patch.object(s, 'buscar_coincidencias', side_effect=lambda *a: self.candidatos),
                        patch.object(s, 'guardar_en_proveedor', side_effect=self.guardar),
                        patch.object(s, 'agregar_en_proveedor', return_value=20),
                        patch.object(datos, 'cargar_clubes', return_value=CLUBES),
                        patch.object(datos, 'cargar_federaciones', return_value=FEDS),
                        patch.object(revision_lotes, 'cargar_resumen', return_value={'version':'prueba', 'grupos_club':[], 'propuestas':[]})]
        self.patches.append(patch.object(deportistas,'datos_pendientes',return_value=[]))
        self.mocks = [p.start() for p in self.patches]
        self.addCleanup(lambda: [p.stop() for p in reversed(self.patches)])
        self.at = AppTest.from_string(SCRIPT, default_timeout=15)
        self.at.session_state['revision_mostrar_individual']=True
        self.at.session_state['revision_solo_pendientes_1']=False

    def contenido(self, *args):
        seleccionadas = {f['id_fila']: f for f in self.filas if f['cumple_criterio']}
        revisables = [{**p, 'fila': seleccionadas[p['id_fila']], 'version': s.version_participante(p)}
                      for p in self.personas if p['id_fila'] in seleccionadas]
        return copy.deepcopy(dict(importacion={'id_importacion': 1, 'nombre_clase': 'Optimist',
                                               'estado': 'en_revision', 'numero_tripulantes': 1,
                                               'nombre_competicion_propuesto': 'Regata',
                                               'fecha_inicio_propuesta': date(2026, 10, 3),
                                               'fecha_fin_propuesta': date(2026, 10, 4),
                                               'localidad_propuesta': 'Vigo', 'tipo_clasificacion': 'definitiva'},
                                  filas=self.filas, participantes=self.personas,
                                  participantes_revision=revisables, seleccionadas=list(seleccionadas.values())))

    def guardar(self, proveedor, participante, accion, campos, version, dni, distinto, **extras):
        if accion == 'crear' and not campos.get('dni'):
            campos={**campos,'dni':'TEMP-ABCDEF123456'}
        s._validar_campos(campos, accion == 'crear')
        if extras:
            resultados._metadatos(extras['datos_resultado'])
        p = next(p for p in self.personas if p['id_participante_importado'] == participante)
        if accion == 'crear':
            p.update(dni_deportista_confirmado=campos['dni'].upper(), estado='nuevo_confirmado')
        elif accion == 'vincular':
            p.update(dni_deportista_confirmado=dni, estado='vinculado')
        else:
            p['estado'] = 'pendiente_datos'
        if extras:
            f = next(f for f in self.filas if f['id_fila'] == p['id_fila'])
            f['estado'] = 'importada'
            return dict(dni=p['dni_deportista_confirmado'], resultado_incorporado=True, pendiente_equipo=False)
        return p['dni_deportista_confirmado']

    def decision(self, nombre):
        next(r for r in self.at.radio if r.label == 'Decisión').set_value(nombre).run()

    def entrada(self, etiqueta, valor):
        next(t for t in self.at.text_input if t.label == etiqueta).set_value(valor)

    def boton(self, etiqueta):
        return next(b for b in self.at.button if b.label == etiqueta)

    def test_muestra_solo_seleccionados_y_fuente_original(self):
        at = self.at.run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual([m.value for m in at.metric], ['2', '0', '2'])
        selector = next(s for s in at.selectbox if s.label == 'Participante que deseas revisar')
        self.assertEqual(len(selector.options), 2)
        self.assertFalse(any('Persona excluida' in x for x in selector.options))
        self.assertTrue(any('Nombre de la fuente' in str(d.value) for d in at.dataframe))
        self.mocks[3].assert_not_called()

    def test_revision_individual_se_abre_solo_si_se_solicita(self):
        self.at.session_state['revision_mostrar_individual']=False
        self.at.run()
        self.assertEqual(len(self.at.exception),0)
        self.mocks[2].assert_not_called()
        self.assertFalse(any(r.label=='Decisión' for r in self.at.radio))
        next(c for c in self.at.checkbox if c.label.startswith('Revisar una identidad individual')).check().run()
        self.mocks[2].assert_called_once()

    def test_vinculo_exige_eleccion_y_confirmacion(self):
        self.at.run()
        self.assertTrue(self.boton('Vincular ficha seleccionada').disabled)
        next(s for s in self.at.selectbox if s.label.startswith('Ficha existente')).set_value('D1')
        next(c for c in self.at.checkbox if c.label.startswith('Confirmo que la ficha')).check().run()
        self.boton('Vincular ficha seleccionada').click().run()
        self.assertEqual(len(self.at.exception), 0)
        self.assertTrue(any('Ficha existente vinculada' in x.value for x in self.at.success))
        self.assertEqual(self.mocks[3].call_args.args[0], 'supabase')
        self.assertEqual(self.mocks[3].call_args.args[5], 'D1')
        self.assertEqual(self.mocks[3].call_args.kwargs, {})
        self.at.run()
        self.mocks[3].assert_called_once()

    def test_creacion_valida_obligatorios_y_no_infiere_nacimiento(self):
        self.at.run();self.decision('Crear deportista')
        self.assertTrue(self.boton('Crear deportista y guardar resultado').disabled)
        next(c for c in self.at.checkbox if c.label.startswith('He revisado las coincidencias')).check().run()
        self.entrada('Nombre', '')
        self.boton('Crear deportista y guardar resultado').click().run()
        self.assertTrue(any('obligatorio' in x.value for x in self.at.error))
        self.entrada('DNI / documento', 'D3')
        self.entrada('Nombre', 'Ana')
        self.entrada('Apellidos', 'Pérez García')
        self.boton('Crear deportista y guardar resultado').click().run()
        self.assertEqual(len(self.at.exception), 0)
        self.assertTrue(any('Deportista creado con su resultado' in x.value for x in self.at.success))
        campos = self.mocks[3].call_args.args[3]
        self.assertIsNone(campos['fecha_nacimiento'])
        self.assertIsNone(campos['sexo'])
        self.assertEqual(campos['dni'], 'D3')
        self.assertEqual(self.mocks[3].call_args.kwargs['datos_resultado']['nombre'], 'Regata')
        self.assertIn('version_importacion', self.mocks[3].call_args.kwargs)
        self.assertEqual(self.mocks[3].call_count, 2)  # Primer intento sin documento, segundo válido.

    def test_dejar_pendiente_sin_documento(self):
        self.at.run();self.decision('Dejar pendiente')
        self.entrada('Nombre', 'Ana')
        self.boton('Guardar pendiente').click().run()
        self.assertEqual(len(self.at.exception), 0)
        self.assertTrue(any('continúa pendiente' in x.value for x in self.at.success))
        self.assertEqual(self.mocks[3].call_args.args[2], 'pendiente')

    def test_nombre_precargado_editable_y_cambia_con_participante(self):
        self.at.run();self.decision('Crear deportista')
        self.assertEqual(next(t.value for t in self.at.text_input if t.label == 'Nombre'), 'Ana')
        self.assertEqual(next(t.value for t in self.at.text_input if t.label == 'Apellidos'), 'Pérez')
        self.entrada('Nombre', 'Ana María')
        self.entrada('DNI / documento', 'D3')
        next(c for c in self.at.checkbox if c.label.startswith('He revisado las coincidencias')).check().run()
        self.boton('Crear deportista y guardar resultado').click().run()
        self.assertEqual(self.mocks[3].call_args.args[3]['nombre'], 'Ana María')
        next(s for s in self.at.selectbox if s.label == 'Participante que deseas revisar').set_value(11).run()
        self.decision('Crear deportista')
        self.assertEqual(next(t.value for t in self.at.text_input if t.label == 'Nombre'), 'Luis')

    def test_respeta_propuestas_y_formato_apellidos_coma_nombre(self):
        from app.revision_participantes import _nombre_inicial
        p = persona(1, 1, 'Pérez García, Ana María')
        self.assertEqual(_nombre_inicial(p), ('Ana María', 'Pérez García'))
        p.update(nombre_propuesto='Ana María', apellidos_propuestos='Pérez corregido')
        self.assertEqual(_nombre_inicial(p), ('Ana María', 'Pérez corregido'))
        p.update(nombre_propuesto='', apellidos_propuestos='')
        self.assertEqual(_nombre_inicial(p), ('', ''))
        self.assertEqual(_nombre_inicial(persona(1, 1, 'Ana')), ('Ana', ''))

    def test_individual_asigna_patron_sin_selector(self):
        self.at.run();self.decision('Dejar pendiente')
        self.assertFalse(any(s.label == 'Rol en la embarcación' for s in self.at.selectbox))
        self.boton('Guardar pendiente').click().run()
        self.assertEqual(self.mocks[3].call_args.args[3]['rol_propuesto'], 'Patron')

    def test_doble_mantiene_selector_de_rol(self):
        contenido = self.contenido
        def doble(*args):
            resultado = contenido(*args)
            resultado['importacion'].update(nombre_clase='420', numero_tripulantes=2)
            return resultado
        self.mocks[1].side_effect = doble
        self.at.run();self.decision('Dejar pendiente')
        next(s for s in self.at.selectbox if s.label == 'Rol en la embarcación').set_value('Tripulante').run()
        self.boton('Guardar pendiente').click().run()
        self.assertEqual(self.mocks[3].call_args.args[3]['rol_propuesto'], 'Tripulante')

    def test_federacion_filtra_clubes_y_conserva_documento(self):
        self.at.run();self.decision('Crear deportista')
        self.entrada('DNI / documento', 'D3')
        next(s for s in self.at.selectbox if s.label.startswith('Federación para')).set_value(2).run()
        clubes = next(s for s in self.at.selectbox if s.label == 'Club identificado en la clasificación')
        self.assertIn('Club B', clubes.options)
        self.assertNotIn('Club A', clubes.options)
        self.assertEqual(next(t for t in self.at.text_input if t.label == 'DNI / documento').value, 'D3')

    def test_conflicto_conserva_datos_para_revisar(self):
        self.at.run();self.decision('Crear deportista')
        self.entrada('DNI / documento', 'D3');self.entrada('Nombre', 'Ana');self.entrada('Apellidos', 'Pérez')
        next(c for c in self.at.checkbox if c.label.startswith('He revisado las coincidencias')).check().run()
        self.mocks[3].side_effect = s.ConflictoError('La revisión cambió. Actualiza los datos.')
        self.boton('Crear deportista y guardar resultado').click().run()
        self.assertEqual(len(self.at.exception), 0)
        self.assertIn('revisión cambió', self.at.error[0].value)
        self.assertEqual(next(t for t in self.at.text_input if t.label == 'DNI / documento').value, 'D3')

    def test_error_conexion_no_expone_detalles(self):
        self.at.run();self.decision('Dejar pendiente')
        self.mocks[3].side_effect = OSError('CONTRASEÑA_PRIVADA')
        self.boton('Guardar pendiente').click().run()
        self.assertEqual(len(self.at.exception), 0)
        self.assertIn('No se pudo confirmar', self.at.error[0].value)
        self.assertNotIn('CONTRASEÑA_PRIVADA', str(self.at.error))

    def test_busqueda_manual_se_envia_al_servicio(self):
        self.at.run()
        next(t for t in self.at.text_input if t.label.startswith('Buscar otra ficha')).set_value('D2')
        self.boton('Buscar fichas').click().run()
        self.assertEqual(self.mocks[2].call_args.args[2], 'D2')
        self.mocks[3].assert_not_called()

    def test_sin_borradores(self):
        self.mocks[0].return_value = []
        self.at.run()
        self.assertEqual(len(self.at.exception), 0)
        self.assertTrue(any('No hay borradores' in x.value for x in self.at.info))
        self.mocks[3].assert_not_called()

    def test_completar_miembro_faltante(self):
        self.personas.pop(0)
        self.at.run()
        next(t for t in self.at.text_input if t.label.startswith('Nombre completo tal')).set_value('Ana Pérez')
        self.boton('Añadir participante pendiente').click().run()
        self.assertEqual(self.mocks[4].call_args.args, ('supabase', 1, 'Ana Pérez', 1))
        self.mocks[3].assert_not_called()

    def test_filtro_pendientes_oculta_identidades_confirmadas(self):
        self.personas[0].update(dni_deportista_confirmado='D1', estado='vinculado')
        self.at.run()
        next(c for c in self.at.checkbox if c.label == 'Mostrar solo identidades pendientes').check().run()
        opciones = next(s for s in self.at.selectbox if s.label == 'Participante que deseas revisar').options
        self.assertEqual(len(opciones), 1)
        self.assertIn('Luis Lago', opciones[0])

    def test_incorporacion_exige_revision_explicita_y_envia_solo_confirmados(self):
        from datetime import date
        self.personas[0].update(dni_deportista_confirmado='D1', estado='vinculado')
        with patch.object(resultados, 'incorporar_en_proveedor', return_value=1) as guardar:
            self.at.run()
            boton = self.boton('Incorporar resultados seleccionados')
            self.assertTrue(boton.disabled)
            guardar.assert_not_called()
            selector = next(s for s in self.at.multiselect if s.label == 'Resultados que se incorporarán')
            self.assertEqual(selector.value, [1])
            self.entrada('Nombre de la regata', 'Vigo')
            next(d for d in self.at.date_input if d.label == 'Inicio de la regata').set_value(date(2026, 10, 3))
            next(d for d in self.at.date_input if d.label == 'Fin de la regata').set_value(date(2026, 10, 4))
            next(s for s in self.at.selectbox if s.label == 'Estado de la clasificación de origen').set_value('definitiva')
            next(c for c in self.at.checkbox if c.label.startswith('He revisado la regata')).check().run()
            self.boton('Incorporar resultados seleccionados').click().run()
            self.assertEqual(len(self.at.exception), 0)
            self.assertEqual(guardar.call_args.args[:3], ('supabase', 1, [1]))
            self.assertEqual(guardar.call_args.args[3]['nombre'], 'Vigo')
            self.assertTrue(any('resultados incorporados' in m.value for m in self.at.success))
            self.mocks[3].assert_not_called()

    def test_fallo_incorporacion_no_anuncia_exito_y_conserva_formulario(self):
        self.personas[0].update(dni_deportista_confirmado='D1', estado='vinculado')
        with patch.object(resultados, 'incorporar_en_proveedor', side_effect=s.ConflictoError('Puesto repetido')):
            self.at.run()
            self.entrada('Nombre de la regata', 'Vigo')
            next(c for c in self.at.checkbox if c.label.startswith('He revisado la regata')).check().run()
            self.boton('Incorporar resultados seleccionados').click().run()
            self.assertTrue(any('Puesto repetido' in m.value for m in self.at.error))
            self.assertEqual(next(t.value for t in self.at.text_input if t.label == 'Nombre de la regata'), 'Vigo')

    def test_importacion_parcial_permite_revisar_identidades_restantes(self):
        contenido = self.contenido
        def parcial(*args):
            b = contenido(*args)
            b['importacion']['estado'] = 'parcialmente_importada'
            return b
        self.mocks[1].side_effect = parcial
        self.at.run();self.decision('Dejar pendiente')
        self.assertFalse(self.boton('Guardar pendiente').disabled)

    def test_alta_permite_corregir_regata_en_el_mismo_boton(self):
        self.at.run();self.decision('Crear deportista')
        self.entrada('DNI / documento', 'D3')
        self.entrada('Nombre de la regata', 'Vigo corregido')
        next(c for c in self.at.checkbox if c.label.startswith('He revisado las coincidencias')).check().run()
        self.boton('Crear deportista y guardar resultado').click().run()
        self.assertEqual(len(self.at.exception), 0)
        self.assertEqual(self.mocks[3].call_args.kwargs['datos_resultado']['nombre'], 'Vigo corregido')
        self.assertTrue(any('con su resultado deportivo' in m.value for m in self.at.success))

    def test_doble_incompleto_explica_que_el_resultado_espera_al_equipo(self):
        contenido = self.contenido
        def doble(*args):
            b = contenido(*args)
            b['importacion'].update(nombre_clase='420', numero_tripulantes=2)
            return b
        self.mocks[1].side_effect = doble
        self.at.run();self.decision('Crear deportista')
        self.assertTrue(self.boton('Crear deportista y dejar equipo pendiente').disabled)
        self.assertTrue(any('ambos miembros' in c.value for c in self.at.caption))


if __name__ == '__main__':
    unittest.main(verbosity=2)
