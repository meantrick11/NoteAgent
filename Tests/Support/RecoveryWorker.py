"""Subprocess worker for isolated PostgreSQL restart and contention drills."""
import asyncio
import json
import socket
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy import select
from Support.DurableApp import build_durable_app
from NoteAgent.BusinessModules.ConversationState.ConversationCheckpoints import checkpoint_id_of
from NoteAgent.BusinessModules.NoteStorage.NoteChanges import CREATE, MutationCommand, Origin
from NoteAgent.BusinessModules.ConversationRecovery.RecoveryModels import RecoveryJob


async def run(config, mode):
    root = Path(config["root"])
    class StopAtCandidate:
        def check(self, stage):
            if stage == "candidate_saved":
                (root / "ready.json").write_text(json.dumps({"stage": stage}), encoding="utf-8")
                # Parent terminates this live worker while the advisory lock is held.
                threading.Event().wait(120)
                raise RuntimeError("parent did not terminate worker")
    app = build_durable_app(root, config["sqlalchemy_url"], config["libpq_dsn"],
                            faults=StopAtCandidate() if mode == "crash" else None)
    await app.checkpoints.open()
    c = app.container
    try:
        if mode == "crash":
            with c.workspace.operation("mutate"):
                c.mutations.initialize_locked()
            conv = await app.service.create_conversation("Restart drill")
            turn = await app.service.prepare_turn(conv.id, "original", "original")
            app.service.finish_run(turn, checkpoint_id_of(turn.config), "completed")
            c.mutations.apply(MutationCommand(kind=CREATE, file_name="A.md", content="owned"),
                Origin(kind="conversation", conversation_id=conv.id), "owned", retrieval=c.model_runtime.snapshot().retrieval)
            c.mutations.apply(MutationCommand(kind=CREATE, file_name="B.md", content="keep"),
                Origin.library(), "other", retrieval=c.model_runtime.snapshot().retrieval)
            preview, plan = await c.recovery.preview(conv.id, turn.user_message_id, "edited")
            await c.recovery.start(preview, "edited", [x.path for x in plan.file_changes], "drill")
        elif mode == "restart":
            # Use the actual application lifespan: maintenance must survive startup.
            from NoteAgent.AppBootstrap.HttpApp import lifespan
            async with lifespan(app.client.app):
                assert c.workspace.maintenance() is not None
                with c.mutations._session_factory() as session:
                    job = session.scalar(select(RecoveryJob).where(RecoveryJob.operation_id == "drill"))
                    job_id = str(job.id)
                job = await c.recovery.retry(job_id, "drill")
                prepared = app.service.claim_prepared(job["prepared_turn_id"])
                async for _ in c.chat_agent.run(prepared):
                    pass
                assert c.workspace.maintenance() is None
                assert not c.notes.exists("A.md") and c.notes.exists("B.md")
                messages = await app.service.list_messages(job["conversation_id"])
                assert [m.content for m in messages] == ["edited", "Recomputed reply"]
                retrieval = c.model_runtime.snapshot().retrieval
                assert not retrieval.is_indexed("A.md")
                assert retrieval.is_indexed("B.md")
                print("RESTART_DRILL_OK", flush=True)
        elif mode == "hold":
            with c.workspace.operation("recovery"):
                (root / "ready.json").write_text("{}", encoding="utf-8")
                threading.Event().wait(120)
        else:
            raise ValueError(mode)
    finally:
        await app.checkpoints.close()
        c.engine.dispose()


if __name__ == "__main__":
    config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    asyncio.run(run(config, sys.argv[2]))
