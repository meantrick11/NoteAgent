"""Conversation metadata, checkpointed state, and history projection.

Sits between the HTTP layer and the checkpointer: it owns which branch is active and
where that branch's head checkpoint points. It does not import HTTP or recovery.
"""

from NoteAgent.BusinessModules.ConversationState.ConversationCheckpoints import CHECKPOINT_NS, CheckpointRuntime, thread_config
from NoteAgent.BusinessModules.ConversationState.ConversationModels import ConversationBranch, ConversationRun, UserMessageBoundary
from NoteAgent.BusinessModules.ConversationState.ConversationRecords import STATE_SCHEMA_VERSION, ConversationRecord, GraphState, MessageRecord, StateSchemaError, initial_state
from NoteAgent.BusinessModules.ConversationState.ConversationStateService import ConversationNotFound, ConversationService, StateView

__all__ = [
    "CHECKPOINT_NS",
    "STATE_SCHEMA_VERSION",
    "CheckpointRuntime",
    "ConversationBranch",
    "ConversationNotFound",
    "ConversationRecord",
    "ConversationRun",
    "ConversationService",
    "GraphState",
    "MessageRecord",
    "StateSchemaError",
    "StateView",
    "UserMessageBoundary",
    "initial_state",
    "thread_config",
]
