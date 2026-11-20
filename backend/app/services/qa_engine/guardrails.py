"""Blindaje de seguridad: detección de Prompt Injection, redacción de secretos y Zero-Hallucination."""
import re

_PATRONES_INYECCION = (
    re.compile(r"ignora\s+(todas\s+)?(las\s+)?instrucciones", re.IGNORECASE),
    re.compile(r"ignore\s+(all\s+)?(previous\s+)?instructions", re.IGNORECASE),
    re.compile(r"(system\s*prompt|prompt\s+del\s+sistema|reglas\s+internas)", re.IGNORECASE),
    re.compile(r"(muestra|revela|imprime|dame)\s+(el\s+)?(jwt_secret|api_key|token|password|clave|secreto)", re.IGNORECASE),
    re.compile(r"<\s*/?\s*system\s*>", re.IGNORECASE),
    re.compile(r"(select\s+\*\s+from|drop\s+table|union\s+select)", re.IGNORECASE),
)

_RE_SECRETOS = (
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),  # JWT
    re.compile(r"(?:sk-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{20,}|ghp_[0-9A-Za-z]{20,})"),
    re.compile(r"(?i)(jwt_secret|api_key|password_hash|fcm_server_key|twilio_auth_token)\s*[:=]\s*\S+"),
)


def detectar_prompt_injection(texto: str, edificio_actual: str) -> tuple[bool, str]:
    """Detecta intentos de manipular instrucciones, exfiltrar secretos o saltar el tenant."""
    t = (texto or "").strip()
    for pat in _PATRONES_INYECCION:
        if pat.search(t):
            return True, "Consulta bloqueada por política de seguridad (intento de inyección o exfiltración)."
    # Bloquea solicitud explícita de datos de otro edificio distinto al autenticado
    m_otro = re.findall(r"\bedificio_[a-z0-9_-]+\b", t.lower())
    for eid in m_otro:
        if eid != edificio_actual.lower():
            return True, f"Acceso denegado: no está autorizado a consultar datos del contexto '{eid}'."
    return False, ""


def redactar_secretos(texto: str) -> str:
    s = texto or ""
    for pat in _RE_SECRETOS:
        s = pat.sub("[REDACTADO]", s)
    return s


def sanitizar_entrada_externa(texto: str) -> str:
    """Neutraliza directivas ocultas dentro de documentos o fuentes indexadas."""
    s = redactar_secretos(texto or "")
    s = re.sub(r"<\s*/?\s*(system|assistant|tool)\s*>", " ", s, flags=re.IGNORECASE)
    return s
