"""Execute an accepted turn from its exact checkpoint and publish via CAS."""

import asyncio
from contextlib import aclosing, suppress

from NoteAgent.BusinessModules.ChatAgent.ChatGraph import stream_graph
from NoteAgent.BusinessModules.ConversationState.ConversationCheckpoints import checkpoint_id_of
from NoteAgent.BusinessModules.ConversationState.TurnLeases import HEARTBEAT_SECONDS


async def execute_turn(graph, service, prepared, *, resume=False):
    """Never infer the run's head from another run's newest saver checkpoint."""
    config = prepared.config

    async def heartbeat():
        while True:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            service.refresh_run_lease(prepared)

    async def checkpoint(saved):
        nonlocal config
        await service.record_run_checkpoint(prepared, saved)
        config = saved

    service.refresh_run_lease(prepared)
    pulse = asyncio.create_task(heartbeat())
    try:
        inputs = {}
        if resume:
            snapshot = await graph.aget_state(config)
            # Accepted-but-never-started checkpoints have no graph tasks. A
            # genuinely interrupted node resumes with None; a completed graph
            # awaiting publication must only publish, never rerun the model.
            if snapshot.next or snapshot.values.get("run_status") in ("completed", "failed"):
                inputs = None
        stream = stream_graph(graph, inputs, config, on_checkpoint=checkpoint)
        async with aclosing(stream):
            async for event in stream:
                if pulse.done():
                    pulse.result()
                yield event
        # Exhausting astream also waits for checkpoint writes to complete.
        state = await service.read_state(config)
        service.finish_run(prepared, checkpoint_id_of(config), state.values["run_status"])
    except BaseException:
        # aclosing above has awaited graph cleanup before releasing ownership.
        service.interrupt_run(prepared)
        raise
    finally:
        pulse.cancel()
        with suppress(asyncio.CancelledError):
            await pulse
