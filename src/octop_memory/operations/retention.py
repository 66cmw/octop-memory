"""Preview or softly retire automatic memories sourced from synthetic failures.

No raw evidence is modified or removed. Capture/extraction/recall share the
retention classifier, so the preserved diagnostics cannot re-enter via fallback.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from octop_memory.domain.retention import is_runtime_error_candidate
from octop_memory.types import JournalEntry

if TYPE_CHECKING:
    from octop_memory.core import Memory

_SCAN_LIMIT = 2_147_483_647
_REASON = "Runtime error retention audit: synthetic failure, no durable user-confirmed knowledge."


@dataclass
class RuntimeErrorAudit:
    """IDs are a review manifest; counts describe mutations actually applied."""

    atoms_scanned: int = 0
    candidates_scanned: int = 0
    atom_ids: list[str] = field(default_factory=list)
    candidate_ids: list[str] = field(default_factory=list)
    atoms_deprecated: int = 0
    candidates_rejected: int = 0


def audit_runtime_errors(memory: Memory, *, apply: bool = False) -> RuntimeErrorAudit:
    """Default to preview; ``apply`` soft-deprecates only proven automatic errors.

    Approved/manual/user-edited/explicitly requested and ambiguous mixed-source
    memories are protected. Re-running is idempotent. Uses existing backend
    contracts and one transaction, identically on SQLite and PostgreSQL.
    """
    report = RuntimeErrorAudit()
    with memory.backend.transaction():
        edited_ids = {entry.target_atom_id for entry in memory.list_journal(action="user_edit", limit=_SCAN_LIMIT)}
        atoms = memory.list_atoms(limit=_SCAN_LIMIT)
        report.atoms_scanned = len(atoms)
        for atom in atoms:
            if atom.id in edited_ids:
                continue
            candidate = memory.get_candidate(atom.candidate_id)
            if candidate is None or not is_runtime_error_candidate(candidate, memory.get_raw):
                continue
            # A mismatch is evidence of editing/import drift; never infer from
            # the old candidate that the current assertion is still an error.
            if atom.assertion != candidate.assertion or atom.quote_event_id != candidate.quote_event_id:
                continue
            report.atom_ids.append(atom.id)
            if apply and memory.deprecate_atom(atom.id, actor="rule", note=_REASON):
                report.atoms_deprecated += 1

        candidates = memory.list_candidates(limit=_SCAN_LIMIT)
        report.candidates_scanned = len(candidates)
        for candidate in candidates:
            if candidate.status not in {"pending", "needs_review", "conflict"}:
                continue
            if not is_runtime_error_candidate(candidate, memory.get_raw):
                continue
            report.candidate_ids.append(candidate.id)
            if apply:
                now = datetime.now(UTC)
                if memory.update_candidate_status(
                    candidate.id,
                    status="rejected",
                    decided_by="rule",
                    decided_at=now,
                    promotion_reason=_REASON,
                ):
                    report.candidates_rejected += 1
                    memory.append_journal(
                        JournalEntry(
                            id=str(uuid.uuid4()),
                            timestamp=now,
                            action="reject",
                            actor="rule",
                            target_candidate_id=candidate.id,
                            note=_REASON,
                        )
                    )
    return report
