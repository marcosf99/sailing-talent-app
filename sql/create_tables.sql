-- ============================================================
-- BASE DE DATOS: Sailing Talent
-- SGBD: PostgreSQL
-- ============================================================


-- ============================================================
-- 1. FEDERACION_AUTONOMICA
-- ============================================================

CREATE TABLE federacion_autonomica (
    id_federacion INTEGER GENERATED ALWAYS AS IDENTITY,
    nombre VARCHAR(150) NOT NULL,
    comunidad_autonoma VARCHAR(100),
    director_tecnico VARCHAR(150),
    direccion VARCHAR(250),
    telefono VARCHAR(20),
    correo_electronico VARCHAR(150),

    CONSTRAINT pk_federacion_autonomica
        PRIMARY KEY (id_federacion),

    CONSTRAINT uq_federacion_nombre
        UNIQUE (nombre)
);


-- ============================================================
-- 2. CLUB
-- ============================================================

CREATE TABLE club (
    id_club INTEGER GENERATED ALWAYS AS IDENTITY,
    nombre VARCHAR(150) NOT NULL,
    director_deportivo VARCHAR(150),
    telefono VARCHAR(20),
    localidad VARCHAR(100),
    provincia VARCHAR(100),
    id_federacion INTEGER NOT NULL,

    CONSTRAINT pk_club
        PRIMARY KEY (id_club),

    CONSTRAINT fk_club_federacion
        FOREIGN KEY (id_federacion)
        REFERENCES federacion_autonomica(id_federacion)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);


-- ============================================================
-- 3. DEPORTISTA
-- ============================================================

CREATE TABLE deportista (
    dni VARCHAR(20) NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    apellidos VARCHAR(150) NOT NULL,
    fecha_nacimiento DATE,
    sexo VARCHAR(20),
    id_club INTEGER,

    CONSTRAINT pk_deportista
        PRIMARY KEY (dni),

    CONSTRAINT chk_deportista_sexo
        CHECK (
            sexo IS NULL
            OR sexo IN ('Masculino', 'Femenino')
        ),

    CONSTRAINT fk_deportista_club
        FOREIGN KEY (id_club)
        REFERENCES club(id_club)
        ON UPDATE CASCADE
        ON DELETE SET NULL
);


-- ============================================================
-- 4. REGISTRO_ANTROPOMETRICO
-- ============================================================

CREATE TABLE registro_antropometrico (
    id_registro INTEGER GENERATED ALWAYS AS IDENTITY,
    fecha DATE NOT NULL,
    altura NUMERIC(5,2),
    peso NUMERIC(5,2),
    envergadura NUMERIC(5,2),
    porcentaje_graso NUMERIC(5,2),
    dni_deportista VARCHAR(20) NOT NULL,

    CONSTRAINT pk_registro_antropometrico
        PRIMARY KEY (id_registro),

    CONSTRAINT fk_registro_deportista
        FOREIGN KEY (dni_deportista)
        REFERENCES deportista(dni)
        ON UPDATE CASCADE
        ON DELETE CASCADE,

    CONSTRAINT chk_altura_positiva
        CHECK (
            altura IS NULL
            OR altura > 0
        ),

    CONSTRAINT chk_peso_positivo
        CHECK (
            peso IS NULL
            OR peso > 0
        ),

    CONSTRAINT chk_envergadura_positiva
        CHECK (
            envergadura IS NULL
            OR envergadura > 0
        ),

    CONSTRAINT chk_porcentaje_graso
        CHECK (
            porcentaje_graso IS NULL
            OR porcentaje_graso BETWEEN 0 AND 100
        )
);


-- ============================================================
-- 5. CLASE
-- ============================================================

CREATE TABLE clase (
    id_clase INTEGER GENERATED ALWAYS AS IDENTITY,
    nombre VARCHAR(100) NOT NULL,
    numero_tripulantes SMALLINT NOT NULL,
    es_olimpica BOOLEAN NOT NULL,

    CONSTRAINT pk_clase
        PRIMARY KEY (id_clase),

    CONSTRAINT uq_clase_nombre
        UNIQUE (nombre),

    CONSTRAINT chk_numero_tripulantes
        CHECK (
            numero_tripulantes > 0
        )
);


-- ============================================================
-- 6. UNIDAD_COMPETITIVA
-- ============================================================

CREATE TABLE unidad_competitiva (
    id_unidad INTEGER GENERATED ALWAYS AS IDENTITY,
    fecha_inicio DATE NOT NULL,
    fecha_fin DATE,
    id_clase INTEGER NOT NULL,

    CONSTRAINT pk_unidad_competitiva
        PRIMARY KEY (id_unidad),

    CONSTRAINT fk_unidad_clase
        FOREIGN KEY (id_clase)
        REFERENCES clase(id_clase)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,

    CONSTRAINT chk_unidad_fechas
        CHECK (
            fecha_fin IS NULL
            OR fecha_fin >= fecha_inicio
        )
);


-- ============================================================
-- 7. FORMA_PARTE
-- Relación N:M entre DEPORTISTA y UNIDAD_COMPETITIVA
-- ============================================================

CREATE TABLE forma_parte (
    dni_deportista VARCHAR(20) NOT NULL,
    id_unidad INTEGER NOT NULL,
    rol VARCHAR(30),

    CONSTRAINT pk_forma_parte
        PRIMARY KEY (dni_deportista, id_unidad),

    CONSTRAINT fk_forma_parte_deportista
        FOREIGN KEY (dni_deportista)
        REFERENCES deportista(dni)
        ON UPDATE CASCADE
        ON DELETE CASCADE,

    CONSTRAINT fk_forma_parte_unidad
        FOREIGN KEY (id_unidad)
        REFERENCES unidad_competitiva(id_unidad)
        ON UPDATE CASCADE
        ON DELETE CASCADE,

    CONSTRAINT chk_forma_parte_rol
        CHECK (
            rol IS NULL
            OR rol IN ('Patron', 'Tripulante')
        )
);


-- ============================================================
-- 8. COMPETICION
-- ============================================================

CREATE TABLE competicion (
    id_competicion INTEGER GENERATED ALWAYS AS IDENTITY,
    nombre VARCHAR(200) NOT NULL,
    fecha_inicio DATE NOT NULL,
    fecha_fin DATE NOT NULL,
    localidad VARCHAR(100),
    nivel VARCHAR(30),
    id_clase INTEGER NOT NULL,

    CONSTRAINT pk_competicion
        PRIMARY KEY (id_competicion),

    CONSTRAINT fk_competicion_clase
        FOREIGN KEY (id_clase)
        REFERENCES clase(id_clase)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,

    CONSTRAINT chk_competicion_fechas
        CHECK (
            fecha_fin >= fecha_inicio
        ),

    CONSTRAINT chk_competicion_nivel
        CHECK (
            nivel IS NULL
            OR nivel IN ('Autonomico', 'Nacional', 'Internacional')
        )
);


-- ============================================================
-- 9. PARTICIPA_EN
-- Relación N:M entre UNIDAD_COMPETITIVA y COMPETICION
-- ============================================================

CREATE TABLE participa_en (
    id_unidad INTEGER NOT NULL,
    id_competicion INTEGER NOT NULL,
    posicion_general INTEGER,
    posicion_categoria INTEGER,
    puntos NUMERIC(10,2),

    CONSTRAINT pk_participa_en
        PRIMARY KEY (id_unidad, id_competicion),

    CONSTRAINT fk_participa_unidad
        FOREIGN KEY (id_unidad)
        REFERENCES unidad_competitiva(id_unidad)
        ON UPDATE CASCADE
        ON DELETE CASCADE,

    CONSTRAINT fk_participa_competicion
        FOREIGN KEY (id_competicion)
        REFERENCES competicion(id_competicion)
        ON UPDATE CASCADE
        ON DELETE CASCADE,

    CONSTRAINT chk_posicion_general
        CHECK (
            posicion_general IS NULL
            OR posicion_general > 0
        ),

    CONSTRAINT chk_posicion_categoria
        CHECK (
            posicion_categoria IS NULL
            OR posicion_categoria > 0
        ),

    CONSTRAINT chk_puntos
        CHECK (
            puntos IS NULL
            OR puntos >= 0
        )
);


-- ============================================================
-- 10. TECNICO
-- ============================================================

CREATE TABLE tecnico (
    dni VARCHAR(20) NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    apellidos VARCHAR(150) NOT NULL,
    titulacion VARCHAR(100),

    CONSTRAINT pk_tecnico
        PRIMARY KEY (dni)
);


-- ============================================================
-- 11. INFORME
-- ============================================================

CREATE TABLE informe (
    id_informe INTEGER GENERATED ALWAYS AS IDENTITY,
    fecha DATE NOT NULL,

    estrategia SMALLINT,
    tactica SMALLINT,
    trimado SMALLINT,
    tecnica SMALLINT,

    fortalezas TEXT,
    debilidades TEXT,
    recomendaciones TEXT,

    dni_deportista VARCHAR(20) NOT NULL,
    dni_tecnico VARCHAR(20) NOT NULL,

    CONSTRAINT pk_informe
        PRIMARY KEY (id_informe),

    CONSTRAINT fk_informe_deportista
        FOREIGN KEY (dni_deportista)
        REFERENCES deportista(dni)
        ON UPDATE CASCADE
        ON DELETE CASCADE,

    CONSTRAINT fk_informe_tecnico
        FOREIGN KEY (dni_tecnico)
        REFERENCES tecnico(dni)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,

    CONSTRAINT chk_informe_estrategia
        CHECK (
            estrategia IS NULL
            OR estrategia BETWEEN 1 AND 5
        ),

    CONSTRAINT chk_informe_tactica
        CHECK (
            tactica IS NULL
            OR tactica BETWEEN 1 AND 5
        ),

    CONSTRAINT chk_informe_trimado
        CHECK (
            trimado IS NULL
            OR trimado BETWEEN 1 AND 5
        ),

    CONSTRAINT chk_informe_tecnica
        CHECK (
            tecnica IS NULL
            OR tecnica BETWEEN 1 AND 5
        )
);