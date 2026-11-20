"""Una confirmación por embarcación, con vínculos y altas en la misma transacción."""
from datetime import date
import unittest
from sqlalchemy import event,text
from services import revision_lotes as s, importaciones as base
from services.deportistas import ValidacionError,ConflictoError
import test_importaciones as fixtures


class RevisionRapida(unittest.TestCase):
    def setUp(self):
        self.db=fixtures.PersistenciaImportaciones();self.db.setUp();self.addCleanup(self.db.doCleanups)
        self.engine=self.db.engine
        event.listen(self.engine,'before_cursor_execute',lambda c,cu,q,p,ctx,m:(q.replace(' FOR UPDATE',''),p),retval=True)
        self.meta=dict(nombre='Regata guiada',fecha_inicio=date(2026,10,3),fecha_fin=date(2026,10,4),localidad='Vigo',tipo_clasificacion='definitiva')

    def crear(self,tripulantes=2,nombres=('Ana Pérez','Úrsula Abad Montoro'),segunda=False):
        miembros=[dict(nombre_original=n,nombre_propuesto=n.split(' ',1)[0],apellidos_propuestos=n.split(' ',1)[1],
            club_original='Club A',rol_propuesto=('Patron','Tripulante')[i]) for i,n in enumerate(nombres)]
        filas=[dict(numero_fila=1,datos_originales={},numero_vela_original='ESP 1',posicion_general=1,puntos='12.25',participantes=miembros)]
        if segunda:
            filas.append(dict(numero_fila=2,datos_originales={},numero_vela_original='ESP 2',posicion_general=2,puntos='20',
                participantes=[dict(nombre_original='Zacarías Velázquez Taboada',club_original='Club A',rol_propuesto='Patron')]))
        self.ident=self.db.crear(campos={**self.db.campos,'id_clase':2 if tripulantes==2 else 1,
            'nombre_competicion_propuesto':self.meta['nombre'],'fecha_inicio_propuesta':self.meta['fecha_inicio'],
            'fecha_fin_propuesta':self.meta['fecha_fin'],'localidad_propuesta':'Vigo','tipo_clasificacion':'definitiva'},filas=filas)
        self.actualizar()

    def actualizar(self):
        self.contenido=base.obtener_borrador(self.engine,self.ident)
        self.resumen=s.cargar_resumen(self.engine,self.ident)
        self.plan=s.plan_revision_rapida(self.contenido,self.resumen,datos_regata=self.meta)

    def guardar(self,filas=None,**extras):
        return s.guardar_revision_rapida(self.engine,self.ident,
            [r['fila'] for r in self.plan['preparadas']] if filas is None else filas,
            self.resumen['version'],extras.pop('version_plan',self.plan['version']),self.meta,confirmar=True,**extras)

    def test_equipo_mixto_se_vincula_crea_y_guarda_junto(self):
        self.crear()
        self.assertEqual((len(self.plan['preparadas']),len(self.plan['pendientes'])),(1,0))
        fila=self.plan['preparadas'][0]
        self.assertEqual((len(fila['vinculos']),len(fila['altas'])),(1,1))
        self.assertEqual(self.db.contar('participa_en'),0)
        self.assertEqual(self.guardar(),dict(vinculados=1,creados=1,resultados_incorporados=1,pendientes=0))
        actual=base.obtener_borrador(self.engine,self.ident)
        self.assertEqual(actual['importacion']['estado'],'completada')
        self.assertEqual({p['rol_propuesto'] for p in actual['participantes']},{'Patron','Tripulante'})
        self.assertEqual(actual['participantes'][0]['dni_deportista_confirmado'],'D1')
        self.assertTrue(actual['participantes'][1]['dni_deportista_confirmado'].startswith('TEMP-'))
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text('SELECT COUNT(*) FROM forma_parte')).scalar_one(),2)
            self.assertIsNone(c.execute(text("SELECT fecha_nacimiento FROM deportista WHERE dni LIKE 'TEMP-%'")).scalar_one())

    def test_fallo_del_resultado_revierte_tambien_vinculos_y_altas(self):
        self.crear()
        with self.engine.begin() as c:c.exec_driver_sql("CREATE TRIGGER fallo_rapido BEFORE INSERT ON participa_en BEGIN SELECT RAISE(ABORT,'fallo'); END")
        with self.assertRaises(ConflictoError):self.guardar()
        self.assertEqual(self.db.contar('deportista'),2)
        actual=base.obtener_borrador(self.engine,self.ident)
        self.assertTrue(all(p['dni_deportista_confirmado'] is None for p in actual['participantes']))
        self.assertEqual(self.db.contar('participa_en'),0)

    def test_solo_guarda_las_embarcaciones_seleccionadas(self):
        self.crear(tripulantes=1,nombres=('Ana Pérez',),segunda=True)
        self.assertEqual(len(self.plan['preparadas']),2)
        self.guardar([self.plan['preparadas'][1]['fila']])
        actual=base.obtener_borrador(self.engine,self.ident)
        self.assertIsNone(actual['participantes'][0]['dni_deportista_confirmado'])
        self.assertEqual(self.db.contar('participa_en'),1)

    def test_candidato_modificado_no_se_sustituye_sin_revisar(self):
        self.crear()
        with self.engine.begin() as c:c.exec_driver_sql("UPDATE deportista SET apellidos='Pérez García' WHERE dni='D1'")
        with self.assertRaisesRegex(ConflictoError,'propuestas'):self.guardar()
        self.assertEqual(self.db.contar('participa_en'),0)

    def test_equipo_incompleto_no_entra_en_preparados(self):
        self.crear(nombres=('Ana Pérez',))
        self.assertEqual(self.plan['preparadas'],[])
        self.assertEqual(len(self.plan['pendientes']),1)
        with self.assertRaises((ValidacionError,ConflictoError)):self.guardar([self.contenido['filas'][0]['id_fila']])

    def test_club_y_roles_pendientes_no_crean_fichas(self):
        self.crear()
        with self.engine.begin() as c:c.exec_driver_sql('UPDATE participante_importado SET id_club_identificado=NULL,rol_propuesto=NULL')
        self.actualizar()
        self.assertEqual(self.plan['preparadas'],[])
        self.assertEqual(self.db.contar('deportista'),2)

    def test_dos_fichas_existentes_no_crean_deportistas(self):
        self.crear(nombres=('Ana Pérez','Luis Lago'))
        salida=self.guardar()
        self.assertEqual((salida['vinculados'],salida['creados'],salida['resultados_incorporados']),(2,0,1))
        self.assertEqual(self.db.contar('deportista'),2)

    def test_metadatos_invalidos_y_version_incorrecta_no_escriben(self):
        self.crear()
        with self.assertRaises(ConflictoError):self.guardar(version_plan='antigua')
        self.meta['fecha_inicio']=None
        with self.assertRaises(ValidacionError):self.guardar()
        self.assertEqual(self.db.contar('participa_en'),0)
