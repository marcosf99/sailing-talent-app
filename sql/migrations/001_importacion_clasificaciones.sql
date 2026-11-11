-- Migracion 001: importacion y revision de clasificaciones.
-- PostgreSQL: compatible con Supabase y Google Cloud SQL.
-- Ejecutar UNA VEZ en una base que ya tenga las 11 tablas originales.
-- No borra ni inserta datos. No ejecutar create_tables.sql en esa base.
-- Si falla una sentencia, se revierte la transaccion completa.

BEGIN;

SET LOCAL search_path TO public, pg_catalog;

-- ============================================================
-- IMPORTACION Y REVISION DE CLASIFICACIONES
-- Cinco tablas nuevas. Sin datos de ejemplo.
-- ============================================================

-- Permite exigir que la competicion confirmada pertenezca a la clase
-- elegida en la importacion. No cambia las filas de competicion.
ALTER TABLE competicion
    ADD CONSTRAINT uq_competicion_id_clase
    UNIQUE (id_competicion, id_clase);

-- ============================================================
-- 12. IMPORTACION_CLASIFICACION
-- Una importacion corresponde a una clase y a una version de la fuente.
-- Los datos de competicion pueden completarse durante la revision.
-- ============================================================
CREATE TABLE importacion_clasificacion (
    id_importacion INTEGER GENERATED ALWAYS AS IDENTITY,
    tipo_fuente VARCHAR(10) NOT NULL,
    nombre_archivo TEXT,
    url_origen TEXT,
    referencia_documento TEXT NOT NULL,
    huella_documento VARCHAR(64) NOT NULL,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    estado VARCHAR(30) NOT NULL DEFAULT 'recibida',
    nombre_competicion_propuesto VARCHAR(200),
    fecha_inicio_propuesta DATE,
    fecha_fin_propuesta DATE,
    localidad_propuesta VARCHAR(100),
    nivel VARCHAR(30),
    id_clase INTEGER NOT NULL,
    tipo_clasificacion VARCHAR(20) NOT NULL DEFAULT 'sin_confirmar',
    fecha_actualizacion_fuente TIMESTAMPTZ,
    mapeo_columnas JSONB NOT NULL DEFAULT '{}'::JSONB,
    criterio_inclusion JSONB,
    observaciones TEXT,
    id_competicion INTEGER,

    CONSTRAINT pk_importacion_clasificacion PRIMARY KEY (id_importacion),
    -- Clave de apoyo para que las filas confirmen resultados de esta
    -- misma competicion, nunca de una competicion diferente.
    CONSTRAINT uq_importacion_competicion
        UNIQUE (id_importacion, id_competicion),
    CONSTRAINT fk_importacion_clase
        FOREIGN KEY (id_clase) REFERENCES clase(id_clase)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_importacion_competicion_clase
        FOREIGN KEY (id_competicion, id_clase)
        REFERENCES competicion(id_competicion, id_clase)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT chk_importacion_tipo_fuente
        CHECK (tipo_fuente IN ('pdf', 'enlace')),
    CONSTRAINT chk_importacion_fuente
        CHECK (
            (tipo_fuente = 'pdf' AND NULLIF(BTRIM(nombre_archivo), '') IS NOT NULL)
            OR (tipo_fuente = 'enlace' AND NULLIF(BTRIM(url_origen), '') IS NOT NULL)
        ),
    CONSTRAINT chk_importacion_documento
        CHECK (BTRIM(referencia_documento) <> ''),
    CONSTRAINT chk_importacion_huella
        CHECK (huella_documento ~ '^[0-9a-f]{64}$'),
    CONSTRAINT chk_importacion_estado
        CHECK (estado IN (
            'recibida', 'extraida', 'en_revision', 'parcialmente_importada',
            'completada', 'error', 'cancelada'
        )),
    CONSTRAINT chk_importacion_nivel
        CHECK (nivel IN ('Autonomico', 'Nacional', 'Internacional')),
    CONSTRAINT chk_importacion_tipo_clasificacion
        CHECK (tipo_clasificacion IN ('provisional', 'definitiva', 'sin_confirmar')),
    CONSTRAINT chk_importacion_fechas
        CHECK (fecha_fin_propuesta >= fecha_inicio_propuesta),
    CONSTRAINT chk_importacion_mapeo
        CHECK (JSONB_TYPEOF(mapeo_columnas) = 'object'),
    CONSTRAINT chk_importacion_criterio
        CHECK (JSONB_TYPEOF(criterio_inclusion) = 'object'),
    CONSTRAINT chk_importacion_confirmacion
        CHECK (
            estado NOT IN ('parcialmente_importada', 'completada')
            OR (id_competicion IS NOT NULL AND nivel IS NOT NULL
                AND criterio_inclusion IS NOT NULL)
        )
);

COMMENT ON COLUMN importacion_clasificacion.huella_documento IS
    'SHA-256 en hexadecimal minusculo de la copia de la fuente. No es unica: un documento puede contener varias clases.';
COMMENT ON COLUMN importacion_clasificacion.criterio_inclusion IS
    'Instantanea JSON del criterio confirmado: Autonomico <=40, Nacional <=80 o Internacional con ESP en numero de vela; incluye empates en el corte.';

-- actualizado_en cambia automaticamente cuando se modifica la importacion.
CREATE FUNCTION actualizar_fecha_importacion_clasificacion()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.actualizado_en := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_importacion_actualizado_en
    BEFORE UPDATE ON importacion_clasificacion
    FOR EACH ROW
    EXECUTE FUNCTION actualizar_fecha_importacion_clasificacion();

-- ============================================================
-- 13. FILA_CLASIFICACION_IMPORTADA
-- Una fila representa una unidad de la clasificacion original.
-- Las posiciones NO son unicas: se conservan los empates oficiales.
-- ============================================================
CREATE TABLE fila_clasificacion_importada (
    id_fila INTEGER GENERATED ALWAYS AS IDENTITY,
    id_importacion INTEGER NOT NULL,
    numero_fila INTEGER NOT NULL,
    pagina_origen INTEGER,
    datos_originales JSONB NOT NULL,
    numero_vela_original VARCHAR(100),
    codigo_pais_vela VARCHAR(3),
    posicion_general INTEGER,
    puntos NUMERIC(10,2),
    categoria_original VARCHAR(100),
    posicion_categoria INTEGER,
    cumple_criterio BOOLEAN,
    motivo_seleccion TEXT,
    estado VARCHAR(30) NOT NULL DEFAULT 'pendiente',
    incidencias TEXT,
    observaciones_revision TEXT,
    id_unidad_confirmada INTEGER,
    id_competicion_confirmada INTEGER,

    CONSTRAINT pk_fila_clasificacion_importada PRIMARY KEY (id_fila),
    CONSTRAINT uq_fila_importacion_numero UNIQUE (id_importacion, numero_fila),
    CONSTRAINT fk_fila_importacion
        FOREIGN KEY (id_importacion)
        REFERENCES importacion_clasificacion(id_importacion)
        ON UPDATE CASCADE ON DELETE CASCADE,
    -- MATCH FULL exige que ambas columnas sean NULL o ambas tengan valor.
    CONSTRAINT fk_fila_resultado_confirmado
        FOREIGN KEY (id_unidad_confirmada, id_competicion_confirmada)
        REFERENCES participa_en(id_unidad, id_competicion)
        MATCH FULL ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_fila_competicion_importacion
        FOREIGN KEY (id_importacion, id_competicion_confirmada)
        REFERENCES importacion_clasificacion(id_importacion, id_competicion)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT chk_fila_numero CHECK (numero_fila > 0),
    CONSTRAINT chk_fila_pagina CHECK (pagina_origen > 0),
    CONSTRAINT chk_fila_datos CHECK (JSONB_TYPEOF(datos_originales) = 'object'),
    CONSTRAINT chk_fila_pais CHECK (codigo_pais_vela ~ '^[A-Z]{3}$'),
    CONSTRAINT chk_fila_posicion_general CHECK (posicion_general > 0),
    CONSTRAINT chk_fila_posicion_categoria CHECK (posicion_categoria > 0),
    CONSTRAINT chk_fila_puntos CHECK (puntos >= 0),
    CONSTRAINT chk_fila_estado
        CHECK (estado IN (
            'pendiente', 'requiere_correccion', 'lista', 'importada', 'excluida'
        )),
    CONSTRAINT chk_fila_importada
        CHECK (
            estado <> 'importada'
            OR (id_unidad_confirmada IS NOT NULL
                AND id_competicion_confirmada IS NOT NULL
                AND posicion_general IS NOT NULL AND puntos IS NOT NULL
                AND cumple_criterio IS TRUE)
        )
);

COMMENT ON COLUMN fila_clasificacion_importada.cumple_criterio IS
    'NULL: no evaluado; TRUE: seleccionado; FALSE: fuera de criterio. No se selecciona ni se confirma automaticamente por este campo.';
COMMENT ON COLUMN fila_clasificacion_importada.id_competicion_confirmada IS
    'Junto con id_unidad_confirmada identifica el resultado en participa_en; debe pertenecer a la competicion confirmada de la importacion.';

-- ============================================================
-- 14. PARTICIPANTE_IMPORTADO
-- Esta es la lista persistente de participantes pendientes de revision.
-- Cada aparicion en una fila es independiente: no se inventan DNI ni fechas.
-- ============================================================
CREATE TABLE participante_importado (
    id_participante_importado INTEGER GENERATED ALWAYS AS IDENTITY,
    id_fila INTEGER NOT NULL,
    orden_en_tripulacion SMALLINT NOT NULL,
    nombre_original TEXT NOT NULL,
    nombre_propuesto VARCHAR(100),
    apellidos_propuestos VARCHAR(150),
    documento_propuesto VARCHAR(20),
    fecha_nacimiento_propuesta DATE,
    sexo_propuesto VARCHAR(20),
    club_original TEXT,
    federacion_original TEXT,
    id_club_identificado INTEGER,
    rol_propuesto VARCHAR(30),
    estado VARCHAR(30) NOT NULL DEFAULT 'pendiente_revision',
    observaciones_revision TEXT,
    dni_deportista_confirmado VARCHAR(20),
    confirmado_en TIMESTAMPTZ,

    CONSTRAINT pk_participante_importado PRIMARY KEY (id_participante_importado),
    CONSTRAINT uq_participante_fila_orden UNIQUE (id_fila, orden_en_tripulacion),
    CONSTRAINT uq_participante_fila_deportista UNIQUE (id_fila, dni_deportista_confirmado),
    CONSTRAINT fk_participante_fila
        FOREIGN KEY (id_fila) REFERENCES fila_clasificacion_importada(id_fila)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_participante_club
        FOREIGN KEY (id_club_identificado) REFERENCES club(id_club)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_participante_deportista
        FOREIGN KEY (dni_deportista_confirmado) REFERENCES deportista(dni)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT chk_participante_orden CHECK (orden_en_tripulacion > 0),
    CONSTRAINT chk_participante_nombre CHECK (BTRIM(nombre_original) <> ''),
    CONSTRAINT chk_participante_sexo
        CHECK (sexo_propuesto IN ('Masculino', 'Femenino')),
    CONSTRAINT chk_participante_rol
        CHECK (rol_propuesto IN ('Patron', 'Tripulante')),
    CONSTRAINT chk_participante_estado
        CHECK (estado IN (
            'pendiente_revision', 'pendiente_datos', 'vinculado',
            'nuevo_confirmado', 'descartado'
        )),
    CONSTRAINT chk_participante_confirmacion_fecha
        CHECK ((dni_deportista_confirmado IS NULL) = (confirmado_en IS NULL)),
    CONSTRAINT chk_participante_confirmado
        CHECK (
            estado NOT IN ('vinculado', 'nuevo_confirmado')
            OR dni_deportista_confirmado IS NOT NULL
        )
);

COMMENT ON COLUMN participante_importado.id_club_identificado IS
    'Club identificado en la fuente. No actualiza automaticamente el club actual del deportista.';
COMMENT ON COLUMN participante_importado.documento_propuesto IS
    'Dato pendiente de verificar; no crea ni identifica automaticamente un deportista definitivo.';

-- ============================================================
-- 15. COINCIDENCIA_PROPUESTA
-- N:M entre una aparicion importada y sus posibles deportistas.
-- ============================================================
CREATE TABLE coincidencia_propuesta (
    id_participante_importado INTEGER NOT NULL,
    dni_deportista VARCHAR(20) NOT NULL,
    indice_similitud NUMERIC(6,5),
    motivos TEXT,
    estado_revision VARCHAR(20) NOT NULL DEFAULT 'pendiente',
    revisado_en TIMESTAMPTZ,

    CONSTRAINT pk_coincidencia_propuesta
        PRIMARY KEY (id_participante_importado, dni_deportista),
    CONSTRAINT fk_coincidencia_participante
        FOREIGN KEY (id_participante_importado)
        REFERENCES participante_importado(id_participante_importado)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_coincidencia_deportista
        FOREIGN KEY (dni_deportista) REFERENCES deportista(dni)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT chk_coincidencia_indice CHECK (indice_similitud BETWEEN 0 AND 1),
    CONSTRAINT chk_coincidencia_estado
        CHECK (estado_revision IN ('pendiente', 'aceptada', 'rechazada')),
    CONSTRAINT chk_coincidencia_revision
        CHECK (estado_revision = 'pendiente' OR revisado_en IS NOT NULL)
);

COMMENT ON COLUMN coincidencia_propuesta.indice_similitud IS
    'Indice heuristico entre 0 y 1 para ordenar candidatos. No es una probabilidad ni confirma una identidad.';

-- ============================================================
-- 16. ALIAS_CLUB
-- Una abreviatura solo puede identificar un club en el mismo contexto.
-- Para abreviaturas ambiguas se debe especificar el contexto de la fuente.
-- ============================================================
CREATE TABLE alias_club (
    id_alias INTEGER GENERATED ALWAYS AS IDENTITY,
    texto_alias VARCHAR(250) NOT NULL,
    texto_normalizado VARCHAR(250) NOT NULL,
    id_club INTEGER NOT NULL,
    contexto_fuente VARCHAR(250),
    confirmado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_alias_club PRIMARY KEY (id_alias),
    CONSTRAINT fk_alias_club
        FOREIGN KEY (id_club) REFERENCES club(id_club)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT chk_alias_texto CHECK (BTRIM(texto_alias) <> ''),
    CONSTRAINT chk_alias_normalizado
        CHECK (texto_normalizado <> ''
            AND texto_normalizado = LOWER(BTRIM(texto_normalizado)))
);

-- Indices para revisar pendientes y resolver claves foraneas.
CREATE INDEX idx_importacion_competicion_clase
    ON importacion_clasificacion (id_competicion, id_clase);
CREATE INDEX idx_importacion_clase ON importacion_clasificacion (id_clase);
CREATE INDEX idx_importacion_estado ON importacion_clasificacion (estado);
CREATE INDEX idx_fila_importacion_estado
    ON fila_clasificacion_importada (id_importacion, estado);
CREATE INDEX idx_fila_resultado_confirmado
    ON fila_clasificacion_importada (id_unidad_confirmada, id_competicion_confirmada);
CREATE INDEX idx_participante_club ON participante_importado (id_club_identificado);
CREATE INDEX idx_participante_deportista ON participante_importado (dni_deportista_confirmado);
CREATE INDEX idx_participante_estado ON participante_importado (estado);
CREATE INDEX idx_coincidencia_deportista ON coincidencia_propuesta (dni_deportista);
CREATE UNIQUE INDEX uq_coincidencia_aceptada
    ON coincidencia_propuesta (id_participante_importado)
    WHERE estado_revision = 'aceptada';
CREATE INDEX idx_alias_club ON alias_club (id_club);
CREATE UNIQUE INDEX uq_alias_contexto
    ON alias_club (texto_normalizado, LOWER(BTRIM(COALESCE(contexto_fuente, ''))));

-- RLS existe en PostgreSQL tanto en Supabase como en Cloud SQL.
-- Sin politicas, la Data API no da acceso a estos datos de revision.
-- El backend conectado como propietario de las tablas sigue teniendo acceso.
-- Si se usa un usuario SQL distinto, habra que definir sus permisos/politicas.
ALTER TABLE importacion_clasificacion ENABLE ROW LEVEL SECURITY;
ALTER TABLE fila_clasificacion_importada ENABLE ROW LEVEL SECURITY;
ALTER TABLE participante_importado ENABLE ROW LEVEL SECURITY;
ALTER TABLE coincidencia_propuesta ENABLE ROW LEVEL SECURITY;
ALTER TABLE alias_club ENABLE ROW LEVEL SECURITY;

-- La confirmacion del numero de tripulantes, sus fechas de pertenencia,
-- la seleccion ESP/40/80 y la escritura atomica del resultado se aplicaran
-- en el servicio de importacion. Este script crea solo el soporte de datos.

COMMIT;
