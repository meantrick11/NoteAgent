"""Isolated real HTTP backend for the browser's explicit-resume regression."""
import asyncio
import socket
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from support.webapp import build_checkpoint_app


async def seed_edit(app):
    from noteagent.conversations.checkpoints import checkpoint_id_of
    from noteagent.notes.mutations import CREATE, MutationCommand, Origin
    conv = await app.service.create_conversation("Editable browser test")
    prepared = await app.service.prepare_turn(conv.id, "original question", "edit-original")
    app.service.finish_run(prepared, checkpoint_id_of(prepared.config), "completed")
    app.container.mutations.apply(MutationCommand(kind=CREATE, file_name="A.md", content="owned"),
        Origin(kind="conversation", conversation_id=conv.id), "owned",
        retrieval=app.container.model_runtime.snapshot().retrieval)


async def seed(app):
    conv = await app.service.create_conversation("Interrupted browser test")
    prepared = await app.service.prepare_turn(conv.id, "browser question", "browser-resume")
    app.service.interrupt_run(prepared)


if __name__ == "__main__":
    with TemporaryDirectory(prefix="noteagent-browser-resume-") as root:
        if "--edit" in sys.argv:
            from support.durable_app import build_durable_app
            app = build_durable_app(Path(root))
            asyncio.run(seed_edit(app))
        else:
            app = build_checkpoint_app(Path(root), reply_batches=[["Recovered reply"]])
            asyncio.run(seed(app))
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        config = uvicorn.Config(app.client.app, log_level="error")
        print(f"REVIEW_SERVER http://127.0.0.1:{sock.getsockname()[1]}", flush=True)
        try:
            uvicorn.Server(config).run(sockets=[sock])
        finally:
            sock.close()
            app.container.engine.dispose()
