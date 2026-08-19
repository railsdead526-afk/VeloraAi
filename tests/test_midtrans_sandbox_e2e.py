import os
import uuid

import pytest

from app.services.midtrans_service import MidtransError, MidtransService


SANDBOX_SERVER_KEY = os.getenv("MIDTRANS_SERVER_KEY", "")
RUN_SANDBOX_E2E = os.getenv("RUN_MIDTRANS_SANDBOX_E2E", "false").lower() == "true"
SETTLED_ORDER_ID = os.getenv("MIDTRANS_E2E_SETTLED_ORDER_ID", "").strip()


pytestmark = pytest.mark.midtrans_e2e


def _service() -> MidtransService:
    return MidtransService()


@pytest.mark.skipif(
    not RUN_SANDBOX_E2E or not SANDBOX_SERVER_KEY,
    reason="Real Midtrans Sandbox E2E requires RUN_MIDTRANS_SANDBOX_E2E=true and MIDTRANS_SERVER_KEY",
)
def test_midtrans_sandbox_create_snap_transaction():
    service = _service()
    order_id = f"velora-e2e-{uuid.uuid4().hex}"
    result = service.create_snap_transaction(
        order_id=order_id,
        gross_amount=10000,
        customer_email=f"e2e-{uuid.uuid4().hex[:8]}@example.com",
        item_name="VeloraAi Sandbox E2E",
    )
    assert result["token"]
    assert result["redirect_url"]


@pytest.mark.skipif(
    not RUN_SANDBOX_E2E or not SANDBOX_SERVER_KEY or not SETTLED_ORDER_ID,
    reason="Provide RUN_MIDTRANS_SANDBOX_E2E=true, MIDTRANS_SERVER_KEY, and MIDTRANS_E2E_SETTLED_ORDER_ID",
)
def test_midtrans_sandbox_settled_order_status():
    service = _service()
    status = service.get_transaction_status(SETTLED_ORDER_ID)
    assert status["order_id"] == SETTLED_ORDER_ID
    assert status["transaction_status"] == "settlement"
    assert float(status["gross_amount"]) > 0


@pytest.mark.skipif(
    not RUN_SANDBOX_E2E or not SANDBOX_SERVER_KEY or not SETTLED_ORDER_ID,
    reason="Provide RUN_MIDTRANS_SANDBOX_E2E=true, MIDTRANS_SERVER_KEY, and MIDTRANS_E2E_SETTLED_ORDER_ID",
)
def test_midtrans_sandbox_refund_is_reachable_for_settled_transaction():
    service = _service()
    status = service.get_transaction_status(SETTLED_ORDER_ID)
    if status.get("transaction_status") != "settlement":
        pytest.skip("The supplied sandbox order is not settled")

    amount = int(float(status["gross_amount"]))
    result = service.refund_transaction(SETTLED_ORDER_ID, amount, "VeloraAi sandbox E2E refund")
    assert isinstance(result, dict)
    assert result


def test_midtrans_signature_verification_and_tamper_detection(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.midtrans_server_key", "sandbox-test-key")
    service = _service()
    import hashlib

    raw = "order-123" + "200" + "10000" + "sandbox-test-key"
    signature = hashlib.sha512(raw.encode()).hexdigest()
    assert service.verify_notification_signature(
        order_id="order-123",
        status_code="200",
        gross_amount="10000",
        signature_key=signature,
    )
    assert not service.verify_notification_signature(
        order_id="order-123",
        status_code="200",
        gross_amount="10001",
        signature_key=signature,
    )


def test_midtrans_service_requires_server_key(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.midtrans_server_key", "")
    with pytest.raises(MidtransError):
        MidtransService()
