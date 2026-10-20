"""Capability state machine tests, independent of storage and providers."""

from datetime import UTC, datetime

from NoteAgent.Modules.Models.Domain.Vo.ModelCapabilities import (
    TEXT_PROBE_VERSION,
    VISION_PROBE_VERSION,
    CapabilityRecord,
    disable_capability,
    enable_capability,
    find_capability,
    initial_capabilities,
    invalidate_capabilities,
    text_failed,
    text_ready,
    text_verified,
    vision_failed,
    vision_ready,
    vision_verified,
)

NOW = datetime(2026, 10, 20, tzinfo=UTC)


def test_initial_model_only_declares_text():
    records = initial_capabilities()
    text = find_capability(records, "text")
    assert text is not None
    assert text.status == "enabled"
    assert text.verification == "unverified"
    assert not text_ready(records)


def test_text_verification_enables_chat_and_records_evidence():
    records = text_verified(initial_capabilities(), evidence={"streaming": True, "tool_calling": True}, checked_at=NOW)
    text = find_capability(records, "text")
    assert text.verification == "verified"
    assert text.probe_version == TEXT_PROBE_VERSION
    assert text.evidence == {"streaming": True, "tool_calling": True}
    assert text_ready(records)


def test_text_probe_version_mismatch_is_not_usable():
    records = [
        CapabilityRecord(
            capability="text",
            verification="verified",
            probe_version=TEXT_PROBE_VERSION - 1,
        )
    ]
    assert not text_ready(records)


def test_failed_text_probe_does_not_enable_chat():
    records = text_failed(initial_capabilities(), evidence={"streaming": False}, checked_at=NOW)
    text = find_capability(records, "text")
    assert text.verification == "failed"
    assert not text_ready(records)


def test_disabling_text_keeps_verification_but_blocks_chat():
    records = text_verified(initial_capabilities(), evidence={"streaming": True}, checked_at=NOW)
    records = disable_capability(records, "text")
    text = find_capability(records, "text")
    assert text.status == "disabled"
    assert text.verification == "verified"
    assert not text_ready(records)


def test_enabling_text_again_does_not_require_reprobe():
    records = text_verified(initial_capabilities(), evidence={"streaming": True}, checked_at=NOW)
    records = disable_capability(records, "text")
    records = enable_capability(records, "text")
    assert text_ready(records)


def test_vision_verification_and_disable_clear_evidence():
    records = text_verified(initial_capabilities(), evidence={"streaming": True}, checked_at=NOW)
    records = vision_verified(records, evidence={"challenge": "2x6"}, checked_at=NOW)
    assert vision_ready(records)
    records = disable_capability(records, "vision")
    vision = find_capability(records, "vision")
    assert vision.status == "disabled"
    assert vision.verification == "unverified"
    assert vision.checked_at is None
    assert vision.probe_version is None
    assert vision.evidence is None
    assert not vision_ready(records)


def test_vision_failure_does_not_enable_vision():
    records = vision_failed(initial_capabilities(), evidence={"challenge": "failed"}, checked_at=NOW)
    assert not vision_ready(records)


def test_connection_change_invalidates_all_evidence_but_keeps_status():
    records = text_verified(initial_capabilities(), evidence={"streaming": True}, checked_at=NOW)
    records = vision_verified(records, evidence={"challenge": "2x6"}, checked_at=NOW)
    records = disable_capability(records, "vision")
    records = invalidate_capabilities(records)
    for record in records:
        assert record.verification == "unverified"
        assert record.checked_at is None
        assert record.probe_version is None
        assert record.evidence is None
    assert find_capability(records, "vision").status == "disabled"
    assert not text_ready(records)


def test_vision_probe_version_is_independent_from_text():
    records = text_verified(initial_capabilities(), evidence={"streaming": True}, checked_at=NOW)
    records = vision_verified(
        records,
        evidence={"challenge": "2x6"},
        checked_at=NOW,
        probe_version=VISION_PROBE_VERSION,
    )
    assert text_ready(records)
    assert vision_ready(records)
