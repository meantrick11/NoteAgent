"""Database leases identify abandoned runs without interrupting another worker."""

from datetime import datetime, timezone, timedelta
import uuid

from sqlalchemy import delete, or_, update

from noteagent.conversations.models import ConversationRun

LEASE_SECONDS = 60
HEARTBEAT_SECONDS = 10


def expires_at():
    return datetime.now(timezone.utc) + timedelta(seconds=LEASE_SECONDS)


def reconcile_expired_runs(session_factory):
    """Expire unaccepted claims; accepted recovery turns survive until claimed."""
    expired = or_(ConversationRun.lease_expires_at.is_(None),
                  ConversationRun.lease_expires_at <= datetime.now(timezone.utc))
    with session_factory() as session:
        session.execute(delete(ConversationRun).where(
            ConversationRun.status == "prepared", expired,
            ConversationRun.accepted_checkpoint_id.is_(None),
        ))
        session.execute(update(ConversationRun).where(
            ConversationRun.status == "running", expired,
        ).values(status="interrupted", lease_token=None, lease_expires_at=None))
        session.commit()


def refresh_lease(session_factory, run_id, token):
    """Fence stale runners: only the current token can extend the claim."""
    with session_factory() as session:
        result = session.execute(update(ConversationRun).where(
            ConversationRun.id == uuid.UUID(run_id), ConversationRun.lease_token == token,
            ConversationRun.status == "running",
        ).values(lease_expires_at=expires_at()))
        if result.rowcount != 1:
            return False
        session.commit()
        return True
