"""Structured capability records and their state transitions.

A record distinguishes three questions the old profile schema conflated:

- is the capability enabled for use (``status``),
- did a probe or the user establish it (``verification`` / ``source``),
- is the evidence still current (``probe_version`` / ``checked_at``).
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

CapabilityName = Literal[
    "text",
    "vision",
    "tool_calling",
    "streaming",
    "json_mode",
    "reasoning",
]
CapabilityStatus = Literal["enabled", "disabled"]
VerificationStatus = Literal["unverified", "verified", "failed"]
CapabilitySource = Literal["manual", "probe"]

TEXT_PROBE_VERSION = 1
VISION_PROBE_VERSION = 1


class CapabilityRecord(BaseModel):
    """One capability row for one model configuration."""

    capability: CapabilityName
    status: CapabilityStatus = "enabled"
    verification: VerificationStatus = "unverified"
    source: CapabilitySource = "manual"
    checked_at: datetime | None = None
    probe_version: int | None = None
    evidence: dict[str, object] | None = None

    def is_usable(self, probe_version: int) -> bool:
        """True only when enabled, verified, and the evidence version is current."""
        return (
            self.status == "enabled"
            and self.verification == "verified"
            and self.probe_version == probe_version
        )


def initial_capabilities() -> list[CapabilityRecord]:
    """A new model starts with text declared but unverified."""
    return [CapabilityRecord(capability="text")]


def find_capability(
    records: list[CapabilityRecord], capability: CapabilityName
) -> CapabilityRecord | None:
    """Return the record for one capability, if it exists."""
    for record in records:
        if record.capability == capability:
            return record
    return None


def _replace(
    records: list[CapabilityRecord], record: CapabilityRecord
) -> list[CapabilityRecord]:
    """Replace one capability, appending it when it is not declared yet."""
    for index, existing in enumerate(records):
        if existing.capability == record.capability:
            updated = list(records)
            updated[index] = record
            return updated
    return [*records, record]


def text_verified(
    records: list[CapabilityRecord],
    *,
    evidence: dict[str, object],
    checked_at: datetime,
    probe_version: int = TEXT_PROBE_VERSION,
) -> list[CapabilityRecord]:
    """Record a passed text probe (streaming + tool calling)."""
    record = CapabilityRecord(
        capability="text",
        status="enabled",
        verification="verified",
        source="probe",
        checked_at=checked_at,
        probe_version=probe_version,
        evidence=evidence,
    )
    return _replace(records, record)


def text_failed(
    records: list[CapabilityRecord],
    *,
    evidence: dict[str, object],
    checked_at: datetime,
    probe_version: int = TEXT_PROBE_VERSION,
) -> list[CapabilityRecord]:
    """Record a failed text probe without enabling the model."""
    record = CapabilityRecord(
        capability="text",
        status="enabled",
        verification="failed",
        source="probe",
        checked_at=checked_at,
        probe_version=probe_version,
        evidence=evidence,
    )
    return _replace(records, record)


def vision_verified(
    records: list[CapabilityRecord],
    *,
    evidence: dict[str, object],
    checked_at: datetime,
    probe_version: int = VISION_PROBE_VERSION,
) -> list[CapabilityRecord]:
    """Record a passed two-round image challenge."""
    record = CapabilityRecord(
        capability="vision",
        status="enabled",
        verification="verified",
        source="probe",
        checked_at=checked_at,
        probe_version=probe_version,
        evidence=evidence,
    )
    return _replace(records, record)


def vision_failed(
    records: list[CapabilityRecord],
    *,
    evidence: dict[str, object],
    checked_at: datetime,
    probe_version: int = VISION_PROBE_VERSION,
) -> list[CapabilityRecord]:
    """Record a failed image challenge."""
    record = CapabilityRecord(
        capability="vision",
        status="enabled",
        verification="failed",
        source="probe",
        checked_at=checked_at,
        probe_version=probe_version,
        evidence=evidence,
    )
    return _replace(records, record)


def disable_capability(
    records: list[CapabilityRecord], capability: CapabilityName
) -> list[CapabilityRecord]:
    """Pause a capability.

    Text keeps its verification so re-enabling does not force a re-probe (the
    previous user-facing behavior). Vision clears its evidence so re-enabling
    always requires a new image probe.
    """
    record = find_capability(records, capability)
    if record is None:
        return records
    if capability == "vision":
        record = record.model_copy(
            update={
                "status": "disabled",
                "verification": "unverified",
                "checked_at": None,
                "probe_version": None,
                "evidence": None,
            }
        )
    else:
        record = record.model_copy(update={"status": "disabled"})
    return _replace(records, record)


def enable_capability(
    records: list[CapabilityRecord], capability: CapabilityName
) -> list[CapabilityRecord]:
    """Mark a capability enabled without inventing verification evidence."""
    record = find_capability(records, capability)
    if record is None:
        return records
    return _replace(records, record.model_copy(update={"status": "enabled"}))


def invalidate_capabilities(
    records: list[CapabilityRecord],
) -> list[CapabilityRecord]:
    """Drop verification evidence after connection or model identity changes."""
    return [
        record.model_copy(
            update={
                "verification": "unverified",
                "checked_at": None,
                "probe_version": None,
                "evidence": None,
            }
        )
        for record in records
    ]


def text_ready(records: list[CapabilityRecord]) -> bool:
    """Whether the model may serve chat requests."""
    record = find_capability(records, "text")
    return record is not None and record.is_usable(TEXT_PROBE_VERSION)


def vision_ready(records: list[CapabilityRecord]) -> bool:
    """Whether the model may parse images or image-only PDF pages."""
    record = find_capability(records, "vision")
    return record is not None and record.is_usable(VISION_PROBE_VERSION)
