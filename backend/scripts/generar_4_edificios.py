"""Genera el SQL completo de inicialización con esquema real + 4 edificios preconfigurados."""
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.security import hash_clave_dispositivo, hash_password

PW_DEFAULT = "Admin2026!"

EDIFICIOS = [
    {
        "id": "edificio_1",
        "nombre": "Torre A (Norte)",
        "admin_nombre": "Administrador Torre A",
        "admin_rut": "11111111-1",
        "admin_email": "admin.torrea@edificios.cl",
        "device_key": "DEVKEY_TORRE_A_" + secrets.token_hex(16),
    },
    {
        "id": "edificio_2",
        "nombre": "Torre B (Sur)",
        "admin_nombre": "Administrador Torre B",
        "admin_rut": "22222222-2",
        "admin_email": "admin.torreb@edificios.cl",
        "device_key": "DEVKEY_TORRE_B_" + secrets.token_hex(16),
    },
    {
        "id": "edificio_3",
        "nombre": "Torre C (Oriente)",
        "admin_nombre": "Administrador Torre C",
        "admin_rut": "33333333-3",
        "admin_email": "admin.torrec@edificios.cl",
        "device_key": "DEVKEY_TORRE_C_" + secrets.token_hex(16),
    },
    {
        "id": "edificio_4",
        "nombre": "Torre D (Poniente)",
        "admin_nombre": "Administrador Torre D",
        "admin_rut": "44444444-4",
        "admin_email": "admin.torred@edificios.cl",
        "device_key": "DEVKEY_TORRE_D_" + secrets.token_hex(16),
    },
]

DEPARTAMENTOS = ["101", "102", "103", "104", "201", "202", "203", "204"]
COEF = round(1.0 / len(DEPARTAMENTOS), 6)


def main():
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    schema_path = os.path.join(raiz, "supabase_schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    lines = []
    lines.append("-- ==========================================================================")
    lines.append("-- ESQUEMA COMPLETO Y DATOS INICIALES PARA 4 EDIFICIOS")
    lines.append("-- Generado automáticamente por Antigravity")
    lines.append("-- ==========================================================================\n")
    lines.append("-- Limpieza preventiva de esquema previo en Supabase para evitar conflictos:")
    lines.append("DROP SCHEMA IF EXISTS public CASCADE;")
    lines.append("CREATE SCHEMA public;\n")
    lines.append(schema_sql.strip())
    lines.append("\n\n-- ==========================================================================")
    lines.append("-- SEMILLA DE 4 EDIFICIOS CON DEPARTAMENTOS Y ADMINISTRADORES")
    lines.append("-- ==========================================================================\n")
    lines.append("BEGIN;\n")

    pw_hash = hash_password(PW_DEFAULT)

    for ed in EDIFICIOS:
        eid = ed["id"]
        dev_hash = hash_clave_dispositivo(ed["device_key"])
        lines.append(f"-- Edificio: {ed['nombre']} ({eid})")
        lines.append(
            f"INSERT INTO edificios (id, nombre, cupos_visitas, max_estac_por_unidad, tolerancia_visita_min, "
            f"device_api_key, modo_acceso, ventana_coincidencia_s, antirrebote_s, anti_passback, umbral_confianza_patente) "
            f"VALUES ('{eid}', '{ed['nombre']}', 6, 2, 20, '{dev_hash}', 'sticker_o_patente', 10, 3, false, 0.85);"
        )

        # Departamentos
        for dep in DEPARTAMENTOS:
            codigo = f"CC-{eid.upper()}-{dep}"
            lines.append(
                f"INSERT INTO unidades (edificio_id, numero, coeficiente, codigo_cobro, estacionamientos) "
                f"VALUES ('{eid}', '{dep}', {COEF}, '{codigo}', 1);"
            )

        # Administrador del edificio (asociado a la unidad 101)
        lines.append(
            f"INSERT INTO residentes (edificio_id, unidad_id, nombre, rut, email, telefono, password_hash, rol, activo) "
            f"SELECT '{eid}', id, '{ed['admin_nombre']}', '{ed['admin_rut']}', '{ed['admin_email']}', '56911112222', "
            f"'{pw_hash}', 'admin', true FROM unidades WHERE edificio_id = '{eid}' AND numero = '101';\n"
        )

    # Superadmin general del sistema (asignado a edificio_1, unidad 101)
    lines.append("-- Superadministrador Global (ve y gestiona los 4 edificios)")
    lines.append(
        f"INSERT INTO residentes (edificio_id, unidad_id, nombre, rut, email, telefono, password_hash, rol, activo) "
        f"SELECT 'edificio_1', id, 'Superadministrador General', '99999999-9', 'superadmin@edificios.cl', '56999999999', "
        f"'{pw_hash}', 'superadmin', true FROM unidades WHERE edificio_id = 'edificio_1' AND numero = '101';\n"
    )

    lines.append("COMMIT;\n")

    out_file = os.path.join(raiz, "supabase_setup_4_edificios.sql")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"SQL generado exitosamente en: {out_file}")
    print("\nRESUMEN DE CREDENCIALES CONFIGURADAS:")
    print("------------------------------------------------------------------------")
    print(f"Contraseña común para todos los usuarios creados: {PW_DEFAULT}")
    print("\nSuperadmin Global:")
    print("  Email: superadmin@edificios.cl")
    print("  Edificio: edificio_1")
    print("  Rol: superadmin (acceso a todos los edificios)")
    print("\nAdministradores por edificio:")
    for ed in EDIFICIOS:
        print(f"  [{ed['nombre']}]:")
        print(f"    Edificio ID: {ed['id']}")
        print(f"    Email: {ed['admin_email']}")
        print(f"    X-Device-Key (para ESP32): {ed['device_key']}")
    print("------------------------------------------------------------------------")


if __name__ == "__main__":
    main()
