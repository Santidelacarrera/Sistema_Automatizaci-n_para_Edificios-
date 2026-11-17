"""Utilidades de logging estructurado en JSON para observabilidad."""
import json
import logging
from datetime import datetime, timezone

log_app = logging.getLogger("edificio.app")


def emitir_log_json(nivel: str, evento: str, **campos) -> str:
    """Formatea y emite un evento estructurado en JSON."""
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "nivel": nivel.upper(),
        "evento": evento,
        **campos,
    }
    linea = json.dumps(payload, default=str, ensure_ascii=False)
    fn = getattr(log_app, nivel.lower(), log_app.info)
    fn(linea)
    return linea
