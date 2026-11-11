-- Completa la ubicación de los 15 clubes de sample_data.sql.
-- Criterio: localidad = municipio; provincia = provincia administrativa.
-- Fuentes y núcleos de población: docs/fuentes_localidades_clubes.md.
-- Supabase / Cloud SQL. Repetible: solo rellena NULL o cadenas vacías.
-- No crea clubes ni sobrescribe ubicaciones ya informadas.

BEGIN;
SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '60s';

WITH ubicaciones (nombre, federacion, localidad, provincia) AS (
    VALUES
        ('Real Club Náutico de Portosín', 'Real Federación Gallega de Vela', 'Porto do Son', 'A Coruña'),
        ('Real Club Náutico de Vigo', 'Real Federación Gallega de Vela', 'Vigo', 'Pontevedra'),
        ('Real Club Náutico de A Coruña', 'Real Federación Gallega de Vela', 'A Coruña', 'A Coruña'),
        ('Real Club Náutico de Sanxenxo', 'Real Federación Gallega de Vela', 'Sanxenxo', 'Pontevedra'),
        ('Real Club Náutico de Palma', 'Federación Balear de Vela', 'Palma', 'Illes Balears'),
        ('Club Nàutic S''Arenal', 'Federación Balear de Vela', 'Llucmajor', 'Illes Balears'),
        ('Real Club Náutico Port de Pollença', 'Federación Balear de Vela', 'Pollença', 'Illes Balears'),
        ('Club Marítimo San Antonio de la Playa', 'Federación Balear de Vela', 'Palma', 'Illes Balears'),
        ('Real Club Náutico de Barcelona', 'Federación Catalana de Vela', 'Barcelona', 'Barcelona'),
        ('Club Náutico El Masnou', 'Federación Catalana de Vela', 'El Masnou', 'Barcelona'),
        ('Club Nàutic El Balís', 'Federación Catalana de Vela', 'Sant Andreu de Llavaneres', 'Barcelona'),
        ('Club Nàutic Garraf', 'Federación Catalana de Vela', 'Sitges', 'Barcelona'),
        ('Real Club Náutico de Valencia', 'Federación de la Comunidad Valenciana de Vela', 'Valencia', 'Valencia'),
        ('Real Club de Regatas de Alicante', 'Federación de la Comunidad Valenciana de Vela', 'Alicante', 'Alicante'),
        ('Real Club Náutico de Torrevieja', 'Federación de la Comunidad Valenciana de Vela', 'Torrevieja', 'Alicante')
)
UPDATE public.club AS c
SET localidad = CASE WHEN NULLIF(BTRIM(c.localidad), '') IS NULL
                     THEN u.localidad ELSE c.localidad END,
    provincia = CASE WHEN NULLIF(BTRIM(c.provincia), '') IS NULL
                     THEN u.provincia ELSE c.provincia END
FROM ubicaciones AS u, public.federacion_autonomica AS f
WHERE c.nombre = u.nombre
  AND c.id_federacion = f.id_federacion
  AND f.nombre = u.federacion
  AND (NULLIF(BTRIM(c.localidad), '') IS NULL
       OR NULLIF(BTRIM(c.provincia), '') IS NULL);

COMMIT;
