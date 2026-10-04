"""State and execution handles shared by conversation services and graph runners."""

from dataclasses import dataclass
from typing import Any

from noteagent.conversations.records import GraphState


class ConversationNotFound(KeyError):
    """The conversation or checkpoint does not exist."""


class TurnAlreadyClaimed(RuntimeError):
    """This request or resume attempt has already been accepted."""


class ConversationBusy(RuntimeError):
    """Another run holds the conversation's execution claim."""


class StaleConversation(RuntimeError):
    """A publisher no longer owns the branch/head/generation it read."""


@dataclass(slots=True)
class StateView:
    """One checkpoint's state plus the exact config it was read with."""

    values: GraphState
    config: dict[str, Any]


@dataclass(slots=True)
class PreparedTurn:
    """Execution position and accepted application head are separate coordinates."""

    conversation_id: str
    branch_id: str
    turn_id: str
    user_message_id: str
    generation: int
    run_id: str
    # Idempotency key chosen for this turn; echoed to the client so an optimistic row
    # can be replaced by the durable server identity.
    request_id: str
    before_config: dict[str, Any]
    config: dict[str, Any]
    head_config: dict[str, Any]
    lease_token: str
