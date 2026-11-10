"""Pruebas de integración de solo lectura para los datos DEMO de Sailing Talent.

Guardar en la raíz del proyecto, junto a requirements.txt. Ejecutar:
    python probar_consultas.py --db-provider supabase
    python probar_consultas.py --db-provider cloudsql
    python probar_consultas.py --db-provider ambos

Requiere sample_data.sql y sample_deportistas.sql en cada proveedor.
No modifica datos ni crea fixtures. No necesita pytest ni otras dependencias.
"""
import argparse
from datetime import date
from decimal import Decimal
import json
import sys
import unittest

from sqlalchemy import event, text

from database import queries as q


REFERENCIA = date(2026, 11, 9)
DOCUMENTOS = [f"STDEMO{i:04}" for i in range(1, 37)]
ENGINE = None


def leer(sql, parametros=None):
    with ENGINE.connect() as conexion:
        return [dict(f) for f in conexion.execute(text(sql), parametros or {}).mappings()]


def solo_demo(filas):
    return [f for f in filas if f["dni"] in DOCUMENTOS]


def clase_activa(dni, fecha=REFERENCIA):
    return q.obtener_ficha_deportista(ENGINE, dni, fecha_referencia=fecha)["clases_activas"]


class PruebasConsultas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        existentes = {f["dni"] for f in leer(
            "SELECT dni FROM public.deportista WHERE dni LIKE 'STDEMO%'"
        )}
        faltantes = set(DOCUMENTOS) - existentes
        if faltantes:
            raise AssertionError(
                f"Faltan {len(faltantes)} deportistas DEMO. "
                "Ejecuta primero sample_deportistas.sql en este proveedor."
            )

    def test_01_federaciones(self):
        nombres = {r["nombre"] for r in q.listar_federaciones(ENGINE)}
        self.assertTrue({
            "Real Federación Gallega de Vela", "Federación Catalana de Vela",
            "Federación Canaria de Vela", "Federación Balear de Vela",
            "Federación de la Comunidad Valenciana de Vela",
            "Federación Andaluza de Vela", "Federación Cántabra de Vela",
        }.issubset(nombres))

    def test_02_clubes_y_federacion(self):
        clubes = q.listar_clubes(ENGINE)
        self.assertGreaterEqual(len(clubes), 15)
        portosin = next(c for c in clubes if c["nombre"] == "Real Club Náutico de Portosín")
        self.assertEqual(portosin["federacion"], "Real Federación Gallega de Vela")
        gallegos = q.listar_clubes(ENGINE, portosin["id_federacion"])
        self.assertGreaterEqual(len(gallegos), 4)
        self.assertTrue(all(c["id_federacion"] == portosin["id_federacion"] for c in gallegos))

    def test_03_clases_y_filtro_olimpico(self):
        clases = {c["nombre"]: c for c in q.listar_clases(ENGINE)}
        dobles = {"420", "470", "29er", "49er"}
        esperadas = dobles | {"Optimist", "ILCA 4", "ILCA 6", "ILCA 7"}
        for nombre in esperadas:
            self.assertEqual(clases[nombre]["numero_tripulantes"], 2 if nombre in dobles else 1)
        olimpicas = {c["nombre"] for c in q.listar_clases(ENGINE, True)}
        no_olimpicas = {c["nombre"] for c in q.listar_clases(ENGINE, False)}
        self.assertEqual(olimpicas & esperadas, {"470", "ILCA 6", "ILCA 7", "49er"})
        self.assertEqual(no_olimpicas & esperadas, {"Optimist", "420", "ILCA 4", "29er"})

    def test_04_busqueda_por_nombre_y_club(self):
        self.assertIn("STDEMO0001", {r["dni"] for r in q.buscar_deportistas(ENGINE, "ALBA LAGO")})
        self.assertIn("STDEMO0001", {r["dni"] for r in q.buscar_deportistas(ENGINE, "Portosín")})
        club = q.obtener_ficha_deportista(ENGINE, "STDEMO0001", fecha_referencia=REFERENCIA)["id_club"]
        self.assertTrue(all(r["id_club"] == club for r in q.buscar_deportistas(ENGINE, id_club=club)))

    def test_05_paginacion(self):
        primera = q.buscar_deportistas(ENGINE, limite=5)
        segunda = q.buscar_deportistas(ENGINE, limite=5, desplazamiento=5)
        diez = q.buscar_deportistas(ENGINE, limite=10)
        self.assertEqual(primera + segunda, diez)
        self.assertFalse({r["dni"] for r in primera} & {r["dni"] for r in segunda})

    def test_06_ficha_edad_y_medicion(self):
        p = q.obtener_ficha_deportista(ENGINE, "STDEMO0001", fecha_referencia=REFERENCIA)
        self.assertEqual(p["nombre"], "Alba")
        self.assertEqual(p["edad"], 14)
        self.assertEqual(p["club"], "Real Club Náutico de Portosín")
        self.assertEqual(p["altura"], Decimal("148"))
        self.assertEqual(p["fecha_medicion"], date(2026, 10, 15))
        self.assertEqual(p["participaciones"], 2)
        self.assertEqual(p["mejor_puesto"], 1)

    def test_07_ficha_inexistente(self):
        self.assertIsNone(q.obtener_ficha_deportista(
            ENGINE, "STNOEXISTENTE", fecha_referencia=REFERENCIA
        ))

    def test_08_historial_ordenado(self):
        filas = q.consultar_historial_antropometrico(ENGINE, "STDEMO0001")
        self.assertEqual([r["fecha"] for r in filas], [date(2025, 10, 15), date(2026, 10, 15)])
        self.assertEqual([r["altura"] for r in filas], [Decimal("146"), Decimal("148")])

    def test_09_sin_mediciones(self):
        self.assertEqual(q.consultar_historial_antropometrico(ENGINE, "STDEMO0004"), [])
        p = q.obtener_ficha_deportista(ENGINE, "STDEMO0004", fecha_referencia=REFERENCIA)
        for campo in ("altura", "peso", "envergadura", "porcentaje_graso", "fecha_medicion"):
            self.assertIsNone(p[campo], campo)
        self.assertEqual(p["participaciones"], 2)

    def test_10_mediciones_hasta_fecha_referencia(self):
        p = q.obtener_ficha_deportista(ENGINE, "STDEMO0001", fecha_referencia=date(2026, 1, 1))
        self.assertEqual(p["altura"], Decimal("146"))
        self.assertEqual(p["fecha_medicion"], date(2025, 10, 15))
        self.assertEqual(p["participaciones"], 0)
        self.assertIsNone(p["mejor_puesto"])

    def test_11_resultados_y_resumen_sin_duplicados(self):
        for dni in DOCUMENTOS:
            with self.subTest(dni=dni):
                filas = q.consultar_resultados_deportista(ENGINE, dni, fecha_referencia=REFERENCIA)
                pares = {(r["id_unidad"], r["id_competicion"]) for r in filas}
                self.assertEqual(len(pares), len(filas))
                p = q.obtener_ficha_deportista(ENGINE, dni, fecha_referencia=REFERENCIA)
                self.assertEqual(p["participaciones"], len(filas))
                self.assertEqual(p["mejor_puesto"], min(r["posicion_general"] for r in filas))
                self.assertEqual([r["fecha_inicio"] for r in filas],
                                 sorted((r["fecha_inicio"] for r in filas), reverse=True))

    def test_12_resultados_filtrados_por_clase(self):
        ilca = next(c for c in q.listar_clases(ENGINE) if c["nombre"] == "ILCA 4")
        filas = q.consultar_resultados_deportista(ENGINE, "STDEMO0007", id_clase=ilca["id_clase"], fecha_referencia=REFERENCIA)
        self.assertEqual(len(filas), 2)
        self.assertTrue(all(r["clase"] == "ILCA 4" for r in filas))
        self.assertEqual(len(q.consultar_resultados_deportista(ENGINE, "STDEMO0007", fecha_referencia=REFERENCIA)), 3)

    def test_13_trayectoria_y_transicion(self):
        filas = q.consultar_trayectoria_deportista(ENGINE, "STDEMO0007", fecha_referencia=REFERENCIA)
        self.assertEqual({r["clase"] for r in filas}, {"Optimist", "ILCA 4"})
        self.assertTrue(all(r["activa"] == (r["clase"] == "ILCA 4") for r in filas))
        self.assertEqual(clase_activa("STDEMO0007", date(2024, 12, 31)), "Optimist")
        self.assertEqual(clase_activa("STDEMO0007", date(2025, 1, 1)), "ILCA 4")

    def test_14_equipos_dobles(self):
        filas = q.consultar_trayectoria_deportista(ENGINE, "STDEMO0025", fecha_referencia=REFERENCIA)
        actuales = [r for r in filas if r["activa"]]
        self.assertEqual(len(actuales), 2)
        self.assertEqual({r["dni_miembro"] for r in actuales}, {"STDEMO0025", "STDEMO0026"})
        self.assertEqual({r["rol"] for r in actuales}, {"Patron", "Tripulante"})
        self.assertEqual({r["clase"] for r in actuales}, {"470"})

    def test_15_candidatos_filtrados(self):
        filas = solo_demo(q.buscar_candidatos(
            ENGINE, clase_actual="Optimist", sexo="Femenino", edad_min=12,
            edad_max=15, altura_min=148, fecha_referencia=REFERENCIA, limite=10000
        ))
        self.assertEqual({r["dni"] for r in filas}, {"STDEMO0001", "STDEMO0003"})

    def test_16_candidatos_sin_mediciones_y_sin_duplicados(self):
        filas = solo_demo(q.buscar_candidatos(ENGINE, fecha_referencia=REFERENCIA, limite=10000))
        self.assertEqual(len(filas), 36)
        self.assertEqual(len({r["dni"] for r in filas}), 36)
        self.assertEqual(sum(r["altura"] is None for r in filas), 9)
        filtradas = q.buscar_candidatos(ENGINE, altura_min=1, fecha_referencia=REFERENCIA, limite=10000)
        self.assertNotIn("STDEMO0004", {r["dni"] for r in filtradas})

    def test_17_comparacion_orden_y_repetidos(self):
        filas = q.comparar_deportistas(ENGINE, ["STDEMO0007", "STDEMO0001", "STDEMO0007", "STDEMO0004"], fecha_referencia=REFERENCIA)
        self.assertEqual([r["dni"] for r in filas], ["STDEMO0007", "STDEMO0001", "STDEMO0004"])
        self.assertIsNone(filas[2]["altura"])
        self.assertEqual(q.comparar_deportistas(ENGINE, []), [])
        self.assertEqual(q.comparar_deportistas(ENGINE, ["STNOEXISTENTE"]), [])

    def test_18_argumentos_invalidos(self):
        for filtros in (dict(edad_min=20, edad_max=10), dict(edad_min=-1),
                        dict(altura_min=float("nan")), dict(sexo="otro"),
                        dict(limite=0), dict(desplazamiento=-1)):
            with self.subTest(filtros=filtros), self.assertRaises(ValueError):
                q.buscar_candidatos(ENGINE, **filtros)
        with self.assertRaises(ValueError):
            q.comparar_deportistas(ENGINE, DOCUMENTOS[:4])
        with self.assertRaises(ValueError):
            q.listar_clases(ENGINE, "False")

    def test_19_texto_no_se_interpreta_como_sql(self):
        self.assertEqual(q.buscar_deportistas(ENGINE, "' OR 1=1 --"), [])
        self.assertEqual(q.comparar_deportistas(ENGINE, ["' OR 1=1 --"]), [])
        # No se ejecutan sentencias destructivas ni siquiera como prueba.
        for valor in ("%", "_"):
            self.assertEqual(solo_demo(q.buscar_deportistas(ENGINE, valor, limite=10000)), [])

    def test_20_puestos_unicos_y_puntuaciones(self):
        filas = leer("""
            SELECT c.id_competicion, p.id_unidad, p.posicion_general, p.puntos
            FROM public.competicion c
            JOIN public.participa_en p ON p.id_competicion=c.id_competicion
            WHERE c.nombre LIKE 'DEMO ST %'
            ORDER BY c.id_competicion, p.posicion_general
        """)
        self.assertEqual(len(filas), 55)
        por_regata = {}
        for r in filas:
            por_regata.setdefault(r["id_competicion"], []).append(r)
        self.assertEqual(len(por_regata), 18)
        for regata in por_regata.values():
            self.assertEqual([r["posicion_general"] for r in regata], list(range(1, len(regata)+1)))
            self.assertEqual(len({r["id_unidad"] for r in regata}), len(regata))
            self.assertTrue(all(a["puntos"] < b["puntos"] for a, b in zip(regata, regata[1:])))

    def test_21_tripulaciones_clases_y_fechas(self):
        errores = leer("""
            SELECT u.id_unidad
            FROM public.unidad_competitiva u
            JOIN public.clase cl ON cl.id_clase=u.id_clase
            JOIN public.forma_parte fp ON fp.id_unidad=u.id_unidad
            JOIN public.deportista d ON d.dni=fp.dni_deportista
            WHERE EXISTS (SELECT 1 FROM public.forma_parte demo
                          WHERE demo.id_unidad=u.id_unidad AND demo.dni_deportista LIKE 'STDEMO%')
            GROUP BY u.id_unidad, cl.numero_tripulantes
            HAVING COUNT(*) <> cl.numero_tripulantes
                OR COUNT(*) FILTER (WHERE fp.rol='Patron') <> 1
                OR COUNT(*) FILTER (WHERE fp.rol='Tripulante') <> cl.numero_tripulantes-1
                OR COUNT(DISTINCT d.id_club) <> 1
        """)
        self.assertEqual(errores, [])
        errores = leer("""
            SELECT p.id_unidad FROM public.participa_en p
            JOIN public.unidad_competitiva u ON u.id_unidad=p.id_unidad
            JOIN public.competicion c ON c.id_competicion=p.id_competicion
            WHERE c.nombre LIKE 'DEMO ST %'
              AND (u.id_clase<>c.id_clase OR u.fecha_inicio>c.fecha_inicio
                   OR (u.fecha_fin IS NOT NULL AND u.fecha_fin<c.fecha_fin))
        """)
        self.assertEqual(errores, [])
        solapamientos = leer("""
            SELECT a.dni_deportista FROM public.forma_parte a
            JOIN public.forma_parte b ON b.dni_deportista=a.dni_deportista AND b.id_unidad>a.id_unidad
            JOIN public.unidad_competitiva ua ON ua.id_unidad=a.id_unidad
            JOIN public.unidad_competitiva ub ON ub.id_unidad=b.id_unidad
            WHERE a.dni_deportista LIKE 'STDEMO%'
              AND (ub.fecha_fin IS NULL OR ua.fecha_inicio<=ub.fecha_fin)
              AND (ua.fecha_fin IS NULL OR ub.fecha_inicio<=ua.fecha_fin)
        """)
        self.assertEqual(solapamientos, [])

    def test_22_informes_opcionales(self):
        filas = leer("""
            SELECT d.dni, COUNT(i.id_informe) AS informes
            FROM public.deportista d
            LEFT JOIN public.informe i ON i.dni_deportista=d.dni
            WHERE d.dni LIKE 'STDEMO%'
            GROUP BY d.dni
        """)
        demo = solo_demo(filas)
        self.assertEqual(sum(r["informes"] for r in demo), 12)
        self.assertEqual(sum(r["informes"] == 0 for r in demo), 24)
        # queries.py todavía no incluye una función para listar informes.


def serializar(valor):
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return str(valor.normalize())
    raise TypeError(f"Tipo no serializable: {type(valor).__name__}")


def normalizar(filas):
    """Compara datos de negocio, ignorando IDs de secuencias y orden de filas."""
    return sorted(json.dumps(
        {k: v for k, v in fila.items() if not k.startswith("id_")},
        sort_keys=True, ensure_ascii=False, default=serializar,
    ) for fila in filas)


def capturar_resultados(engine):
    """Ejecuta las diez consultas para comparar ambas bases sin sus IDs."""
    datos = {
        "federaciones": normalizar(q.listar_federaciones(engine)),
        "clubes": normalizar(q.listar_clubes(engine)),
        "clases": normalizar(q.listar_clases(engine)),
        "busqueda": normalizar(solo_demo(q.buscar_deportistas(engine, limite=10000))),
        "candidatos": normalizar(solo_demo(q.buscar_candidatos(engine, fecha_referencia=REFERENCIA, limite=10000))),
        "comparacion": normalizar(q.comparar_deportistas(engine, DOCUMENTOS[:3], fecha_referencia=REFERENCIA)),
    }
    for dni in DOCUMENTOS:
        ficha = q.obtener_ficha_deportista(engine, dni, fecha_referencia=REFERENCIA)
        datos[dni+":ficha"] = normalizar([ficha] if ficha else [])
        datos[dni+":historial"] = normalizar(q.consultar_historial_antropometrico(engine, dni))
        datos[dni+":resultados"] = normalizar(q.consultar_resultados_deportista(engine, dni, fecha_referencia=REFERENCIA))
        datos[dni+":trayectoria"] = normalizar(q.consultar_trayectoria_deportista(engine, dni, fecha_referencia=REFERENCIA))
    return datos


def ejecutar(provider, comparar=False):
    global ENGINE
    # Importación diferida: --help no requiere cargar credenciales.
    from database.database import crear_engine
    engine = crear_engine(provider)
    # PostgreSQL impide escrituras en TODAS las transacciones de estas pruebas.
    @event.listens_for(engine, "begin")
    def solo_lectura(conexion):
        conexion.exec_driver_sql("SET TRANSACTION READ ONLY")
    ENGINE = engine
    try:
        print(f"\nProveedor: {provider}. Fecha de referencia: {REFERENCIA}.", flush=True)
        with engine.connect() as conexion:
            conexion.execute(text("SELECT 1"))
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(PruebasConsultas)
        resultado = unittest.TextTestRunner(verbosity=2).run(suite)
        datos = capturar_resultados(engine) if comparar and resultado.wasSuccessful() else None
        return resultado.wasSuccessful(), datos
    finally:
        ENGINE = None
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-provider", required=True, choices=["supabase", "cloudsql", "ambos"])
    args = parser.parse_args()
    providers = ["supabase", "cloudsql"] if args.db_provider == "ambos" else [args.db_provider]
    estados, capturas = [], {}
    for provider in providers:
        try:
            ok, datos = ejecutar(provider, comparar=len(providers)==2)
        except Exception as error:
            # No imprimir URL de conexión, contraseña ni detalles del controlador.
            print(f"ERROR en {provider}: no se pudo completar la prueba ({type(error).__name__}). "
                  "Comprueba .env, conexión y, para Cloud SQL, el proxy.", file=sys.stderr)
            ok, datos = False, None
        estados.append(ok)
        capturas[provider] = datos
    if len(providers)==2 and all(estados):
        a, b = capturas["supabase"], capturas["cloudsql"]
        diferencias = [clave for clave in sorted(set(a)|set(b)) if a.get(clave)!=b.get(clave)]
        if diferencias:
            print("DIFERENCIAS entre proveedores en: " + ", ".join(diferencias))
            estados.append(False)
        else:
            print("Coinciden los datos consultados en ambos proveedores, ignorando los IDs autogenerados.")
    print("\nResultado final: " + ("CORRECTO" if all(estados) else "REVISAR FALLOS"))
    return 0 if all(estados) else 1


if __name__ == "__main__":
    sys.exit(main())
