"""E2E reproducible en Windows/Linux con datos desechables y sin servicios externos.

python scripts/e2e_local.py
Levanta únicamente sus procesos, usa puertos 18091/13091 y conserva logs en .artifacts/e2e.
No lee credenciales operativas ni usa la base configurada en .env.
"""
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / ".artifacts" / "e2e"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ART.mkdir(parents=True, exist_ok=True)
    for port in (18091, 13091):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                raise RuntimeError(f"Puerto {port} ocupado. No se modifica ese proceso.")
    run_dir = Path(tempfile.mkdtemp(prefix="edificios-e2e-"))
    env = os.environ.copy()
    env.update(DATABASE_URL=f"sqlite:///{(run_dir / 'e2e.db').as_posix()}", ENTORNO="desarrollo",
               **{"JWT_SECRET": secrets.token_urlsafe(48)}, CELERY_EAGER="true", MFA_REQUIRED_PRIVILEGED="false",
               EVOLUTION_URL="", EVOLUTION_APIKEY="", EVOLUTION_INSTANCE="", SMTP_HOST="", SMTP_PASSWORD="",
               ANTHROPIC_API_KEY="", DOCMIND_URL="", DOCMIND_TENANTS="{}", MFA_ENCRYPTION_KEY="",
               E2E_API="http://localhost:18091", NEXT_PUBLIC_API_URL="http://localhost:18091",
               E2E_EDIFICIO="e2e_a", E2E_EMAIL="admin@e2e.cl", E2E_PASSWORD=secrets.token_urlsafe(20),
               E2E_DEVICE_KEY=secrets.token_urlsafe(32), CORS_ORIGINS="http://localhost:13091",
               PW_BASE_URL="http://localhost:13091", NEXT_TELEMETRY_DISABLED="1")
    chrome = Path("C:/Program Files/Google/Chrome/Application/chrome.exe")
    if chrome.exists():
        env["PW_CHROMIUM"] = str(chrome)
    backend, frontend = ROOT / "backend", ROOT / "frontend"
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    def run(args, cwd, name):
        with (ART / f"{name}.log").open("w", encoding="utf-8") as log:
            result = subprocess.run(args, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, **flags)
        print(f"{name}: salida {result.returncode}", flush=True)
        if result.returncode:
            print((ART / f"{name}.log").read_text(encoding="utf-8", errors="replace")[-8000:], flush=True)
            raise RuntimeError(f"Falló {name}; vea .artifacts/e2e/{name}.log")
    run([sys.executable, "-m", "alembic", "upgrade", "head"], backend, "migraciones")
    run([sys.executable, "-c", '''
import os
from app.db import SessionLocal
from app.models import Edificio, Unidad, Residente, Rol, EspacioComun, Regla
from app.security import hash_password, hash_clave_dispositivo
with SessionLocal() as db:
    for eid in ('e2e_a', 'e2e_b'):
        db.add(Edificio(id=eid, nombre='Comunidad de prueba ' + eid, device_api_key=hash_clave_dispositivo(os.environ['E2E_DEVICE_KEY'] if eid == 'e2e_a' else 'clave-otro-edificio')))
        db.flush()
        for num in ('101', '102', '103', '201', '202', '203'):
            db.add(Unidad(edificio_id=eid, numero=num, coeficiente=1/6, codigo_cobro='CC-' + eid.replace('_', '').upper() + '-' + num, estacionamientos=2))
    db.flush()
    u = db.query(Unidad).filter_by(edificio_id='e2e_a', numero='101').one()
    u2 = db.query(Unidad).filter_by(edificio_id='e2e_a', numero='102').one()
    for email, rol, unidad, nombre, rut in [('admin@e2e.cl', Rol.admin, u.id, 'Admin E2E', '11111111-1'), ('residente@e2e.cl', Rol.residente, u2.id, 'Residente E2E', '12345678-5'), ('conserje@e2e.cl', Rol.conserje, u.id, 'Conserje E2E', '33333333-3'), ('saas@e2e.cl', Rol.superadmin, u.id, 'Operador SaaS E2E', '22222222-2')]:
        db.add(Residente(edificio_id='e2e_a', unidad_id=unidad, nombre=nombre, rut=rut, email=email, rol=rol, password_hash=hash_password(os.environ['E2E_PASSWORD'])))
    db.add(EspacioComun(edificio_id='e2e_a', nombre='Quincho', accion='reservar_quincho', tarifa=5000))
    db.add(Regla(edificio_id='e2e_a', accion='reservar_quincho', tipo='horario', params={'desde':'10:00','hasta':'22:00'}))
    db.commit()
'''], backend, "fixtures")
    run(["node", "node_modules/next/dist/bin/next", "build"], frontend, "build")
    procs, logs = [], []
    try:
        for args, cwd, name in (([sys.executable, "-m", "uvicorn", "app.main:app", "--port", "18091"], backend, "api"),
                               (["node", "node_modules/next/dist/bin/next", "start", "-p", "13091"], frontend, "web")):
            log = (ART / f"{name}.log").open("w", encoding="utf-8")
            logs.append(log)
            procs.append(subprocess.Popen(args, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, **flags))
        for url in (env["E2E_API"] + "/health", env["PW_BASE_URL"]):
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                try:
                    with urllib.request.urlopen(url, timeout=2) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(.5)
            else:
                raise RuntimeError("Servidor de prueba no arrancó")
        run(["node", "node_modules/@playwright/test/cli.js", "test", "-c", "playwright.config.js", "--workers=2"], frontend, "demo")
        run(["node", "node_modules/@playwright/test/cli.js", "test", "-c", "playwright.real.config.js"], frontend, "real")
        run([sys.executable, "-c", '''
import asyncio, os
from types import SimpleNamespace
from scripts.prueba_carga import main
raise SystemExit(asyncio.run(main(SimpleNamespace(api=os.environ['E2E_API'], edificio=os.environ['E2E_EDIFICIO'],
    clave_dispositivo=os.environ['E2E_DEVICE_KEY'], patentes='', peticiones=200, concurrencia=5, max_p95_ms=5000))))
'''], ROOT, "carga-local")
    finally:
        for proc in procs:
            proc.terminate()
        for proc in procs:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        for log in logs:
            log.close()
    print("E2E finalizado. Datos temporales conservados fuera del repositorio; logs en .artifacts/e2e.")


if __name__ == "__main__":
    main()
