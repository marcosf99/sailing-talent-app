BEGIN;

-- Registro de cada unión confirmada. Los documentos originales y las copias
-- anteriores se conservan aunque posteriormente cambie el DNI de la ficha.
CREATE TABLE IF NOT EXISTS fusion_deportista (
    id_fusion INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    documento_origen VARCHAR(20) NOT NULL,
    documento_conservado VARCHAR(20) NOT NULL,
    dni_deportista VARCHAR(20) REFERENCES deportista(dni)
        ON UPDATE CASCADE ON DELETE SET NULL,
    motivo TEXT NOT NULL CHECK (BTRIM(motivo) <> ''),
    datos_antes JSONB NOT NULL,
    ficha_despues JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fusion_deportista_destino ON fusion_deportista(dni_deportista);
ALTER TABLE fusion_deportista ENABLE ROW LEVEL SECURITY;

COMMIT;
