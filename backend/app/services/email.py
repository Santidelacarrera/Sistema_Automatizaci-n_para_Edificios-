"""Correo masivo: plantillas HTML personalizadas y envío SMTP/SES."""
import smtplib
from email.message import EmailMessage
from html import escape
from string import Template

from ..config import settings

PLANTILLA_GASTO_COMUN = Template("""<html><body style="font-family:Arial,sans-serif">
<h2>$edificio — Gastos comunes $periodo</h2>
<p>Estimado(a) $nombre (unidad $unidad):</p>
<p>Su gasto común del periodo es <b>$monto</b>, con vencimiento el <b>$vencimiento</b>.</p>
<p>Código de pago para transferencias: <code>$codigo_cobro</code></p>
</body></html>""")

PLANTILLA_CIRCULAR = Template("""<html><body style="font-family:Arial,sans-serif">
<h2>$edificio — $asunto</h2><p>Estimado(a) $nombre:</p><div>$cuerpo</div></body></html>""")


def render(plantilla: Template, **ctx) -> str:
    return plantilla.safe_substitute({k: escape(str(v)) for k, v in ctx.items() if k != "cuerpo"} |
                                     ({"cuerpo": ctx["cuerpo"]} if "cuerpo" in ctx else {}))


def enviar(destino: str, asunto: str, html: str) -> bool:
    if not settings.smtp_host or not destino:
        return False
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.smtp_from, destino, asunto
    msg.set_content("Este mensaje requiere un cliente con soporte HTML.")
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
        s.starttls()
        if settings.smtp_user:
            s.login(settings.smtp_user, settings.smtp_password)
        s.send_message(msg)
    return True
