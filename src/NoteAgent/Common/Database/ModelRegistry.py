"""Explicit ORM registration for migrations and schema-isolated tests."""


def load_all_models() -> None:
    """Register every application table on the shared Base metadata."""
    import NoteAgent.Modules.Conversations.Domain.Po.ConversationModels  # noqa: F401
    import NoteAgent.Common.WorkspaceAccess.NoteAccessModels  # noqa: F401
    import NoteAgent.Modules.Notes.Domain.Po.NoteChangeModels  # noqa: F401
    import NoteAgent.Modules.Recovery.Domain.Po.RecoveryModels  # noqa: F401
    import NoteAgent.Modules.Retrieval.Domain.Po.IndexRepairModels  # noqa: F401
    import NoteAgent.Modules.Sources.Domain.Po.SourceFileModels  # noqa: F401
