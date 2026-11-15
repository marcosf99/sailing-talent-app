-- Variantes confirmadas y coincidencias descartadas, limitadas al club de la fuente.
-- Ejecutar después de la migración 001. No deduce decisiones de revisiones antiguas.
BEGIN;
SET LOCAL search_path TO public;
SET LOCAL lock_timeout='10s';
CREATE TABLE IF NOT EXISTS variante_nombre_deportista (
    dni_deportista VARCHAR(20) NOT NULL REFERENCES deportista(dni) ON UPDATE CASCADE ON DELETE RESTRICT,
    id_club INTEGER NOT NULL REFERENCES club(id_club) ON UPDATE CASCADE ON DELETE RESTRICT,
    nombre_original TEXT NOT NULL CHECK (BTRIM(nombre_original)<>''),
    nombre_normalizado TEXT NOT NULL CHECK (BTRIM(nombre_normalizado)<>''),
    id_participante_origen INTEGER REFERENCES participante_importado(id_participante_importado) ON DELETE SET NULL,
    confirmado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (dni_deportista,id_club,nombre_normalizado)
);
CREATE INDEX IF NOT EXISTS idx_variante_nombre_deportista_buscar ON variante_nombre_deportista(nombre_normalizado,id_club);
ALTER TABLE variante_nombre_deportista ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS descarte_nombre_deportista (
    dni_deportista VARCHAR(20) NOT NULL REFERENCES deportista(dni) ON UPDATE CASCADE ON DELETE RESTRICT,
    id_club INTEGER NOT NULL REFERENCES club(id_club) ON UPDATE CASCADE ON DELETE RESTRICT,
    nombre_original TEXT NOT NULL CHECK (BTRIM(nombre_original)<>''),
    nombre_normalizado TEXT NOT NULL CHECK (BTRIM(nombre_normalizado)<>''),
    id_participante_origen INTEGER REFERENCES participante_importado(id_participante_importado) ON DELETE SET NULL,
    confirmado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (dni_deportista,id_club,nombre_normalizado)
);
CREATE INDEX IF NOT EXISTS idx_descarte_nombre_deportista_buscar ON descarte_nombre_deportista(nombre_normalizado,id_club);
ALTER TABLE descarte_nombre_deportista ENABLE ROW LEVEL SECURITY;

COMMIT;
