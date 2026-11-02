-- ============================================================
-- sailing-talent-app: sample_data.sql
-- Datos base compatibles con create_tables.sql (PostgreSQL).
-- Ejecutar conectado a la base de datos sailing_talent.
-- Incluye todos los atributos: DEFAULT para las columnas IDENTITY
-- y NULL para datos opcionales que el usuario no ha proporcionado.
-- Los clubes se vinculan mediante subconsultas por nombre único.
-- Carga inicial: ejecutar una sola vez sobre estas tablas sin datos.
-- No incluye deportistas ni información personal ficticia.
-- ============================================================

BEGIN;

-- 1. Federaciones autonómicas (7).
INSERT INTO public.federacion_autonomica (
    id_federacion, nombre, comunidad_autonoma, director_tecnico,
    direccion, telefono, correo_electronico
) VALUES
    (DEFAULT, 'Real Federación Gallega de Vela', 'Galicia', NULL, NULL, NULL, NULL),
    (DEFAULT, 'Federación Catalana de Vela', 'Cataluña', NULL, NULL, NULL, NULL),
    (DEFAULT, 'Federación Canaria de Vela', 'Canarias', NULL, NULL, NULL, NULL),
    (DEFAULT, 'Federación Balear de Vela', 'Illes Balears', NULL, NULL, NULL, NULL),
    (DEFAULT, 'Federación de la Comunidad Valenciana de Vela', 'Comunidad Valenciana', NULL, NULL, NULL, NULL),
    (DEFAULT, 'Federación Andaluza de Vela', 'Andalucía', NULL, NULL, NULL, NULL),
    (DEFAULT, 'Federación Cántabra de Vela', 'Cantabria', NULL, NULL, NULL, NULL);

-- 2. Clubes (15), agrupados por federación.
-- Localidad y provincia quedan pendientes de completar.
INSERT INTO public.club (
    id_club, nombre, director_deportivo, telefono,
    localidad, provincia, id_federacion
) VALUES
    (DEFAULT, 'Real Club Náutico de Portosín', NULL, NULL, NULL, NULL,
        (SELECT id_federacion FROM public.federacion_autonomica
         WHERE nombre = 'Real Federación Gallega de Vela')),
    (DEFAULT, 'Real Club Náutico de Vigo', NULL, NULL, NULL, NULL,
        (SELECT id_federacion FROM public.federacion_autonomica
         WHERE nombre = 'Real Federación Gallega de Vela')),
    (DEFAULT, 'Real Club Náutico de A Coruña', NULL, NULL, NULL, NULL,
        (SELECT id_federacion FROM public.federacion_autonomica
         WHERE nombre = 'Real Federación Gallega de Vela')),
    (DEFAULT, 'Real Club Náutico de Sanxenxo', NULL, NULL, NULL, NULL,
        (SELECT id_federacion FROM public.federacion_autonomica
         WHERE nombre = 'Real Federación Gallega de Vela')),
    (DEFAULT, 'Real Club Náutico de Palma', NULL, NULL, NULL, NULL,
        (SELECT id_federacion FROM public.federacion_autonomica
         WHERE nombre = 'Federación Balear de Vela')),
    (DEFAULT, 'Club Nàutic S''Arenal', NULL, NULL, NULL, NULL,
        (SELECT id_federacion FROM public.federacion_autonomica
         WHERE nombre = 'Federación Balear de Vela')),
    (DEFAULT, 'Real Club Náutico Port de Pollença', NULL, NULL, NULL, NULL,
        (SELECT id_federacion FROM public.federacion_autonomica
         WHERE nombre = 'Federación Balear de Vela')),
    (DEFAULT, 'Club Marítimo San Antonio de la Playa', NULL, NULL, NULL, NULL,
        (SELECT id_federacion FROM public.federacion_autonomica
         WHERE nombre = 'Federación Balear de Vela')),
    (DEFAULT, 'Real Club Náutico de Barcelona', NULL, NULL, NULL, NULL,
        (SELECT id_federacion FROM public.federacion_autonomica
         WHERE nombre = 'Federación Catalana de Vela')),
    (DEFAULT, 'Club Náutico El Masnou', NULL, NULL, NULL, NULL,
        (SELECT id_federacion FROM public.federacion_autonomica
         WHERE nombre = 'Federación Catalana de Vela')),
    (DEFAULT, 'Club Nàutic El Balís', NULL, NULL, NULL, NULL,
        (SELECT id_federacion FROM public.federacion_autonomica
         WHERE nombre = 'Federación Catalana de Vela')),
    (DEFAULT, 'Club Nàutic Garraf', NULL, NULL, NULL, NULL,
        (SELECT id_federacion FROM public.federacion_autonomica
         WHERE nombre = 'Federación Catalana de Vela')),
    (DEFAULT, 'Real Club Náutico de Valencia', NULL, NULL, NULL, NULL,
        (SELECT id_federacion FROM public.federacion_autonomica
         WHERE nombre = 'Federación de la Comunidad Valenciana de Vela')),
    (DEFAULT, 'Real Club de Regatas de Alicante', NULL, NULL, NULL, NULL,
        (SELECT id_federacion FROM public.federacion_autonomica
         WHERE nombre = 'Federación de la Comunidad Valenciana de Vela')),
    (DEFAULT, 'Real Club Náutico de Torrevieja', NULL, NULL, NULL, NULL,
        (SELECT id_federacion FROM public.federacion_autonomica
         WHERE nombre = 'Federación de la Comunidad Valenciana de Vela'));

-- 3. Clases (8).
-- Un tripulante: Optimist e ILCA 4/6/7.
-- Dos tripulantes: 420, 470, 29er y 49er.
-- Clasificación olímpica solicitada: 470, ILCA 6, ILCA 7 y 49er.
INSERT INTO public.clase (
    id_clase, nombre, numero_tripulantes, es_olimpica
) VALUES
    (DEFAULT, 'Optimist', 1, FALSE),
    (DEFAULT, '420', 2, FALSE),
    (DEFAULT, '470', 2, TRUE),
    (DEFAULT, 'ILCA 4', 1, FALSE),
    (DEFAULT, 'ILCA 6', 1, TRUE),
    (DEFAULT, 'ILCA 7', 1, TRUE),
    (DEFAULT, '29er', 2, FALSE),
    (DEFAULT, '49er', 2, TRUE);

COMMIT;
