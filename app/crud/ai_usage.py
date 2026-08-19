from sqlalchemy.orm import Session

from app.models.ai_usage import AIUsage


def record_ai_usage(
    db: Session,
    *,
    user_id: int,
    conversation_id: int,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    commit: bool = True,
) -> AIUsage:
    usage = AIUsage(
        user_id=user_id,
        conversation_id=conversation_id,
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
    )
    db.add(usage)
    if commit:
        db.commit()
        db.refresh(usage)
    else:
        db.flush()
    return usage
