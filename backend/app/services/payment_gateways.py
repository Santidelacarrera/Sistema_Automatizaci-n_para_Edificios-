"""Adaptadores de pasarelas de pago para comunidades chilenas y SaaS.

Soporta:
- `sandbox`: pasarela local determinista de laboratorio/pruebas (nunca mueve dinero real).
- `transbank`: Webpay Plus REST API v1.2 (ambiente de integración o producción con credenciales explícitas).
- `mercadopago`: Checkout Preferences API + consulta de pago y firma HMAC de webhook (`x-signature`).
- `khipu`: API v3.0 (`/v3/payments`) con autenticación `x-api-key`.

Nunca ejecuta cobros reales sin credenciales configuradas ni simula éxito cuando un proveedor externo falla.
"""
import hashlib
import hmac
import secrets
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException

from ..config import settings

PROVEEDORES = ("sandbox", "transbank", "mercadopago", "khipu")


def _validar_url_retorno(url: str) -> str:
    if not url:
        return "http://localhost:3000/mi-depto"
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(422, "URL de retorno inválida")
    return url


def crear_transaccion(proveedor: str, orden_compra: str, sesion_id: str, monto: float,
                      moneda: str = "CLP", url_retorno: str = "") -> dict:
    """Inicia una transacción en la pasarela seleccionada y devuelve `{token, url_pago, modo}`."""
    url_retorno = _validar_url_retorno(url_retorno)
    monto_entero = int(round(float(monto)))
    if monto_entero <= 0:
        raise HTTPException(422, "El monto a pagar debe ser mayor que cero")

    if proveedor == "sandbox":
        if settings.entorno == "produccion":
            raise HTTPException(503, "La pasarela sandbox no está permitida en producción")
        token = f"sbx_{secrets.token_urlsafe(24)}"
        return {
            "token": token,
            "url_pago": f"{url_retorno}?proveedor=sandbox&token_ws={token}",
            "modo": "sandbox_local",
        }

    if proveedor == "transbank":
        if not settings.transbank_commerce_code or not settings.transbank_api_key:
            raise HTTPException(503, "Transbank Webpay Plus no está configurado (faltan TRANSBANK_COMMERCE_CODE / TRANSBANK_API_KEY)")
        base = ("https://webpay3g.transbank.cl" if settings.transbank_env == "produccion"
                else "https://webpay3gint.transbank.cl")
        try:
            with httpx.Client(timeout=15, follow_redirects=False) as client:
                r = client.post(
                    f"{base}/rswebpaytransaction/api/webpay/v1.2/transactions",
                    headers={
                        "Tbk-Api-Key-Id": settings.transbank_commerce_code,
                        "Tbk-Api-Key-Secret": settings.transbank_api_key,
                        "Content-Type": "application/json",
                    },
                    json={
                        "buy_order": orden_compra[:26],
                        "session_id": sesion_id[:61],
                        "amount": monto_entero,
                        "return_url": url_retorno,
                    },
                )
                r.raise_for_status()
                data = r.json()
                return {
                    "token": str(data["token"]),
                    "url_pago": f"{data['url']}?token_ws={data['token']}",
                    "modo": settings.transbank_env,
                }
        except (httpx.HTTPError, KeyError, ValueError):
            raise HTTPException(503, "Transbank no pudo iniciar la transacción; verifique credenciales y conectividad") from None

    if proveedor == "mercadopago":
        if not settings.mercadopago_access_token:
            raise HTTPException(503, "Mercado Pago no está configurado (falta MERCADOPAGO_ACCESS_TOKEN)")
        try:
            with httpx.Client(timeout=15, follow_redirects=False) as client:
                r = client.post(
                    "https://api.mercadopago.com/checkout/preferences",
                    headers={"Authorization": f"Bearer {settings.mercadopago_access_token}"},
                    json={
                        "external_reference": orden_compra,
                        "items": [{"title": f"Gasto común {orden_compra}", "quantity": 1,
                                   "currency_id": moneda, "unit_price": monto_entero}],
                        "back_urls": {"success": url_retorno, "failure": url_retorno, "pending": url_retorno},
                    },
                )
                r.raise_for_status()
                data = r.json()
                return {
                    "token": str(data["id"]),
                    "url_pago": str(data.get("sandbox_init_point") or data.get("init_point") or ""),
                    "modo": "api",
                }
        except (httpx.HTTPError, KeyError, ValueError):
            raise HTTPException(503, "Mercado Pago no pudo crear la preferencia de pago") from None

    if proveedor == "khipu":
        if not settings.khipu_api_key:
            raise HTTPException(503, "Khipu no está configurado (falta KHIPU_API_KEY)")
        try:
            with httpx.Client(timeout=15, follow_redirects=False) as client:
                r = client.post(
                    "https://payment-api.khipu.com/v3/payments",
                    headers={"x-api-key": settings.khipu_api_key, "Content-Type": "application/json"},
                    json={
                        "subject": f"Pago comunidad {orden_compra}",
                        "currency": moneda,
                        "amount": monto_entero,
                        "transaction_id": orden_compra,
                        "return_url": url_retorno,
                    },
                )
                r.raise_for_status()
                data = r.json()
                return {
                    "token": str(data["payment_id"]),
                    "url_pago": str(data.get("payment_url") or ""),
                    "modo": "api_v3",
                }
        except (httpx.HTTPError, KeyError, ValueError):
            raise HTTPException(503, "Khipu no pudo crear el cobro") from None

    raise HTTPException(422, f"Proveedor de pago no soportado: {proveedor}")


def confirmar_transaccion(proveedor: str, token: str, monto_esperado: float, resultado_sandbox: str = "autorizada") -> dict:
    """Confirma el estado de una transacción con el proveedor y verifica el monto."""
    monto_entero = int(round(float(monto_esperado)))
    if proveedor == "sandbox":
        if settings.entorno == "produccion":
            raise HTTPException(503, "Sandbox deshabilitado en producción")
        if resultado_sandbox == "rechazada":
            return {"estado": "rechazada", "codigo_autorizacion": ""}
        return {"estado": "autorizada", "codigo_autorizacion": f"AUTH-{token[-8:].upper()}", "monto": monto_entero}

    if proveedor == "transbank":
        if not settings.transbank_commerce_code or not settings.transbank_api_key:
            raise HTTPException(503, "Transbank no está configurado")
        base = ("https://webpay3g.transbank.cl" if settings.transbank_env == "produccion"
                else "https://webpay3gint.transbank.cl")
        try:
            with httpx.Client(timeout=15, follow_redirects=False) as client:
                r = client.put(
                    f"{base}/rswebpaytransaction/api/webpay/v1.2/transactions/{token}",
                    headers={
                        "Tbk-Api-Key-Id": settings.transbank_commerce_code,
                        "Tbk-Api-Key-Secret": settings.transbank_api_key,
                        "Content-Type": "application/json",
                    },
                )
                r.raise_for_status()
                data = r.json()
        except (httpx.HTTPError, ValueError):
            raise HTTPException(503, "No se pudo confirmar la transacción con Transbank") from None
        if int(round(float(data.get("amount", 0)))) != monto_entero:
            raise HTTPException(409, "El monto confirmado por Transbank no coincide con la orden")
        autorizada = data.get("status") == "AUTHORIZED" and data.get("response_code") == 0
        return {
            "estado": "autorizada" if autorizada else "rechazada",
            "codigo_autorizacion": str(data.get("authorization_code") or ""),
            "monto": monto_entero,
        }

    if proveedor == "mercadopago":
        if not settings.mercadopago_access_token:
            raise HTTPException(503, "Mercado Pago no está configurado")
        try:
            with httpx.Client(timeout=15, follow_redirects=False) as client:
                r = client.get(
                    f"https://api.mercadopago.com/v1/payments/{token}",
                    headers={"Authorization": f"Bearer {settings.mercadopago_access_token}"},
                )
                r.raise_for_status()
                data = r.json()
        except (httpx.HTTPError, ValueError):
            raise HTTPException(503, "No se pudo consultar el pago en Mercado Pago") from None
        if int(round(float(data.get("transaction_amount", 0)))) != monto_entero:
            raise HTTPException(409, "El monto informado por Mercado Pago no coincide con la orden")
        return {
            "estado": "autorizada" if data.get("status") == "approved" else "rechazada",
            "codigo_autorizacion": str(data.get("id") or ""),
            "monto": monto_entero,
        }

    if proveedor == "khipu":
        if not settings.khipu_api_key:
            raise HTTPException(503, "Khipu no está configurado")
        try:
            with httpx.Client(timeout=15, follow_redirects=False) as client:
                r = client.get(
                    f"https://payment-api.khipu.com/v3/payments/{token}",
                    headers={"x-api-key": settings.khipu_api_key},
                )
                r.raise_for_status()
                data = r.json()
        except (httpx.HTTPError, ValueError):
            raise HTTPException(503, "No se pudo consultar el cobro en Khipu") from None
        if int(round(float(data.get("amount", 0)))) != monto_entero:
            raise HTTPException(409, "El monto informado por Khipu no coincide con la orden")
        return {
            "estado": "autorizada" if data.get("status") == "done" else "rechazada",
            "codigo_autorizacion": str(data.get("receipt_url") or data.get("payment_id") or "")[:40],
            "monto": monto_entero,
        }

    raise HTTPException(422, f"Proveedor no soportado: {proveedor}")


def verificar_firma_webhook(cuerpo: bytes, firma_header: str | None) -> bool:
    """Verifica firma HMAC-SHA256 del webhook de pasarela con `PAYMENT_WEBHOOK_SECRET`."""
    if not settings.payment_webhook_secret or not firma_header:
        return False
    esperada = hmac.new(settings.payment_webhook_secret.encode(), cuerpo, hashlib.sha256).hexdigest()
    limpia = firma_header.strip().removeprefix("sha256=")
    return hmac.compare_digest(esperada, limpia)
