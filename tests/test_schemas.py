import pytest
from pydantic import ValidationError

from app.schemas.conversation import ConversationCreate, ConversationUpdate
from app.schemas.message import MessageCreate


def test_message_rejects_blank_content():
    with pytest.raises(ValidationError):
        MessageCreate(content="   ")


def test_message_rejects_oversized_content():
    with pytest.raises(ValidationError):
        MessageCreate(content="x" * 12001)


def test_conversation_title_is_normalized():
    assert ConversationCreate(title="  My Chat  ").title == "My Chat"
    assert ConversationCreate(title="   ").title == "New Chat"


def test_conversation_update_rejects_blank_title():
    with pytest.raises(ValidationError):
        ConversationUpdate(title="   ")
