import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI


_logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open the checkpointer on startup; release every connection on shutdown."""
    container = app.state.container
    if container.checkpoints is not None:
        await container.checkpoints.open()
    try:
        if container.workspace is not None:
            container.workspace.ensure_row()
        if container.versions is not None and container.workspace.state().current_commit is None:
            with container.workspace.operation("mutate"):
                container.mutations.initialize_locked()
        if container.conversations is not None:
            container.conversations.reconcile_expired_runs()
        if container.mutations is not None:
            maintenance = container.workspace.maintenance()
            if maintenance is None or maintenance[1] == "mutation":
                container.mutations.reconcile_pending()
            maintenance = container.workspace.maintenance()
            if maintenance is not None and maintenance[1] == "approval":
                from NoteAgent.BusinessModules.NoteStorage.ChangeJournal.NoteChangeModels import MutationRecord
                from sqlalchemy import select
                with container.mutations._session_factory() as session:
                    pending = session.scalar(select(MutationRecord).where(MutationRecord.operation_id == maintenance[0]))
                    cid = str(pending.conversation_id) if pending is not None else None
                if cid is not None:
                    with container.workspace.operation("mutate", owner=maintenance[0]):
                        await container.chat_agent.review(cid, "approve")
            retrieval = container.model_runtime.snapshot().retrieval
            if retrieval is not None and container.workspace.maintenance() is None:
                with container.workspace.operation("mutate"):
                    container.mutations.index_repairs.reconcile(retrieval)
        yield
    finally:
        if container.checkpoints is not None:
            await container.checkpoints.close()
        container.model_runtime.shutdown()
        container.engine.dispose()
