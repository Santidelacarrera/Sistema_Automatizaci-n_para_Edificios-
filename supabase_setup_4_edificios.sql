-- ==========================================================================
-- ESQUEMA COMPLETO Y DATOS INICIALES PARA 4 EDIFICIOS
-- Generado automáticamente por Antigravity
-- ==========================================================================

-- Limpieza preventiva de esquema previo en Supabase para evitar conflictos:
DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;

BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> f1af332eaa4c

CREATE TABLE accesos_log (
    id SERIAL NOT NULL, 
    edificio_id VARCHAR(40) NOT NULL, 
    token VARCHAR(80) NOT NULL, 
    punto VARCHAR(40) NOT NULL, 
    permitido BOOLEAN NOT NULL, 
    motivo VARCHAR(120) NOT NULL, 
    creado TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    PRIMARY KEY (id)
);

CREATE INDEX ix_accesos_log_edificio_id ON accesos_log (edificio_id);

CREATE TABLE edificios (
    id VARCHAR(40) NOT NULL, 
    nombre VARCHAR(120) NOT NULL, 
    cupos_visitas INTEGER NOT NULL, 
    max_estac_por_unidad INTEGER NOT NULL, 
    tolerancia_visita_min INTEGER NOT NULL, 
    device_api_key VARCHAR(80) NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (device_api_key)
);

CREATE TABLE eventos (
    id SERIAL NOT NULL, 
    edificio_id VARCHAR(40) NOT NULL, 
    tipo VARCHAR(60) NOT NULL, 
    payload JSON NOT NULL, 
    creado TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    PRIMARY KEY (id)
);

CREATE INDEX ix_eventos_edificio_id ON eventos (edificio_id);

CREATE INDEX ix_eventos_tipo ON eventos (tipo);

CREATE TABLE espacios_comunes (
    id SERIAL NOT NULL, 
    edificio_id VARCHAR(40) NOT NULL, 
    nombre VARCHAR(60) NOT NULL, 
    accion VARCHAR(60) NOT NULL, 
    tarifa NUMERIC(12, 2) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(edificio_id) REFERENCES edificios (id)
);

CREATE INDEX ix_espacios_comunes_edificio_id ON espacios_comunes (edificio_id);

CREATE TABLE reglas (
    id SERIAL NOT NULL, 
    edificio_id VARCHAR(40) NOT NULL, 
    accion VARCHAR(60) NOT NULL, 
    tipo VARCHAR(40) NOT NULL, 
    params JSON NOT NULL, 
    activa BOOLEAN NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(edificio_id) REFERENCES edificios (id)
);

CREATE INDEX ix_reglas_edificio_id ON reglas (edificio_id);

CREATE TABLE unidades (
    id SERIAL NOT NULL, 
    edificio_id VARCHAR(40) NOT NULL, 
    numero VARCHAR(20) NOT NULL, 
    coeficiente NUMERIC(9, 6) NOT NULL, 
    codigo_cobro VARCHAR(30) NOT NULL, 
    estacionamientos INTEGER NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(edificio_id) REFERENCES edificios (id), 
    UNIQUE (codigo_cobro), 
    UNIQUE (edificio_id, numero)
);

CREATE INDEX ix_unidades_edificio_id ON unidades (edificio_id);

CREATE TABLE cargos (
    id SERIAL NOT NULL, 
    edificio_id VARCHAR(40) NOT NULL, 
    unidad_id INTEGER NOT NULL, 
    periodo VARCHAR(7) NOT NULL, 
    concepto VARCHAR(80) NOT NULL, 
    monto NUMERIC(14, 2) NOT NULL, 
    saldo NUMERIC(14, 2) NOT NULL, 
    vencimiento DATE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(edificio_id) REFERENCES edificios (id), 
    FOREIGN KEY(unidad_id) REFERENCES unidades (id)
);

CREATE INDEX ix_cargos_edificio_id ON cargos (edificio_id);

CREATE INDEX ix_cargos_unidad_id ON cargos (unidad_id);

CREATE TABLE lecturas_medidor (
    id SERIAL NOT NULL, 
    edificio_id VARCHAR(40) NOT NULL, 
    unidad_id INTEGER NOT NULL, 
    periodo VARCHAR(7) NOT NULL, 
    servicio VARCHAR(20) NOT NULL, 
    consumo NUMERIC(14, 3) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(edificio_id) REFERENCES edificios (id), 
    FOREIGN KEY(unidad_id) REFERENCES unidades (id), 
    UNIQUE (unidad_id, periodo, servicio)
);

CREATE INDEX ix_lecturas_medidor_edificio_id ON lecturas_medidor (edificio_id);

CREATE TABLE pagos (
    id SERIAL NOT NULL, 
    edificio_id VARCHAR(40) NOT NULL, 
    unidad_id INTEGER, 
    monto NUMERIC(14, 2) NOT NULL, 
    fecha DATE NOT NULL, 
    referencia VARCHAR(200) NOT NULL, 
    ref_banco VARCHAR(80) NOT NULL, 
    conciliado BOOLEAN NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(edificio_id) REFERENCES edificios (id), 
    FOREIGN KEY(unidad_id) REFERENCES unidades (id), 
    UNIQUE (edificio_id, ref_banco)
);

CREATE INDEX ix_pagos_edificio_id ON pagos (edificio_id);

CREATE TABLE reservas_espacio (
    id SERIAL NOT NULL, 
    edificio_id VARCHAR(40) NOT NULL, 
    espacio_id INTEGER NOT NULL, 
    unidad_id INTEGER NOT NULL, 
    desde TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    hasta TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    estado VARCHAR(20) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(edificio_id) REFERENCES edificios (id), 
    FOREIGN KEY(espacio_id) REFERENCES espacios_comunes (id), 
    FOREIGN KEY(unidad_id) REFERENCES unidades (id)
);

CREATE INDEX ix_reservas_espacio_edificio_id ON reservas_espacio (edificio_id);

CREATE TYPE rol AS ENUM ('superadmin', 'admin', 'residente', 'conserje');

CREATE TABLE residentes (
    id SERIAL NOT NULL, 
    edificio_id VARCHAR(40) NOT NULL, 
    unidad_id INTEGER NOT NULL, 
    nombre VARCHAR(120) NOT NULL, 
    rut VARCHAR(15) NOT NULL, 
    email VARCHAR(160) NOT NULL, 
    telefono VARCHAR(20) NOT NULL, 
    password_hash VARCHAR(200) NOT NULL, 
    rol rol NOT NULL, 
    activo BOOLEAN NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(edificio_id) REFERENCES edificios (id), 
    FOREIGN KEY(unidad_id) REFERENCES unidades (id)
);

CREATE INDEX ix_residentes_edificio_id ON residentes (edificio_id);

CREATE INDEX ix_residentes_rut ON residentes (rut);

CREATE INDEX ix_residentes_telefono ON residentes (telefono);

CREATE TYPE estadovisita AS ENUM ('reservada', 'llego', 'no_show', 'cancelada');

CREATE TABLE visitas (
    id SERIAL NOT NULL, 
    edificio_id VARCHAR(40) NOT NULL, 
    unidad_id INTEGER NOT NULL, 
    nombre_visita VARCHAR(120) NOT NULL, 
    patente VARCHAR(12) NOT NULL, 
    usa_estacionamiento BOOLEAN NOT NULL, 
    desde TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    hasta TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    codigo_qr VARCHAR(64) NOT NULL, 
    usos_max INTEGER NOT NULL, 
    usos INTEGER NOT NULL, 
    estado estadovisita NOT NULL, 
    llegada_at TIMESTAMP WITHOUT TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(edificio_id) REFERENCES edificios (id), 
    FOREIGN KEY(unidad_id) REFERENCES unidades (id), 
    UNIQUE (codigo_qr)
);

CREATE INDEX ix_visitas_edificio_id ON visitas (edificio_id);

CREATE INDEX ix_visitas_ventana ON visitas (edificio_id, desde, hasta);

CREATE TYPE tipotag AS ENUM ('vehicular', 'peatonal');

CREATE TABLE tags (
    id SERIAL NOT NULL, 
    edificio_id VARCHAR(40) NOT NULL, 
    unidad_id INTEGER NOT NULL, 
    residente_id INTEGER, 
    uid VARCHAR(40) NOT NULL, 
    tipo tipotag NOT NULL, 
    activo BOOLEAN NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(edificio_id) REFERENCES edificios (id), 
    FOREIGN KEY(residente_id) REFERENCES residentes (id), 
    FOREIGN KEY(unidad_id) REFERENCES unidades (id), 
    UNIQUE (edificio_id, uid)
);

CREATE INDEX ix_tags_edificio_id ON tags (edificio_id);

CREATE TABLE vehiculos (
    id SERIAL NOT NULL, 
    edificio_id VARCHAR(40) NOT NULL, 
    unidad_id INTEGER NOT NULL, 
    patente VARCHAR(10) NOT NULL, 
    descripcion VARCHAR(80) NOT NULL, 
    tag_id INTEGER, 
    activo BOOLEAN NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(edificio_id) REFERENCES edificios (id), 
    FOREIGN KEY(tag_id) REFERENCES tags (id), 
    FOREIGN KEY(unidad_id) REFERENCES unidades (id), 
    UNIQUE (edificio_id, patente)
);

CREATE INDEX ix_vehiculos_edificio_id ON vehiculos (edificio_id);

CREATE INDEX ix_vehiculos_unidad_id ON vehiculos (unidad_id);

INSERT INTO alembic_version (version_num) VALUES ('f1af332eaa4c') RETURNING alembic_version.version_num;

-- Running upgrade f1af332eaa4c -> 0002_stickers

ALTER TABLE tags ADD COLUMN estado VARCHAR(12) DEFAULT 'activo' NOT NULL;

ALTER TABLE tags ADD COLUMN formato VARCHAR(12) DEFAULT 'epc' NOT NULL;

ALTER TABLE tags ADD COLUMN fecha_alta TIMESTAMP WITHOUT TIME ZONE;

ALTER TABLE tags ADD COLUMN ultima_lectura TIMESTAMP WITHOUT TIME ZONE;

UPDATE tags SET estado = 'bloqueado' WHERE activo = false;

UPDATE tags SET fecha_alta = CURRENT_TIMESTAMP WHERE fecha_alta IS NULL;

ALTER TABLE tags ALTER COLUMN fecha_alta SET NOT NULL;

ALTER TABLE tags DROP COLUMN activo;

ALTER TABLE edificios ADD COLUMN modo_acceso VARCHAR(30) DEFAULT 'sticker_o_patente' NOT NULL;

ALTER TABLE edificios ADD COLUMN ventana_coincidencia_s INTEGER DEFAULT '10' NOT NULL;

ALTER TABLE edificios ADD COLUMN antirrebote_s INTEGER DEFAULT '3' NOT NULL;

ALTER TABLE edificios ADD COLUMN anti_passback BOOLEAN DEFAULT false NOT NULL;

ALTER TABLE edificios ADD COLUMN umbral_confianza_patente FLOAT DEFAULT '0.85' NOT NULL;

ALTER TABLE vehiculos ADD COLUMN adentro BOOLEAN DEFAULT false NOT NULL;

ALTER TABLE accesos_log ADD COLUMN fuente VARCHAR(12) DEFAULT '' NOT NULL;

ALTER TABLE accesos_log ALTER COLUMN motivo TYPE VARCHAR(160);

CREATE TABLE lecturas_pendientes (
    id SERIAL NOT NULL, 
    edificio_id VARCHAR(40) NOT NULL, 
    punto VARCHAR(40) NOT NULL, 
    fuente VARCHAR(12) NOT NULL, 
    valor VARCHAR(80) NOT NULL, 
    vehiculo_id INTEGER, 
    creado TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(vehiculo_id) REFERENCES vehiculos (id)
);

CREATE INDEX ix_lecturas_pendientes_edificio_id ON lecturas_pendientes (edificio_id);

UPDATE alembic_version SET version_num='0002_stickers' WHERE alembic_version.version_num = 'f1af332eaa4c';

-- Running upgrade 0002_stickers -> 0003_intentos_login

CREATE TABLE intentos_login (
    id SERIAL NOT NULL, 
    clave VARCHAR(220) NOT NULL, 
    ip VARCHAR(64) DEFAULT '' NOT NULL, 
    exitoso BOOLEAN DEFAULT false NOT NULL, 
    creado TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    PRIMARY KEY (id)
);

CREATE INDEX ix_intentos_login_clave ON intentos_login (clave);

CREATE INDEX ix_intentos_login_ip ON intentos_login (ip);

CREATE INDEX ix_intentos_login_creado ON intentos_login (creado);

UPDATE alembic_version SET version_num='0003_intentos_login' WHERE alembic_version.version_num = '0002_stickers';

-- Running upgrade 0003_intentos_login -> 0004_clave_dispositivo_hash

UPDATE alembic_version SET version_num='0004_clave_dispositivo_hash' WHERE alembic_version.version_num = '0003_intentos_login';

-- Running upgrade 0004_clave_dispositivo_hash -> 0005_conversaciones_wa

CREATE TABLE conversaciones_wa (
    id SERIAL NOT NULL, 
    telefono VARCHAR(20) NOT NULL, 
    estado VARCHAR(20) NOT NULL, 
    datos JSON NOT NULL, 
    actualizado TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (telefono)
);

CREATE TABLE mensajes_wa (
    id SERIAL NOT NULL, 
    msg_id VARCHAR(120) NOT NULL, 
    creado TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (msg_id)
);

CREATE INDEX ix_mensajes_wa_creado ON mensajes_wa (creado);

UPDATE alembic_version SET version_num='0005_conversaciones_wa' WHERE alembic_version.version_num = '0004_clave_dispositivo_hash';

COMMIT;


-- ==========================================================================
-- SEMILLA DE 4 EDIFICIOS CON DEPARTAMENTOS Y ADMINISTRADORES
-- ==========================================================================

BEGIN;

-- Edificio: Torre A (Norte) (edificio_1)
INSERT INTO edificios (id, nombre, cupos_visitas, max_estac_por_unidad, tolerancia_visita_min, device_api_key, modo_acceso, ventana_coincidencia_s, antirrebote_s, anti_passback, umbral_confianza_patente) VALUES ('edificio_1', 'Torre A (Norte)', 6, 2, 20, '6618ae69dbf8b4dfeecaf632ae9c0e8bbeeb5e25c77443d9fee98109eb5835b5', 'sticker_o_patente', 10, 3, false, 0.85);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_1', '101', 0.125, 'CC-EDIFICIO_1-101', 1);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_1', '102', 0.125, 'CC-EDIFICIO_1-102', 1);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_1', '103', 0.125, 'CC-EDIFICIO_1-103', 1);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_1', '104', 0.125, 'CC-EDIFICIO_1-104', 1);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_1', '201', 0.125, 'CC-EDIFICIO_1-201', 1);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_1', '202', 0.125, 'CC-EDIFICIO_1-202', 1);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_1', '203', 0.125, 'CC-EDIFICIO_1-203', 1);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_1', '204', 0.125, 'CC-EDIFICIO_1-204', 1);
INSERT INTO residentes (edificio_id, unidad_id, nombre, rut, email, telefono, password_hash, rol, activo) SELECT 'edificio_1', id, 'Administrador Torre A', '11111111-1', 'admin.torrea@edificios.cl', '56911112222', '9d1abb8427b3582d9d9388de641b1b21$c7740de3da1c2b5b5febda6d2ae0805dab22a006a7fe3415e16a6580fdd3e968bbfe2b64048b0711e8483cd6f0f17ade8dae158536a186b79576a5f5c3aa4985', 'admin', true FROM unidades WHERE edificio_id = 'edificio_1' AND numero = '101';

-- Edificio: Torre B (Sur) (edificio_2)
INSERT INTO edificios (id, nombre, cupos_visitas, max_estac_por_unidad, tolerancia_visita_min, device_api_key, modo_acceso, ventana_coincidencia_s, antirrebote_s, anti_passback, umbral_confianza_patente) VALUES ('edificio_2', 'Torre B (Sur)', 6, 2, 20, '0d36bb20066f9db5a8222c5e4ff2ae5df83f3d51950deb1d58f3c58d3a6cd045', 'sticker_o_patente', 10, 3, false, 0.85);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_2', '101', 0.125, 'CC-EDIFICIO_2-101', 1);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_2', '102', 0.125, 'CC-EDIFICIO_2-102', 1);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_2', '103', 0.125, 'CC-EDIFICIO_2-103', 1);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_2', '104', 0.125, 'CC-EDIFICIO_2-104', 1);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_2', '201', 0.125, 'CC-EDIFICIO_2-201', 1);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_2', '202', 0.125, 'CC-EDIFICIO_2-202', 1);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_2', '203', 0.125, 'CC-EDIFICIO_2-203', 1);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_2', '204', 0.125, 'CC-EDIFICIO_2-204', 1);
INSERT INTO residentes (edificio_id, unidad_id, nombre, rut, email, telefono, password_hash, rol, activo) SELECT 'edificio_2', id, 'Administrador Torre B', '22222222-2', 'admin.torreb@edificios.cl', '56911112222', '9d1abb8427b3582d9d9388de641b1b21$c7740de3da1c2b5b5febda6d2ae0805dab22a006a7fe3415e16a6580fdd3e968bbfe2b64048b0711e8483cd6f0f17ade8dae158536a186b79576a5f5c3aa4985', 'admin', true FROM unidades WHERE edificio_id = 'edificio_2' AND numero = '101';

-- Edificio: Torre C (Oriente) (edificio_3)
INSERT INTO edificios (id, nombre, cupos_visitas, max_estac_por_unidad, tolerancia_visita_min, device_api_key, modo_acceso, ventana_coincidencia_s, antirrebote_s, anti_passback, umbral_confianza_patente) VALUES ('edificio_3', 'Torre C (Oriente)', 6, 2, 20, '139ebab802a7736574b9e251e4b1dd58b97d599e1bec7c180b5e264922449748', 'sticker_o_patente', 10, 3, false, 0.85);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_3', '101', 0.125, 'CC-EDIFICIO_3-101', 1);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_3', '102', 0.125, 'CC-EDIFICIO_3-102', 1);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_3', '103', 0.125, 'CC-EDIFICIO_3-103', 1);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_3', '104', 0.125, 'CC-EDIFICIO_3-104', 1);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_3', '201', 0.125, 'CC-EDIFICIO_3-201', 1);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_3', '202', 0.125, 'CC-EDIFICIO_3-202', 1);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_3', '203', 0.125, 'CC-EDIFICIO_3-203', 1);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_3', '204', 0.125, 'CC-EDIFICIO_3-204', 1);
INSERT INTO residentes (edificio_id, unidad_id, nombre, rut, email, telefono, password_hash, rol, activo) SELECT 'edificio_3', id, 'Administrador Torre C', '33333333-3', 'admin.torrec@edificios.cl', '56911112222', '9d1abb8427b3582d9d9388de641b1b21$c7740de3da1c2b5b5febda6d2ae0805dab22a006a7fe3415e16a6580fdd3e968bbfe2b64048b0711e8483cd6f0f17ade8dae158536a186b79576a5f5c3aa4985', 'admin', true FROM unidades WHERE edificio_id = 'edificio_3' AND numero = '101';

-- Edificio: Torre D (Poniente) (edificio_4)
INSERT INTO edificios (id, nombre, cupos_visitas, max_estac_por_unidad, tolerancia_visita_min, device_api_key, modo_acceso, ventana_coincidencia_s, antirrebote_s, anti_passback, umbral_confianza_patente) VALUES ('edificio_4', 'Torre D (Poniente)', 6, 2, 20, '38cd024fb4591442d377994e562d967311617ee77df9393d35eef6f098b25367', 'sticker_o_patente', 10, 3, false, 0.85);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_4', '101', 0.125, 'CC-EDIFICIO_4-101', 1);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_4', '102', 0.125, 'CC-EDIFICIO_4-102', 1);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_4', '103', 0.125, 'CC-EDIFICIO_4-103', 1);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_4', '104', 0.125, 'CC-EDIFICIO_4-104', 1);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_4', '201', 0.125, 'CC-EDIFICIO_4-201', 1);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_4', '202', 0.125, 'CC-EDIFICIO_4-202', 1);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_4', '203', 0.125, 'CC-EDIFICIO_4-203', 1);
INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) VALUES ('edificio_4', '204', 0.125, 'CC-EDIFICIO_4-204', 1);
INSERT INTO residentes (edificio_id, unidad_id, nombre, rut, email, telefono, password_hash, rol, activo) SELECT 'edificio_4', id, 'Administrador Torre D', '44444444-4', 'admin.torred@edificios.cl', '56911112222', '9d1abb8427b3582d9d9388de641b1b21$c7740de3da1c2b5b5febda6d2ae0805dab22a006a7fe3415e16a6580fdd3e968bbfe2b64048b0711e8483cd6f0f17ade8dae158536a186b79576a5f5c3aa4985', 'admin', true FROM unidades WHERE edificio_id = 'edificio_4' AND numero = '101';

-- Superadministrador Global (ve y gestiona los 4 edificios)
INSERT INTO residentes (edificio_id, unidad_id, nombre, rut, email, telefono, password_hash, rol, activo) SELECT 'edificio_1', id, 'Superadministrador General', '99999999-9', 'superadmin@edificios.cl', '56999999999', '9d1abb8427b3582d9d9388de641b1b21$c7740de3da1c2b5b5febda6d2ae0805dab22a006a7fe3415e16a6580fdd3e968bbfe2b64048b0711e8483cd6f0f17ade8dae158536a186b79576a5f5c3aa4985', 'superadmin', true FROM unidades WHERE edificio_id = 'edificio_1' AND numero = '101';

COMMIT;
