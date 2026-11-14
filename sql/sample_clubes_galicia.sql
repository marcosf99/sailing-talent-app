-- Clubes gallegos identificados en las clasificaciones de Optimist e ILCA 4
-- de la XXVII Semana del Atlántico Ciudad de Vigo (2026).
-- Procedencia y correspondencias: docs/fuentes_clubes_galicia.md.
-- Ejecutar después de create_tables.sql y sample_data.sql.
-- Compatible con Supabase y Cloud SQL. Puede repetirse sin duplicar clubes.
-- No modifica los cuatro clubes gallegos de sample_data.sql ni sus IDs.

BEGIN;
SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '60s';

-- club no tiene una restricción UNIQUE por nombre: serializamos las altas
-- mientras comprobamos si existe cada club. Las consultas siguen permitidas.
LOCK TABLE public.club IN SHARE ROW EXCLUSIVE MODE;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.federacion_autonomica
        WHERE nombre = 'Real Federación Gallega de Vela'
    ) THEN
        RAISE EXCEPTION 'Falta Real Federación Gallega de Vela; ejecutar primero sample_data.sql';
    END IF;
END;
$$;

WITH nuevos (nombre, localidad, provincia) AS (
    VALUES
        ('Club Alamar Sada', 'Sada', 'A Coruña'),
        ('Club Grupo Bazán', 'Ferrol', 'A Coruña'),
        ('Club Marítimo de Oza O Puntal', 'A Coruña', 'A Coruña'),
        ('Club do Mar Cariño', 'Cariño', 'A Coruña'),
        ('Club Náutico Deportivo de Riveira', 'Ribeira', 'A Coruña'),
        ('Club Náutico Marina Coruña', 'A Coruña', 'A Coruña'),
        ('Club Náutico Ría de Ares', 'Ares', 'A Coruña'),
        ('Monte Real Club de Yates de Baiona', 'Baiona', 'Pontevedra'),
        ('Real Club de Mar de Aguete', 'Marín', 'Pontevedra'),
        ('Real Club Náutico Rodeira', 'Cangas', 'Pontevedra'),
        ('Club Marítimo de Canido', 'Vigo', 'Pontevedra')
)
INSERT INTO public.club (
    nombre, director_deportivo, telefono, localidad, provincia, id_federacion
)
-- id_club se genera automáticamente; no se inventan contactos ni directores.
SELECT n.nombre, NULL, NULL, n.localidad, n.provincia,
    (SELECT id_federacion FROM public.federacion_autonomica
     WHERE nombre = 'Real Federación Gallega de Vela')
FROM nuevos n
WHERE NOT EXISTS (
    SELECT 1 FROM public.club c
    WHERE LOWER(BTRIM(c.nombre)) = LOWER(BTRIM(n.nombre))
      AND c.id_federacion = (
          SELECT id_federacion FROM public.federacion_autonomica
          WHERE nombre = 'Real Federación Gallega de Vela'
      )
);

COMMIT;
