from app.services import ai_tool_loop, tool_agent


class _Result:
    content = "canonical result"


def test_legacy_tool_agent_delegates_to_canonical_loop(monkeypatch):
    calls = {}

    def fake_generate(messages, *, plan, confirmed, registry):
        calls.update(
            {
                "messages": messages,
                "plan": plan,
                "confirmed": confirmed,
                "registry": registry,
            }
        )
        return _Result()

    monkeypatch.setattr(ai_tool_loop, "generate_ai_reply_with_tools", fake_generate)

    registry = object()
    result = tool_agent.generate_with_tools(
        [{"role": "user", "content": "hello"}],
        registry=registry,
        plan="pro",
        confirmed=True,
    )

    assert result == "canonical result"
    assert calls == {
        "messages": [{"role": "user", "content": "hello"}],
        "plan": "pro",
        "confirmed": True,
        "registry": registry,
    }
