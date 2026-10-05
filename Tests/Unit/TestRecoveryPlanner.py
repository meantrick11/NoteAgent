"""Recovery preview planner: owned-only restore, conflicts, state-only plans."""

from __future__ import annotations

from NoteAgent.ApplicationFlows.ConversationRecovery.RecoveryPlanner import MutationView, plan


def _owned(seq: int, paths, before, kind="write", origin="conversation") -> MutationView:
    return MutationView(
        operation_id=f"op-{origin}-{seq}",
        origin_kind=origin,
        kind=kind,
        paths=list(paths),
        before_hashes=dict(before),
        workspace_seq=seq,
    )


def _plan(**kwargs):
    base = dict(
        conversation_id="c1",
        branch_id="b1",
        state_revision=7,
        workspace_seq=7,
        boundary={"recoverable": True, "files": {"A.md": "hA0"}},
        owned_mutations=[],
        later_mutations=[],
        current_manifest={},
        affected_messages=["m1"],
    )
    base.update(kwargs)
    return plan(**base)


def test_owned_change_only_restores_that_file():
    # This conversation changed A (hA→hA1); another session changed B afterwards.
    result = _plan(
        owned_mutations=[_owned(3, ["A.md"], {"A.md": "hA0"})],
        later_mutations=[_owned(4, ["B.md"], {"B.md": "hB0"}, origin="library")],
        current_manifest={"A.md": "hA1", "B.md": "hB1"},
    )
    assert result.can_apply
    assert result.requires_confirmation
    assert [c.path for c in result.file_changes] == ["A.md"]
    assert result.file_changes[0].action == "restore"
    assert result.file_changes[0].target_hash == "hA0"
    # B is untouched by the plan.
    assert all(c.path != "B.md" for c in result.file_changes)


def test_later_change_to_same_file_is_a_conflict():
    result = _plan(
        owned_mutations=[_owned(3, ["A.md"], {"A.md": "hA0"})],
        later_mutations=[_owned(4, ["A.md"], {"A.md": "hA1"}, origin="library")],
        current_manifest={"A.md": "hA2"},
    )
    assert not result.can_apply
    assert result.conflicts and result.conflicts[0].path == "A.md"


def test_aba_write_back_of_same_bytes_is_still_a_conflict():
    # A later op wrote the *same* bytes back; the bytes match, but it is someone else's
    # operation on our path, so the whole plan is refused.
    result = _plan(
        owned_mutations=[_owned(3, ["A.md"], {"A.md": "hA0"})],
        later_mutations=[_owned(4, ["A.md"], {"A.md": "hA1"}, origin="external")],
        current_manifest={"A.md": "hA1"},
    )
    assert not result.can_apply
    assert result.conflicts[0].reason.startswith("changed after the boundary")


def test_move_into_an_affected_folder_conflicts():
    result = _plan(
        owned_mutations=[_owned(3, ["Python/"], {}, kind="folder_create")],
        later_mutations=[_owned(4, ["Python/other.md"], {"Python/other.md": None}, origin="library")],
        current_manifest={"Python/other.md": "hX"},
        boundary={"recoverable": True, "files": {}},
    )
    assert not result.can_apply


def test_untracked_content_in_restored_folder_conflicts():
    result = _plan(
        owned_mutations=[_owned(3, ["Python/"], {}, kind="folder_create")],
        current_manifest={"Python/extra.md": "hZ"},
        boundary={"recoverable": True, "files": {}},
    )
    assert not result.can_apply
    assert any("untracked" in c.reason for c in result.conflicts)


def test_no_formal_writes_allows_state_only_restore():
    result = _plan(owned_mutations=[], current_manifest={"A.md": "hA1"})
    assert result.can_apply
    assert result.requires_confirmation is False
    assert result.file_changes == []


def test_imported_history_is_not_recoverable():
    result = _plan(boundary={"recoverable": False, "files": {}})
    assert not result.can_apply
    assert result.conflicts[0].reason == "history_not_recoverable"
