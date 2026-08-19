from __future__ import annotations

import base64
import hashlib
import hmac

import httpx

from app.core.config import settings


class MidtransError(RuntimeError):
    pass


class MidtransService:
    def __init__(self) -> None:
        self.server_key = settings.midtrans_server_key
        self.base_url = settings.midtrans_base_url.rstrip("/")
        self.snap_base_url = settings.midtrans_snap_base_url.rstrip("/")
        self.is_production = settings.midtrans_is_production
        if not self.server_key:
            raise MidtransError("Midtrans server key is not configured")

    @property
    def _authorization(self) -> str:
        return "Basic " + base64.b64encode(f"{self.server_key}:".encode()).decode()

    def create_snap_transaction(
        self,
        *,
        order_id: str,
        gross_amount: int,
        customer_email: str,
        item_name: str,
    ) -> dict:
        payload = {
            "transaction_details": {
                "order_id": order_id,
                "gross_amount": gross_amount,
            },
            "customer_details": {
                "email": customer_email,
            },
            "item_details": [
                {
                    "id": item_name.lower().replace(" ", "-"),
                    "price": gross_amount,
                    "quantity": 1,
                    "name": item_name[:50],
                }
            ],
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": self._authorization,
        }
        try:
            response = httpx.post(
                f"{self.snap_base_url}/snap/v1/transactions",
                headers=headers,
                json=payload,
                timeout=settings.payment_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MidtransError("Unable to create Midtrans transaction") from exc
        token = data.get("token")
        redirect_url = data.get("redirect_url")
        if not token or not redirect_url:
            raise MidtransError("Midtrans returned an incomplete transaction response")
        return data

    def verify_notification_signature(
        self,
        *,
        order_id: str,
        status_code: str,
        gross_amount: str,
        signature_key: str,
    ) -> bool:
        raw = f"{order_id}{status_code}{gross_amount}{self.server_key}".encode()
        expected = hashlib.sha512(raw).hexdigest()
        return hmac.compare_digest(expected, signature_key)

    def get_transaction_status(self, order_id: str) -> dict:
        headers = {
            "Accept": "application/json",
            "Authorization": self._authorization,
        }
        try:
            response = httpx.get(
                f"{self.base_url}/v2/{order_id}/status",
                headers=headers,
                timeout=settings.payment_timeout_seconds,
            )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MidtransError("Unable to query Midtrans transaction status") from exc

    def refund_transaction(self, order_id: str, amount: int, reason: str) -> dict:
        payload = {
            "refund_key": f"velora-refund-{order_id}",
            "amount": amount,
            "reason": reason[:255],
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": self._authorization,
        }
        try:
            response = httpx.post(
                f"{self.base_url}/v2/{order_id}/refunds",
                headers=headers,
                json=payload,
                timeout=settings.payment_timeout_seconds,
            )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MidtransError("Unable to create Midtrans refund") from exc
