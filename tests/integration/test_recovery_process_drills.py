"""Real worker termination/restart and cross-process advisory lock acceptance."""
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from noteagent.db import create_engine_from_url, create_session_factory
from noteagent.recovery.gate import WorkspaceBusy, WorkspaceGate

WORKER = Path(__file__).resolve().parents[1] / "support" / "recovery_worker.py"


def launch(tmp_path, pg_target, mode):
    config = tmp_path / "worker-config.json"
    config.write_text(json.dumps({"root": str(tmp_path), "sqlalchemy_url": pg_target.sqlalchemy_url,
                                 "libpq_dsn": pg_target.libpq_dsn}), encoding="utf-8")
    process = subprocess.Popen([sys.executable, str(WORKER), str(config), mode],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 60
    while not (tmp_path / "ready.json").exists():
        if process.poll() is not None:
            _, err = process.communicate()
            pytest.fail(f"worker exited before ready: {err[-1800:]}")
        if time.monotonic() > deadline:
            process.kill(); process.communicate()
            pytest.fail("worker ready timeout")
        time.sleep(0.05)
    return process, config


def test_live_worker_kill_and_restart_preserves_recovery(pg_target, tmp_path):
    process, config = launch(tmp_path, pg_target, "crash")
    process.kill(); process.communicate(timeout=10)
    restarted = subprocess.run([sys.executable, str(WORKER), str(config), "restart"],
        capture_output=True, text=True, timeout=60)
    assert restarted.returncode == 0, restarted.stderr[-2400:]
    assert "RESTART_DRILL_OK" in restarted.stdout


def test_two_processes_refuse_chat_write_and_rebuild(pg_target, tmp_path):
    process, _ = launch(tmp_path, pg_target, "hold")
    engine = create_engine_from_url(pg_target.sqlalchemy_url)
    gate = WorkspaceGate(create_session_factory(engine), libpq_dsn=pg_target.libpq_dsn)
    try:
        for mode in ("read", "chat", "mutate", "model_rebuild", "recovery"):
            with pytest.raises(WorkspaceBusy):
                with gate.operation(mode):
                    pass
        process.kill(); process.communicate(timeout=10)
        with gate.operation("chat"):
            pass
    finally:
        if process.poll() is None:
            process.kill(); process.communicate(timeout=10)
        engine.dispose()
