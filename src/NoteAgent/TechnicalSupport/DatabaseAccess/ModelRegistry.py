"""Explicit ORM registration for migrations and schema-isolated tests."""


def load_all_models() -> None:
    """Register every application table on the shared Base metadata."""
    import NoteAgent.BusinessModules.ConversationState.ConversationModels  # noqa: F401
    import NoteAgent.TechnicalSupport.NoteAccessControl.NoteAccessModels  # noqa: F401
    import NoteAgent.BusinessModules.NoteStorage.ChangeJournal.NoteChangeModels  # noqa: F401
    import NoteAgent.BusinessModules.ConversationRecovery.RecoveryModels  # noqa: F401
    import NoteAgent.BusinessModules.NoteRetrieval.IndexRepair.IndexRepairModels  # noqa: F401
