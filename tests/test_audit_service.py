import json

from app.core.observability import set_request_id
from app.models.audit_log import AuditLog
from app.services.audit_service import record_audit_event


def test_audit_event_stores_metadata_without_sensitive_prompt_data(db, user):
    set_request_id("req-test-audit")
    record_audit_event(
        db,
        user_id=user.id,
        event="agent_tool_requested",
        resource_type="tool",
        resource_id="github_create_branch",
        metadata={"plan": "pro"},
    )

    row = db.query(AuditLog).filter(AuditLog.user_id == user.id).one()
    assert row.request_id == "req-test-audit"
    assert row.event == "agent_tool_requested"
    assert row.resource_id == "github_create_branch"
    assert json.loads(row.metadata_json) == {"plan": "pro"}


def test_audit_service_contract_has_no_prompt_or_arguments_fields():
    import inspect
    from app.services.audit_service import record_audit_event_best_effort

    signature = inspect.signature(record_audit_event_best_effort)
    assert "prompt" not in signature.parameters
    assert "arguments" not in signature.parameters
