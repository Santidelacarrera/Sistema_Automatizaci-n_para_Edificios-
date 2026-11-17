"""Prueba Redis + Celery real con DB temporal, sin proveedores ni mensajes externos.

Requiere Docker y dependencias backend. Crea y elimina sólo su contenedor Redis con nombre aleatorio.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    run_dir = Path(tempfile.mkdtemp(prefix="edificios-worker-"))
    art = ROOT / ".artifacts" / "worker"
    art.mkdir(parents=True, exist_ok=True)
    name = "edificios-worker-check-" + secrets.token_hex(5)
    env = os.environ.copy()
    env.update(DATABASE_URL="sqlite:///" + (run_dir / "worker.db").as_posix(), ENTORNO="desarrollo",
               CELERY_EAGER="false", SMTP_HOST="", SMTP_PASSWORD="", EVOLUTION_URL="", EVOLUTION_APIKEY="",
               EVOLUTION_INSTANCE="", ANTHROPIC_API_KEY="", DOCMIND_URL="", DOCMIND_TENANTS="{}",
               MFA_ENCRYPTION_KEY="", MFA_REQUIRED_PRIVILEGED="false")
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    worker, created, logs = None, False, []
    def start_worker():
        log = (art / f"worker-{len(logs)}.log").open("w", encoding="utf-8")
        logs.append(log)
        return subprocess.Popen([sys.executable, "-m", "celery", "-A", "app.tasks.celery", "worker", "--pool=solo",
            "--concurrency=1", "--loglevel=INFO", "--without-gossip", "--without-mingle"], cwd=ROOT / "backend",
            env=env, stdout=log, stderr=subprocess.STDOUT, **flags)
    def stop_worker(proc):
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
    try:
        subprocess.run(["docker", "run", "-d", "--name", name, "--label", "task=edificios-worker-check",
            "-p", "127.0.0.1::6379", "redis:7-alpine"], check=True, capture_output=True, **flags)
        created = True
        info = json.loads(subprocess.check_output(["docker", "inspect", name], **flags))[0]
        port = info["NetworkSettings"]["Ports"]["6379/tcp"][0]["HostPort"]
        env["REDIS_URL"] = f"redis://127.0.0.1:{port}/0"
        os.environ.update(env)
        sys.path.insert(0, str(ROOT / "backend"))
        import redis
        broker = redis.Redis.from_url(env["REDIS_URL"], socket_connect_timeout=2)
        for _ in range(20):
            try:
                if broker.ping():
                    break
            except redis.ConnectionError:
                time.sleep(.5)
        else:
            raise RuntimeError("Redis temporal no arrancó")
        with (art / "migraciones.log").open("w", encoding="utf-8") as log:
            subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT / "backend", env=env,
                           stdout=log, stderr=subprocess.STDOUT, check=True, **flags)
        from app.config import hoy_local
        from app.db import SessionLocal
        from app.models import Edificio, Residente, Rol, Unidad
        from app.operations_models import Incidencia, Notificacion, PlanMantenimiento
        from app.security import hash_clave_dispositivo
        from app.tasks import automatizaciones, entregar_outbox
        with SessionLocal() as db:
            db.add(Edificio(id="worker_test", nombre="Prueba worker", device_api_key=hash_clave_dispositivo(secrets.token_urlsafe(32))))
            db.flush()
            u = Unidad(edificio_id="worker_test", numero="101", coeficiente=1, codigo_cobro="WORKER101")
            db.add(u)
            db.flush()
            r = Residente(edificio_id=u.edificio_id, unidad_id=u.id, nombre="Admin prueba", rut="11111111-1",
                          email="prueba@example.invalid", rol=Rol.admin)
            db.add(r)
            db.flush()
            db.add(PlanMantenimiento(edificio_id=u.edificio_id, titulo="Revisión programada", responsable_id=r.id,
                                    intervalo_dias=30, proxima_fecha=hoy_local()))
            db.add(Notificacion(edificio_id=u.edificio_id, residente_id=r.id, clave="fallo-controlado", canal="email",
                                titulo="Prueba aislada", texto="No enviar fuera del entorno temporal"))
            db.commit()
        worker = start_worker()
        result = automatizaciones.delay().get(timeout=45)
        assert result["worker_test"]["creadas"] == 1, result
        with SessionLocal() as db:
            assert db.query(Incidencia).count() == 1
            assert db.query(Notificacion).filter_by(canal="app").count() == 1
        stop_worker(worker)
        # El broker conserva la tarea cuando no hay worker. El segundo proceso debe consumirla.
        pending = entregar_outbox.delay()
        assert not pending.ready()
        worker = start_worker()
        delivery = pending.get(timeout=45)
        assert delivery == {"enviados": 0, "fallidos": 1, "cancelados": 0}, delivery
        with SessionLocal() as db:
            n = db.query(Notificacion).filter_by(canal="email").one()
            assert n.estado == "fallido" and n.intentos == 1
        result = {"broker": "Redis real", "worker": "Celery solo, dos procesos sucesivos", "automatizacion": result,
                  "outbox": delivery, "tarea_conservada_sin_worker": True, "proveedores_externos": False}
        (art / "resultado.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=True))
    finally:
        stop_worker(worker)
        for log in logs:
            log.close()
        if created:
            subprocess.run(["docker", "rm", "-f", name], check=True, capture_output=True, **flags)


if __name__ == "__main__":
    main()
