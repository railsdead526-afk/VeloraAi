from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.message import Message


def generate_conversation_title(content: str, max_length: int = 40) -> str:
    text = " ".join(content.strip().split())
    if not text:
        return "Chat Baru"
    if len(text) <= max_length:
        return text
    return text[:max_length].rstrip() + "..."


def create_message(
    db: Session,
    conversation_id: int,
    role: str,
    content: str,
    *,
    commit: bool = True,
):
    existing_user_message = (
        db.query(Message)
        .filter(
            Message.conversation_id == conversation_id,
            Message.role == "user",
        )
        .first()
    )

    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()

    message = Message(conversation_id=conversation_id, role=role, content=content)
    db.add(message)

    if (
        role == "user"
        and conversation
        and conversation.title in ["Chat Baru", "New Chat", "Untitled"]
        and existing_user_message is None
    ):
        conversation.title = generate_conversation_title(content)

    if commit:
        db.commit()
        db.refresh(message)
    else:
        db.flush()

    return message


def get_messages_by_conversation(
    db: Session,
    conversation_id: int,
    limit: int = 100,
    offset: int = 0,
):
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return list(reversed(messages))
