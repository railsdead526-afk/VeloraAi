from app.models.conversation import Conversation
from app.models.tool_confirmation import ToolConfirmation
from app.services.tool_confirmation import create_confirmation_token, verify_confirmation_token


def test_confirmation_token_is_single_use(db, user):
    conversation = Conversation(title="Tool confirmation", user_id=user.id)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    arguments = {"repository": "railsdead526-afk/VeloraAi", "path": "README.md"}
    token = create_confirmation_token(
        user_id=user.id,
        conversation_id=conversation.id,
        tool_name="github_write_file",
        arguments=arguments,
    )

    assert (
        verify_confirmation_token(
            token,
            user_id=user.id,
            conversation_id=conversation.id,
            tool_name="github_write_file",
            arguments=arguments,
        )
        is True
    )

    assert (
        verify_confirmation_token(
            token,
            user_id=user.id,
            conversation_id=conversation.id,
            tool_name="github_write_file",
            arguments=arguments,
        )
        is False
    )

    confirmation = db.query(ToolConfirmation).filter_by(user_id=user.id).one()
    assert confirmation.used_at is not None
