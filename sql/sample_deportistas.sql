-- ============================================================
-- sailing-talent-app / sample_deportistas.sql
-- DATOS TOTALMENTE FICTICIOS. Referencia temporal: 09/11/2026.
-- Los documentos STDEMO/STTEC son identificadores de prueba, no DNI reales.
-- Las competiciones DEMO son encuentros abiertos ficticios, no regatas reales.
-- Requisitos: create_tables.sql y sample_data.sql ejecutados previamente.
-- Compatible con PostgreSQL en Cloud SQL y Supabase (rol con permisos INSERT).
-- Ejecutar el archivo COMPLETO una sola vez por base de datos.
-- Si ya existen estos identificadores o nombres de regatas, aborta sin duplicar.
-- No borra datos, no cambia el esquema y no depende de IDs autogenerados.
--
-- Contenido: 36 deportistas / 15 clubes / 4 federaciones con clubes de prueba.
-- 26 unidades actuales + 3 históricas; 40 pertenencias; 18 regatas; 55 resultados.
-- La posición general es única por competición y los puntos crecen con el puesto.
-- posicion_categoria = NULL: el esquema no define categorías deportivas.
-- Cada unidad doble tiene un Patron y un Tripulante del mismo club.
-- 470: equipos mixtos; ILCA 7 y 49er: masculinos; resto: encuentros abiertos.
-- Dos transiciones Optimist -> ILCA 4 y una 420 -> 470, sin solapamientos.
-- Algunos deportistas no tienen mediciones y/o informes deliberadamente.
-- Las tablas temporales solo sirven para enlazar los IDs devueltos por INSERT.
-- Todas las comprobaciones se ejecutan ANTES de COMMIT.
-- ============================================================

BEGIN;

CREATE TEMP TABLE st_clubes (
    nombre TEXT PRIMARY KEY, federacion TEXT NOT NULL
) ON COMMIT DROP;
INSERT INTO st_clubes (nombre, federacion) VALUES
    ('Real Club Náutico de Portosín', 'Real Federación Gallega de Vela'),
    ('Real Club Náutico de Vigo', 'Real Federación Gallega de Vela'),
    ('Real Club Náutico de A Coruña', 'Real Federación Gallega de Vela'),
    ('Real Club Náutico de Sanxenxo', 'Real Federación Gallega de Vela'),
    ('Real Club Náutico de Palma', 'Federación Balear de Vela'),
    ('Club Nàutic S''Arenal', 'Federación Balear de Vela'),
    ('Real Club Náutico Port de Pollença', 'Federación Balear de Vela'),
    ('Club Marítimo San Antonio de la Playa', 'Federación Balear de Vela'),
    ('Real Club Náutico de Barcelona', 'Federación Catalana de Vela'),
    ('Club Náutico El Masnou', 'Federación Catalana de Vela'),
    ('Club Nàutic El Balís', 'Federación Catalana de Vela'),
    ('Club Nàutic Garraf', 'Federación Catalana de Vela'),
    ('Real Club Náutico de Valencia', 'Federación de la Comunidad Valenciana de Vela'),
    ('Real Club de Regatas de Alicante', 'Federación de la Comunidad Valenciana de Vela'),
    ('Real Club Náutico de Torrevieja', 'Federación de la Comunidad Valenciana de Vela');

CREATE TEMP TABLE st_clases (
    nombre TEXT PRIMARY KEY, tripulantes INTEGER NOT NULL
) ON COMMIT DROP;
INSERT INTO st_clases (nombre, tripulantes) VALUES
    ('Optimist', 1),
    ('ILCA 4', 1),
    ('ILCA 6', 1),
    ('ILCA 7', 1),
    ('420', 2),
    ('470', 2),
    ('29er', 2),
    ('49er', 2);

CREATE TEMP TABLE st_deportistas (
    dni TEXT PRIMARY KEY, nombre TEXT NOT NULL, apellidos TEXT NOT NULL,
    nacimiento DATE NOT NULL, sexo TEXT NOT NULL, club TEXT NOT NULL
) ON COMMIT DROP;
INSERT INTO st_deportistas (dni, nombre, apellidos, nacimiento, sexo, club) VALUES
    ('STDEMO0001', 'Alba', 'Lago Varela', '2012-01-04', 'Femenino', 'Real Club Náutico de Portosín'),
    ('STDEMO0002', 'Brais', 'Souto Castro', '2013-02-07', 'Masculino', 'Real Club Náutico de Vigo'),
    ('STDEMO0003', 'Noa', 'Vidal Freire', '2012-03-10', 'Femenino', 'Real Club Náutico de A Coruña'),
    ('STDEMO0004', 'Iago', 'Rey Blanco', '2013-04-13', 'Masculino', 'Real Club Náutico de Sanxenxo'),
    ('STDEMO0005', 'Lara', 'Pazos Soutelo', '2012-05-16', 'Femenino', 'Real Club Náutico de Palma'),
    ('STDEMO0006', 'Hugo', 'Doval Ríos', '2013-06-19', 'Masculino', 'Club Nàutic S''Arenal'),
    ('STDEMO0007', 'Aina', 'Serra Pons', '2010-07-22', 'Femenino', 'Real Club Náutico Port de Pollença'),
    ('STDEMO0008', 'Pau', 'Vidal Ferrer', '2011-08-25', 'Masculino', 'Club Marítimo San Antonio de la Playa'),
    ('STDEMO0009', 'Laia', 'Roca Soler', '2010-09-03', 'Femenino', 'Real Club Náutico de Barcelona'),
    ('STDEMO0010', 'Nil', 'Puig Costa', '2011-10-06', 'Masculino', 'Club Náutico El Masnou'),
    ('STDEMO0011', 'Clara', 'Vila Martí', '2008-11-09', 'Femenino', 'Club Nàutic El Balís'),
    ('STDEMO0012', 'Marc', 'Soler Prat', '2009-12-12', 'Masculino', 'Club Nàutic Garraf'),
    ('STDEMO0013', 'Emma', 'Font Riera', '2008-01-15', 'Femenino', 'Real Club Náutico de Valencia'),
    ('STDEMO0014', 'Joan', 'Pons Vidal', '2009-02-18', 'Masculino', 'Real Club de Regatas de Alicante'),
    ('STDEMO0015', 'Arnau', 'Serra Grau', '2005-03-21', 'Masculino', 'Real Club Náutico de Torrevieja'),
    ('STDEMO0016', 'Pol', 'Roca Mas', '2005-04-24', 'Masculino', 'Real Club Náutico de Portosín'),
    ('STDEMO0017', 'Carla', 'Ferrer Lluch', '2009-05-02', 'Femenino', 'Real Club Náutico de Vigo'),
    ('STDEMO0018', 'Adrián', 'Navarro Gil', '2009-06-05', 'Masculino', 'Real Club Náutico de Vigo'),
    ('STDEMO0019', 'Júlia', 'Torres Miró', '2009-07-08', 'Femenino', 'Real Club Náutico de A Coruña'),
    ('STDEMO0020', 'Álex', 'Ribes Pastor', '2009-08-11', 'Masculino', 'Real Club Náutico de A Coruña'),
    ('STDEMO0021', 'Iria', 'Lema Fariña', '2009-09-14', 'Femenino', 'Real Club Náutico de Sanxenxo'),
    ('STDEMO0022', 'Antón', 'Varela Piñeiro', '2009-10-17', 'Masculino', 'Real Club Náutico de Sanxenxo'),
    ('STDEMO0023', 'Marina', 'Fuster Bosch', '2009-11-20', 'Femenino', 'Real Club Náutico de Palma'),
    ('STDEMO0024', 'Miquel', 'Riera Salom', '2009-12-23', 'Masculino', 'Real Club Náutico de Palma'),
    ('STDEMO0025', 'Nerea', 'Costa Beltrán', '2003-01-01', 'Femenino', 'Club Nàutic S''Arenal'),
    ('STDEMO0026', 'Daniel', 'Soler Ferrando', '2003-02-04', 'Masculino', 'Club Nàutic S''Arenal'),
    ('STDEMO0027', 'Elena', 'Ortega Vidal', '2003-03-07', 'Femenino', 'Real Club Náutico Port de Pollença'),
    ('STDEMO0028', 'Sergio', 'Molina Roca', '2003-04-10', 'Masculino', 'Real Club Náutico Port de Pollença'),
    ('STDEMO0029', 'Sira', 'Ferrer Puig', '2009-05-13', 'Femenino', 'Club Marítimo San Antonio de la Playa'),
    ('STDEMO0030', 'Jan', 'Vila Roca', '2009-06-16', 'Masculino', 'Club Marítimo San Antonio de la Playa'),
    ('STDEMO0031', 'Nora', 'Serra Font', '2009-07-19', 'Femenino', 'Real Club Náutico de Barcelona'),
    ('STDEMO0032', 'Oriol', 'Mas Riera', '2009-08-22', 'Masculino', 'Real Club Náutico de Barcelona'),
    ('STDEMO0033', 'Mateo', 'Gil Navarro', '2003-09-25', 'Masculino', 'Club Náutico El Masnou'),
    ('STDEMO0034', 'Lucas', 'Ribes Costa', '2003-10-03', 'Masculino', 'Club Náutico El Masnou'),
    ('STDEMO0035', 'Diego', 'Pastor Soler', '2003-11-06', 'Masculino', 'Club Nàutic El Balís'),
    ('STDEMO0036', 'Pablo', 'Bosch Ferrer', '2003-12-09', 'Masculino', 'Club Nàutic El Balís');

CREATE TEMP TABLE st_unidades (
    codigo TEXT PRIMARY KEY, clase TEXT NOT NULL, inicio DATE NOT NULL,
    fin DATE, patron TEXT NOT NULL, tripulante TEXT, id_unidad INTEGER
) ON COMMIT DROP;
INSERT INTO st_unidades (codigo, clase, inicio, fin, patron, tripulante) VALUES
    ('U01', 'Optimist', '2025-01-01', NULL, 'STDEMO0001', NULL),
    ('U02', 'Optimist', '2025-01-01', NULL, 'STDEMO0002', NULL),
    ('U03', 'Optimist', '2025-01-01', NULL, 'STDEMO0003', NULL),
    ('U04', 'Optimist', '2025-01-01', NULL, 'STDEMO0004', NULL),
    ('U05', 'Optimist', '2025-01-01', NULL, 'STDEMO0005', NULL),
    ('U06', 'Optimist', '2025-01-01', NULL, 'STDEMO0006', NULL),
    ('U07', 'ILCA 4', '2025-01-01', NULL, 'STDEMO0007', NULL),
    ('U08', 'ILCA 4', '2025-01-01', NULL, 'STDEMO0008', NULL),
    ('U09', 'ILCA 4', '2025-01-01', NULL, 'STDEMO0009', NULL),
    ('U10', 'ILCA 4', '2025-01-01', NULL, 'STDEMO0010', NULL),
    ('U11', 'ILCA 6', '2025-01-01', NULL, 'STDEMO0011', NULL),
    ('U12', 'ILCA 6', '2025-01-01', NULL, 'STDEMO0012', NULL),
    ('U13', 'ILCA 6', '2025-01-01', NULL, 'STDEMO0013', NULL),
    ('U14', 'ILCA 6', '2025-01-01', NULL, 'STDEMO0014', NULL),
    ('U15', 'ILCA 7', '2025-01-01', NULL, 'STDEMO0015', NULL),
    ('U16', 'ILCA 7', '2025-01-01', NULL, 'STDEMO0016', NULL),
    ('U17', '420', '2025-01-01', NULL, 'STDEMO0017', 'STDEMO0018'),
    ('U18', '420', '2025-01-01', NULL, 'STDEMO0019', 'STDEMO0020'),
    ('U19', '420', '2025-01-01', NULL, 'STDEMO0021', 'STDEMO0022'),
    ('U20', '420', '2025-01-01', NULL, 'STDEMO0023', 'STDEMO0024'),
    ('U21', '470', '2025-01-01', NULL, 'STDEMO0025', 'STDEMO0026'),
    ('U22', '470', '2025-01-01', NULL, 'STDEMO0027', 'STDEMO0028'),
    ('U23', '29er', '2025-01-01', NULL, 'STDEMO0029', 'STDEMO0030'),
    ('U24', '29er', '2025-01-01', NULL, 'STDEMO0031', 'STDEMO0032'),
    ('U25', '49er', '2025-01-01', NULL, 'STDEMO0033', 'STDEMO0034'),
    ('U26', '49er', '2025-01-01', NULL, 'STDEMO0035', 'STDEMO0036'),
    ('H01', 'Optimist', '2024-01-01', '2024-12-31', 'STDEMO0007', NULL),
    ('H02', 'Optimist', '2024-01-01', '2024-12-31', 'STDEMO0008', NULL),
    ('H03', '420', '2024-01-01', '2024-12-31', 'STDEMO0025', 'STDEMO0026');

CREATE TEMP TABLE st_competiciones (
    codigo TEXT PRIMARY KEY, nombre TEXT NOT NULL, inicio DATE NOT NULL,
    fin DATE NOT NULL, localidad TEXT NOT NULL, nivel TEXT NOT NULL,
    clase TEXT NOT NULL, id_competicion INTEGER
) ON COMMIT DROP;
INSERT INTO st_competiciones (codigo, nombre, inicio, fin, localidad, nivel, clase) VALUES
    ('C01', 'DEMO ST 2026 - Encuentro 1 - Optimist', '2026-05-02', '2026-05-03', 'Valencia', 'Nacional', 'Optimist'),
    ('C02', 'DEMO ST 2026 - Encuentro 2 - Optimist', '2026-09-02', '2026-09-03', 'Palma', 'Nacional', 'Optimist'),
    ('C03', 'DEMO ST 2026 - Encuentro 1 - ILCA 4', '2026-05-05', '2026-05-06', 'Valencia', 'Nacional', 'ILCA 4'),
    ('C04', 'DEMO ST 2026 - Encuentro 2 - ILCA 4', '2026-09-05', '2026-09-06', 'Palma', 'Nacional', 'ILCA 4'),
    ('C05', 'DEMO ST 2026 - Encuentro 1 - ILCA 6', '2026-05-08', '2026-05-09', 'Valencia', 'Nacional', 'ILCA 6'),
    ('C06', 'DEMO ST 2026 - Encuentro 2 - ILCA 6', '2026-09-08', '2026-09-09', 'Palma', 'Nacional', 'ILCA 6'),
    ('C07', 'DEMO ST 2026 - Encuentro 1 - ILCA 7', '2026-05-11', '2026-05-12', 'Valencia', 'Nacional', 'ILCA 7'),
    ('C08', 'DEMO ST 2026 - Encuentro 2 - ILCA 7', '2026-09-11', '2026-09-12', 'Palma', 'Nacional', 'ILCA 7'),
    ('C09', 'DEMO ST 2026 - Encuentro 1 - 420', '2026-05-14', '2026-05-15', 'Valencia', 'Nacional', '420'),
    ('C10', 'DEMO ST 2026 - Encuentro 2 - 420', '2026-09-14', '2026-09-15', 'Palma', 'Nacional', '420'),
    ('C11', 'DEMO ST 2026 - Encuentro 1 - 470', '2026-05-17', '2026-05-18', 'Valencia', 'Nacional', '470'),
    ('C12', 'DEMO ST 2026 - Encuentro 2 - 470', '2026-09-17', '2026-09-18', 'Palma', 'Nacional', '470'),
    ('C13', 'DEMO ST 2026 - Encuentro 1 - 29er', '2026-05-20', '2026-05-21', 'Valencia', 'Nacional', '29er'),
    ('C14', 'DEMO ST 2026 - Encuentro 2 - 29er', '2026-09-20', '2026-09-21', 'Palma', 'Nacional', '29er'),
    ('C15', 'DEMO ST 2026 - Encuentro 1 - 49er', '2026-05-23', '2026-05-24', 'Valencia', 'Nacional', '49er'),
    ('C16', 'DEMO ST 2026 - Encuentro 2 - 49er', '2026-09-23', '2026-09-24', 'Palma', 'Nacional', '49er'),
    ('C17', 'DEMO ST 2024 - Encuentro histórico - Optimist', '2024-06-15', '2024-06-16', 'Palma', 'Nacional', 'Optimist'),
    ('C18', 'DEMO ST 2024 - Encuentro histórico - 420', '2024-06-22', '2024-06-23', 'Palma', 'Nacional', '420');

CREATE TEMP TABLE st_resultados (
    unidad TEXT NOT NULL, competicion TEXT NOT NULL,
    posicion INTEGER NOT NULL CHECK (posicion > 0),
    puntos NUMERIC(10,2) NOT NULL CHECK (puntos >= 0),
    PRIMARY KEY (unidad, competicion), UNIQUE (competicion, posicion)
) ON COMMIT DROP;
INSERT INTO st_resultados (unidad, competicion, posicion, puntos) VALUES
    ('U01', 'C01', 1, 10),
    ('U02', 'C01', 2, 19),
    ('U03', 'C01', 3, 28),
    ('U04', 'C01', 4, 37),
    ('U05', 'C01', 5, 46),
    ('U06', 'C01', 6, 55),
    ('U02', 'C02', 1, 11),
    ('U03', 'C02', 2, 20),
    ('U04', 'C02', 3, 29),
    ('U05', 'C02', 4, 38),
    ('U06', 'C02', 5, 47),
    ('U01', 'C02', 6, 56),
    ('U07', 'C03', 1, 10),
    ('U08', 'C03', 2, 19),
    ('U09', 'C03', 3, 28),
    ('U10', 'C03', 4, 37),
    ('U08', 'C04', 1, 11),
    ('U09', 'C04', 2, 20),
    ('U10', 'C04', 3, 29),
    ('U07', 'C04', 4, 38),
    ('U11', 'C05', 1, 10),
    ('U12', 'C05', 2, 19),
    ('U13', 'C05', 3, 28),
    ('U14', 'C05', 4, 37),
    ('U12', 'C06', 1, 11),
    ('U13', 'C06', 2, 20),
    ('U14', 'C06', 3, 29),
    ('U11', 'C06', 4, 38),
    ('U15', 'C07', 1, 10),
    ('U16', 'C07', 2, 19),
    ('U16', 'C08', 1, 11),
    ('U15', 'C08', 2, 20),
    ('U17', 'C09', 1, 10),
    ('U18', 'C09', 2, 19),
    ('U19', 'C09', 3, 28),
    ('U20', 'C09', 4, 37),
    ('U18', 'C10', 1, 11),
    ('U19', 'C10', 2, 20),
    ('U20', 'C10', 3, 29),
    ('U17', 'C10', 4, 38),
    ('U21', 'C11', 1, 10),
    ('U22', 'C11', 2, 19),
    ('U22', 'C12', 1, 11),
    ('U21', 'C12', 2, 20),
    ('U23', 'C13', 1, 10),
    ('U24', 'C13', 2, 19),
    ('U24', 'C14', 1, 11),
    ('U23', 'C14', 2, 20),
    ('U25', 'C15', 1, 10),
    ('U26', 'C15', 2, 19),
    ('U26', 'C16', 1, 11),
    ('U25', 'C16', 2, 20),
    ('H01', 'C17', 1, 10),
    ('H02', 'C17', 2, 20),
    ('H03', 'C18', 1, 10);

-- Validaciones previas: nunca insertar deportistas sin resolver su club.
DO $precondiciones$
BEGIN
    IF EXISTS (
        SELECT 1 FROM st_clubes esperado
        WHERE (SELECT COUNT(*) FROM public.club c
               JOIN public.federacion_autonomica f
                 ON f.id_federacion = c.id_federacion
               WHERE c.nombre = esperado.nombre
                 AND f.nombre = esperado.federacion) <> 1
           OR (SELECT COUNT(*) FROM public.club c
               WHERE c.nombre = esperado.nombre) <> 1
    ) THEN
        RAISE EXCEPTION 'Faltan clubes/federaciones, hay clubes duplicados o enlaces incorrectos. Revisar sample_data.sql.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM st_clases esperado
        WHERE (SELECT COUNT(*) FROM public.clase c
               WHERE c.nombre = esperado.nombre
                 AND c.numero_tripulantes = esperado.tripulantes) <> 1
    ) THEN
        RAISE EXCEPTION 'Faltan clases o su número de tripulantes es incorrecto.';
    END IF;
    IF EXISTS (SELECT 1 FROM public.deportista d
               JOIN st_deportistas s ON s.dni = d.dni)
       OR EXISTS (SELECT 1 FROM public.tecnico
                  WHERE dni IN ('STTEC001','STTEC002','STTEC003','STTEC004'))
       OR EXISTS (SELECT 1 FROM public.competicion c
                  JOIN st_competiciones s ON s.nombre = c.nombre) THEN
        RAISE EXCEPTION 'Los datos DEMO ya existen total o parcialmente. No se permite repetir esta carga.';
    END IF;
END;
$precondiciones$;

-- 1. Deportistas: DNI ficticio y club resuelto por nombre.
INSERT INTO public.deportista (
    dni, nombre, apellidos, fecha_nacimiento, sexo, id_club
)
SELECT d.dni, d.nombre, d.apellidos, d.nacimiento, d.sexo,
       (SELECT c.id_club FROM public.club c WHERE c.nombre = d.club)
FROM st_deportistas d;

-- 2. Unidades y miembros. RETURNING captura el ID real, sea cual sea su valor.
DO $equipos$
DECLARE
    fila RECORD;
    nueva_unidad INTEGER;
BEGIN
    FOR fila IN SELECT * FROM st_unidades ORDER BY codigo LOOP
        INSERT INTO public.unidad_competitiva (fecha_inicio, fecha_fin, id_clase)
        VALUES (fila.inicio, fila.fin,
                (SELECT id_clase FROM public.clase WHERE nombre = fila.clase))
        RETURNING id_unidad INTO nueva_unidad;

        UPDATE st_unidades SET id_unidad = nueva_unidad WHERE codigo = fila.codigo;
        INSERT INTO public.forma_parte (dni_deportista, id_unidad, rol)
        VALUES (fila.patron, nueva_unidad, 'Patron');
        IF fila.tripulante IS NOT NULL THEN
            INSERT INTO public.forma_parte (dni_deportista, id_unidad, rol)
            VALUES (fila.tripulante, nueva_unidad, 'Tripulante');
        END IF;
    END LOOP;
END;
$equipos$;

-- 3. Competiciones de una sola clase. Los nombres identifican datos ficticios.
DO $regatas$
DECLARE
    fila RECORD;
    nueva_competicion INTEGER;
BEGIN
    FOR fila IN SELECT * FROM st_competiciones ORDER BY codigo LOOP
        INSERT INTO public.competicion (
            nombre, fecha_inicio, fecha_fin, localidad, nivel, id_clase
        ) VALUES (
            fila.nombre, fila.inicio, fila.fin, fila.localidad, fila.nivel,
            (SELECT id_clase FROM public.clase WHERE nombre = fila.clase)
        ) RETURNING id_competicion INTO nueva_competicion;
        UPDATE st_competiciones SET id_competicion = nueva_competicion
        WHERE codigo = fila.codigo;
    END LOOP;
END;
$regatas$;

-- 4. Una fila por equipo/regata, NO una por cada miembro del equipo.
INSERT INTO public.participa_en (
    id_unidad, id_competicion, posicion_general, posicion_categoria, puntos
)
SELECT u.id_unidad, c.id_competicion, r.posicion, NULL, r.puntos
FROM st_resultados r
JOIN st_unidades u ON u.codigo = r.unidad
JOIN st_competiciones c ON c.codigo = r.competicion;

-- 5. Mediciones: sin registro para 9 deportistas; otros tienen una o dos fechas.
-- Son valores ilustrativos para probar consultas, no referencias médicas.
INSERT INTO public.registro_antropometrico (
    dni_deportista, fecha, altura, peso, envergadura, porcentaje_graso
) VALUES
    ('STDEMO0001', '2025-10-15', 146, 38, 149, 18),
    ('STDEMO0001', '2026-10-15', 148, 39, 151, 18),
    ('STDEMO0002', '2025-10-15', 147, 39, 150, 19),
    ('STDEMO0002', '2026-10-15', 149, 40, 152, 19),
    ('STDEMO0003', '2025-10-15', 148, 40, 151, 20),
    ('STDEMO0003', '2026-10-15', 150, 41, 153, 20),
    ('STDEMO0005', '2026-10-15', 147, 43, 150, 22),
    ('STDEMO0006', '2025-10-15', 146, 43, 149, 17),
    ('STDEMO0006', '2026-10-15', 148, 44, 151, 17),
    ('STDEMO0007', '2025-10-15', 162, 49, 165, NULL),
    ('STDEMO0007', '2026-10-15', 164, 50, 167, NULL),
    ('STDEMO0009', '2025-10-15', 164, 51, 167, 20),
    ('STDEMO0009', '2026-10-15', 166, 52, 169, 20),
    ('STDEMO0010', '2026-10-15', 162, 53, 165, 21),
    ('STDEMO0011', '2025-10-15', 170, 64, 173, 22),
    ('STDEMO0011', '2026-10-15', 172, 65, 175, 22),
    ('STDEMO0013', '2025-10-15', 172, 66, 175, 18),
    ('STDEMO0013', '2026-10-15', 174, 67, 177, 18),
    ('STDEMO0014', '2025-10-15', 173, 60, 176, NULL),
    ('STDEMO0014', '2026-10-15', 175, 61, 178, NULL),
    ('STDEMO0015', '2026-10-15', 180, 77, 183, 20),
    ('STDEMO0017', '2025-10-15', 169, 59, 172, 22),
    ('STDEMO0017', '2026-10-15', 171, 60, 174, 22),
    ('STDEMO0018', '2025-10-15', 170, 60, 173, 17),
    ('STDEMO0018', '2026-10-15', 172, 61, 175, 17),
    ('STDEMO0019', '2025-10-15', 171, 61, 174, 18),
    ('STDEMO0019', '2026-10-15', 173, 62, 176, 18),
    ('STDEMO0021', '2025-10-15', 168, 56, 171, NULL),
    ('STDEMO0021', '2026-10-15', 170, 57, 173, NULL),
    ('STDEMO0022', '2025-10-15', 169, 57, 172, 21),
    ('STDEMO0022', '2026-10-15', 171, 58, 174, 21),
    ('STDEMO0023', '2025-10-15', 170, 58, 173, 22),
    ('STDEMO0023', '2026-10-15', 172, 59, 175, 22),
    ('STDEMO0025', '2026-10-15', 174, 69, 177, 18),
    ('STDEMO0026', '2025-10-15', 173, 69, 176, 19),
    ('STDEMO0026', '2026-10-15', 175, 70, 178, 19),
    ('STDEMO0027', '2025-10-15', 174, 70, 177, 20),
    ('STDEMO0027', '2026-10-15', 176, 71, 179, 20),
    ('STDEMO0029', '2025-10-15', 172, 56, 175, 22),
    ('STDEMO0029', '2026-10-15', 174, 57, 177, 22),
    ('STDEMO0030', '2026-10-15', 170, 58, 173, 17),
    ('STDEMO0031', '2025-10-15', 169, 58, 172, 18),
    ('STDEMO0031', '2026-10-15', 171, 59, 174, 18),
    ('STDEMO0033', '2025-10-15', 182, 82, 185, 20),
    ('STDEMO0033', '2026-10-15', 184, 83, 187, 20),
    ('STDEMO0034', '2025-10-15', 183, 83, 186, 21),
    ('STDEMO0034', '2026-10-15', 185, 84, 188, 21),
    ('STDEMO0035', '2026-10-15', 181, 78, 184, NULL);

-- 6. Técnicos ficticios e informes para 12 deportistas; 24 quedan sin informes.
INSERT INTO public.tecnico (dni, nombre, apellidos, titulacion) VALUES
    ('STTEC001', 'Eva', 'Lago Ríos', 'Técnico deportivo en vela (ficticio)'),
    ('STTEC002', 'Toni', 'Serra Pons', 'Técnico deportivo en vela (ficticio)'),
    ('STTEC003', 'Mireia', 'Font Soler', 'Técnico deportivo en vela (ficticio)'),
    ('STTEC004', 'Carlos', 'Ribes Gil', 'Técnico deportivo en vela (ficticio)');

INSERT INTO public.informe (
    fecha, estrategia, tactica, trimado, tecnica, fortalezas, debilidades,
    recomendaciones, dni_deportista, dni_tecnico
) VALUES
    ('2026-10-20', 3, 5, 3, 4, 'DEMO: mantiene una rutina ordenada de preparación.', 'DEMO: necesita mejorar la regularidad en las salidas.', 'DEMO: practicar salidas y revisar maniobras con el equipo técnico.', 'STDEMO0003', 'STTEC001'),
    ('2026-10-20', 3, 4, 3, NULL, 'DEMO: mantiene una rutina ordenada de preparación.', 'DEMO: necesita mejorar la regularidad en las salidas.', 'DEMO: practicar salidas y revisar maniobras con el equipo técnico.', 'STDEMO0006', 'STTEC002'),
    ('2026-10-20', 3, 3, 3, 4, 'DEMO: mantiene una rutina ordenada de preparación.', 'DEMO: necesita mejorar la regularidad en las salidas.', 'DEMO: practicar salidas y revisar maniobras con el equipo técnico.', 'STDEMO0009', 'STTEC003'),
    ('2026-10-20', 3, 2, 3, NULL, 'DEMO: mantiene una rutina ordenada de preparación.', 'DEMO: necesita mejorar la regularidad en las salidas.', 'DEMO: practicar salidas y revisar maniobras con el equipo técnico.', 'STDEMO0012', 'STTEC004'),
    ('2026-10-20', 3, 5, 3, 4, 'DEMO: mantiene una rutina ordenada de preparación.', 'DEMO: necesita mejorar la regularidad en las salidas.', 'DEMO: practicar salidas y revisar maniobras con el equipo técnico.', 'STDEMO0015', 'STTEC001'),
    ('2026-10-20', 3, 4, 3, NULL, 'DEMO: mantiene una rutina ordenada de preparación.', 'DEMO: necesita mejorar la regularidad en las salidas.', 'DEMO: practicar salidas y revisar maniobras con el equipo técnico.', 'STDEMO0018', 'STTEC002'),
    ('2026-10-20', 3, 3, 3, 4, 'DEMO: mantiene una rutina ordenada de preparación.', 'DEMO: necesita mejorar la regularidad en las salidas.', 'DEMO: practicar salidas y revisar maniobras con el equipo técnico.', 'STDEMO0021', 'STTEC003'),
    ('2026-10-20', 3, 2, 3, NULL, 'DEMO: mantiene una rutina ordenada de preparación.', 'DEMO: necesita mejorar la regularidad en las salidas.', 'DEMO: practicar salidas y revisar maniobras con el equipo técnico.', 'STDEMO0024', 'STTEC004'),
    ('2026-10-20', 3, 5, 3, 4, 'DEMO: mantiene una rutina ordenada de preparación.', 'DEMO: necesita mejorar la regularidad en las salidas.', 'DEMO: practicar salidas y revisar maniobras con el equipo técnico.', 'STDEMO0027', 'STTEC001'),
    ('2026-10-20', 3, 4, 3, NULL, 'DEMO: mantiene una rutina ordenada de preparación.', 'DEMO: necesita mejorar la regularidad en las salidas.', 'DEMO: practicar salidas y revisar maniobras con el equipo técnico.', 'STDEMO0030', 'STTEC002'),
    ('2026-10-20', 3, 3, 3, 4, 'DEMO: mantiene una rutina ordenada de preparación.', 'DEMO: necesita mejorar la regularidad en las salidas.', 'DEMO: practicar salidas y revisar maniobras con el equipo técnico.', 'STDEMO0033', 'STTEC003'),
    ('2026-10-20', 3, 2, 3, NULL, 'DEMO: mantiene una rutina ordenada de preparación.', 'DEMO: necesita mejorar la regularidad en las salidas.', 'DEMO: practicar salidas y revisar maniobras con el equipo técnico.', 'STDEMO0036', 'STTEC004');

-- 7. Integridad deportiva adicional (no está garantizada por el esquema original).
DO $validacion$
BEGIN
    IF (SELECT COUNT(*) FROM public.deportista d
        JOIN st_deportistas s ON s.dni = d.dni) <> 36
       OR (SELECT COUNT(*) FROM public.forma_parte fp
           JOIN st_unidades s ON s.id_unidad = fp.id_unidad) <> 40
       OR (SELECT COUNT(*) FROM public.participa_en p
           JOIN st_competiciones s ON s.id_competicion = p.id_competicion) <> 55 THEN
        RAISE EXCEPTION 'Carga incompleta: recuentos inesperados.';
    END IF;

    -- Tripulación exacta: una persona en clases individuales y dos en dobles.
    IF EXISTS (
        SELECT u.id_unidad
        FROM public.unidad_competitiva u
        JOIN st_unidades s ON s.id_unidad = u.id_unidad
        JOIN public.clase c ON c.id_clase = u.id_clase
        LEFT JOIN public.forma_parte fp ON fp.id_unidad = u.id_unidad
        LEFT JOIN public.deportista d ON d.dni = fp.dni_deportista
        GROUP BY u.id_unidad, c.numero_tripulantes
        HAVING COUNT(fp.dni_deportista) <> c.numero_tripulantes
           OR COUNT(*) FILTER (WHERE fp.rol = 'Patron') <> 1
           OR COUNT(*) FILTER (WHERE fp.rol = 'Tripulante') <> c.numero_tripulantes - 1
           OR COUNT(DISTINCT d.id_club) <> 1
    ) THEN
        RAISE EXCEPTION 'Tripulación incompleta, roles incorrectos o miembros de clubes diferentes.';
    END IF;

    -- Un deportista no pertenece a equipos con intervalos solapados.
    IF EXISTS (
        SELECT 1 FROM public.forma_parte a
        JOIN st_deportistas d ON d.dni = a.dni_deportista
        JOIN public.forma_parte b ON b.dni_deportista = a.dni_deportista
                                  AND b.id_unidad > a.id_unidad
        JOIN public.unidad_competitiva ua ON ua.id_unidad = a.id_unidad
        JOIN public.unidad_competitiva ub ON ub.id_unidad = b.id_unidad
        WHERE ua.fecha_inicio <= COALESCE(ub.fecha_fin, 'infinity'::date)
          AND ub.fecha_inicio <= COALESCE(ua.fecha_fin, 'infinity'::date)
    ) THEN
        RAISE EXCEPTION 'Un deportista aparece en unidades con fechas solapadas.';
    END IF;

    -- Clase del equipo = clase de la regata; equipo activo durante TODA la regata.
    IF EXISTS (
        SELECT 1 FROM public.participa_en p
        JOIN st_competiciones s ON s.id_competicion = p.id_competicion
        JOIN public.competicion c ON c.id_competicion = p.id_competicion
        JOIN public.unidad_competitiva u ON u.id_unidad = p.id_unidad
        WHERE u.id_clase <> c.id_clase OR u.fecha_inicio > c.fecha_inicio
           OR (u.fecha_fin IS NOT NULL AND u.fecha_fin < c.fecha_fin)
    ) THEN
        RAISE EXCEPTION 'Clase incorrecta o unidad inactiva durante una regata.';
    END IF;

    -- Regla solicitada: NO hay dos equipos con la misma posición en una regata.
    IF EXISTS (
        SELECT p.id_competicion, p.posicion_general
        FROM public.participa_en p
        JOIN st_competiciones s ON s.id_competicion = p.id_competicion
        GROUP BY p.id_competicion, p.posicion_general
        HAVING COUNT(*) > 1 OR p.posicion_general IS NULL
    ) THEN
        RAISE EXCEPTION 'Posiciones generales duplicadas o desconocidas en una competición.';
    END IF;

    -- Flotas DEMO completas: puestos consecutivos 1..N; sin huecos ni empates.
    IF EXISTS (
        SELECT p.id_competicion
        FROM public.participa_en p
        JOIN st_competiciones s ON s.id_competicion = p.id_competicion
        GROUP BY p.id_competicion
        HAVING MIN(p.posicion_general) <> 1
            OR MAX(p.posicion_general) <> COUNT(*)
    ) THEN
        RAISE EXCEPTION 'La clasificación no es consecutiva desde 1 hasta el número de unidades.';
    END IF;

    IF EXISTS (
        SELECT p.id_competicion, fp.dni_deportista
        FROM public.participa_en p
        JOIN st_competiciones s ON s.id_competicion = p.id_competicion
        JOIN public.forma_parte fp ON fp.id_unidad = p.id_unidad
        GROUP BY p.id_competicion, fp.dni_deportista HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION 'Un deportista participa con dos unidades en la misma regata.';
    END IF;

    IF EXISTS (
        SELECT 1 FROM public.participa_en a
        JOIN st_competiciones s ON s.id_competicion = a.id_competicion
        JOIN public.participa_en b ON b.id_competicion = a.id_competicion
        WHERE a.posicion_general < b.posicion_general AND a.puntos >= b.puntos
    ) THEN
        RAISE EXCEPTION 'Puntuaciones incoherentes con el orden de la clasificación.';
    END IF;

    -- Edad infantil coherente en las regatas Optimist del conjunto DEMO.
    IF EXISTS (
        SELECT 1 FROM public.participa_en p
        JOIN st_competiciones s ON s.id_competicion = p.id_competicion
        JOIN public.competicion c ON c.id_competicion = p.id_competicion
        JOIN public.clase cl ON cl.id_clase = c.id_clase
        JOIN public.forma_parte fp ON fp.id_unidad = p.id_unidad
        JOIN public.deportista d ON d.dni = fp.dni_deportista
        WHERE cl.nombre = 'Optimist'
          AND EXTRACT(YEAR FROM c.fecha_inicio) - EXTRACT(YEAR FROM d.fecha_nacimiento) > 15
    ) THEN
        RAISE EXCEPTION 'Edad no coherente con Optimist en los datos de prueba.';
    END IF;
END;
$validacion$;

-- Resumen SOLO de esta carga, antes de eliminar las tablas temporales.
SELECT 'Deportistas DEMO' AS tabla, COUNT(*) AS total FROM st_deportistas
UNION ALL SELECT 'Unidades DEMO', COUNT(*) FROM st_unidades
UNION ALL SELECT 'Pertenencias DEMO', COUNT(*) FROM public.forma_parte fp
          JOIN st_unidades u ON u.id_unidad = fp.id_unidad
UNION ALL SELECT 'Competiciones DEMO', COUNT(*) FROM st_competiciones
UNION ALL SELECT 'Resultados DEMO', COUNT(*) FROM st_resultados
UNION ALL SELECT 'Mediciones DEMO', COUNT(*) FROM public.registro_antropometrico r
          JOIN st_deportistas d ON d.dni = r.dni_deportista
UNION ALL SELECT 'Informes DEMO', COUNT(*) FROM public.informe i
          JOIN st_deportistas d ON d.dni = i.dni_deportista;

COMMIT;

-- Nota: estas validaciones protegen esta carga. Para garantizar posiciones
-- únicas en FUTURAS inserciones, valorar una migración independiente con:
-- UNIQUE (id_competicion, posicion_general) sobre public.participa_en.
