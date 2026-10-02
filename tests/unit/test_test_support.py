"""The test doubles must actually hold their contracts before tests rely on them."""

import pytest

from support.fakes import FAULT_STAGES, FailInjector


def test_fake_embedder_is_deterministic(fake_embedder):
    first = fake_embedder.embed_documents(["alpha", "beta"])
    second = fake_embedder.embed_documents(["alpha", "beta"])
    assert first == second
    assert first[0] != first[1]
    assert fake_embedder.embed_query("alpha") == first[0]
    assert all(len(vector) == 32 for vector in first)


def test_fail_injector_fires_exactly_once(fail_stage):
    injector = FailInjector()
    injector.inject("index_rebuilt")

    injector.check("file_applied")  # untouched stage is a no-op
    with pytest.raises(RuntimeError, match="index_rebuilt"):
        injector.check("index_rebuilt")
    injector.check("index_rebuilt")  # consumed: second call passes
    assert injector.pending("index_rebuilt") == 0


def test_fail_injector_keeps_queued_faults_in_order(fail_stage):
    injector = FailInjector()
    injector.inject("git_committed", ValueError("first"))
    injector.inject("git_committed", ValueError("second"))

    with pytest.raises(ValueError, match="first"):
        injector.check("git_committed")
    assert injector.pending("git_committed") == 1
    with pytest.raises(ValueError, match="second"):
        injector.check("git_committed")


def test_fail_injector_rejects_unknown_stage(fail_stage):
    with pytest.raises(ValueError, match="unknown fault stage"):
        fail_stage.inject("no_such_stage")


def test_fault_stages_match_recovery_protocol():
    assert FAULT_STAGES == (
        "file_applied",
        "git_committed",
        "index_rebuilt",
        "candidate_saved",
        "before_publish",
        "after_publish",
    )
