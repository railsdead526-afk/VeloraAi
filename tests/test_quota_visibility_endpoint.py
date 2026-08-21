def test_quota_visibility_user_fields_are_exposed(db):
    from datetime import datetime, timezone

    from app.models.conversation import Conversation
    from app.models.user import User
    from app.services.quota_service import requests_used_since

    user = User(email="quota-visibility@example.com", hashed_password="test", role="free")
    db.add(user)
    db.flush()
    conversation = Conversation(title="Quota", user_id=user.id)
    db.add(conversation)
    db.commit()

    day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    assert requests_used_since(db, user.id, day_start) == 0
