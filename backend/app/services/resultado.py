"""Resultado explícito de un envío (WhatsApp, correo): el panel debe poder decir qué pasó y por qué."""
from dataclasses import dataclass

ENVIADO = "enviado"            # entregado al proveedor (WhatsApp) o aceptado por el servidor SMTP
ENCOLADO = "encolado"          # en cola de Celery; el resultado final queda en el log del worker
NO_CONFIGURADO = "no_configurado"  # falta configuración del sistema o dato del residente
ERROR = "error"


@dataclass(frozen=True)
class ResultadoEnvio:
    canal: str
    estado: str
    motivo: str = ""
    transitorio: bool = False  # error de red o servidor temporal: vale la pena reintentar

    @property
    def exitoso(self) -> bool:
        return self.estado in (ENVIADO, ENCOLADO)

    def a_dict(self) -> dict:
        return {"canal": self.canal, "estado": self.estado, "motivo": self.motivo}
