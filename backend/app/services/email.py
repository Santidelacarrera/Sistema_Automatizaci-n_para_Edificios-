"""Correo masivo: plantillas HTML personalizadas y envío SMTP/SES."""
import smtplib
from email.message import EmailMessage
from html import escape
from string import Template

from ..config import settings
from .resultado import ENVIADO, ERROR, NO_CONFIGURADO, ResultadoEnvio

CANAL = "correo"

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


def configurado() -> bool:
    return bool(settings.smtp_host)


def motivo_no_configurado() -> str:
    return "" if configurado() else "Falta SMTP_HOST en .env (servidor de correo no configurado)"


def enviar(destino: str, asunto: str, html: str) -> ResultadoEnvio:
    """Envía un correo y devuelve el resultado. Marca ``transitorio`` los fallos de red para que el worker reintente."""
    if not destino:
        return ResultadoEnvio(CANAL, NO_CONFIGURADO, "El residente no tiene correo registrado")
    if not configurado():
        return ResultadoEnvio(CANAL, NO_CONFIGURADO, motivo_no_configurado())
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.smtp_from, destino, asunto
    msg.set_content("Este mensaje requiere un cliente con soporte HTML.")
    msg.add_alternative(html, subtype="html")
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
            s.starttls()
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        return ResultadoEnvio(CANAL, ERROR, "El servidor rechazó las credenciales (SMTP_USER / SMTP_PASSWORD)")
    except smtplib.SMTPRecipientsRefused:
        return ResultadoEnvio(CANAL, ERROR, f"El servidor rechazó el destinatario {destino}")
    except (smtplib.SMTPServerDisconnected, TimeoutError, OSError) as e:
        return ResultadoEnvio(CANAL, ERROR, f"Conexión con el servidor SMTP fallida ({e.__class__.__name__})",
                              transitorio=True)
    except smtplib.SMTPResponseException as e:
        return ResultadoEnvio(CANAL, ERROR, f"El servidor SMTP respondió {e.smtp_code}",
                              transitorio=400 <= e.smtp_code < 500)
    except smtplib.SMTPException as e:
        return ResultadoEnvio(CANAL, ERROR, f"Error SMTP ({e.__class__.__name__})")
    return ResultadoEnvio(CANAL, ENVIADO)
