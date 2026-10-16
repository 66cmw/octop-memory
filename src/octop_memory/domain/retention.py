"""Source-based retention rules shared by capture, extraction and recall.

401/timeout keywords do not identify a source: users may discuss these normally.
Only a host marker or the exact legacy retry envelope identifies synthetic output.
User/manual events always remain eligible, even when they quote that envelope.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable

from octop_memory.types import Candidate, RawEvent

MANUAL_DOCUMENTS_META_KEY = "manual_documents/v1"
MANUAL_DOCUMENTS_RECALL_KEY = "manual_documents/recall/v1"


def manual_documents_revision(documents: dict[str, str]) -> str:
    """Revision of the two authoritative documents, including absent files."""
    canonical = {name: documents.get(name, "") for name in ("USER.md", "MEMORY.md")}
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def normalize_manual_fact(text: str) -> str:
    """Remove Markdown bullet/formatting whitespace while preserving factual values."""
    text = re.sub(r"^\s*[-+*]\s+", "", text)
    return " ".join(text.replace("**", "").replace("`", "").split())


EXPLICIT_MEMORY_INTENT_RE = re.compile(
    r"(请记住|帮我记住|记住|记一下|记下来|记到记忆|加入记忆|保存到记忆|remember this|remember that|please remember|"
    r"save this to memory|add this to memory)",
    re.IGNORECASE,
)
_LEGACY_RETRY_FAILURE = re.compile(r"\AModel call failed after [1-9]\d* attempts? with [\w.]+:\s", re.ASCII)
_VERIFIED_LESSON = re.compile(
    r"已验证|验证成功|已解决|已修复|排障经验|verified (?:fix|solution|workaround)|(?:resolved|fixed) by",
    re.IGNORECASE,
)


def is_runtime_error(event: RawEvent) -> bool:
    """Identify synthetic assistant failures without filtering user error reports."""
    if event.event_type != "assistant_message" or event.payload.get("role") == "user":
        return False
    if event.payload.get("octop_runtime_error") is True:
        return True
    # Older hosts lost structured provenance. Be conservative when an assistant
    # quotes the legacy error before explaining a verified fix in the same body.
    return bool(_LEGACY_RETRY_FAILURE.match(event.content)) and not _VERIFIED_LESSON.search(event.content)


def is_runtime_error_candidate(candidate: Candidate, get_raw: Callable[[str], RawEvent | None]) -> bool:
    """True only for automatic candidates demonstrably based on runtime failures.

    A user approval/manual save, explicit user memory request, user quote, or
    another assistant explanation makes a legacy mixed-source record ineligible
    for automatic retirement. Missing/ambiguous provenance is preserved.
    """
    if candidate.decided_by == "user" or candidate.extractor_version.startswith("manual/"):
        return False
    events = {key: get_raw(key) for key in set([*candidate.raw_event_ids, candidate.quote_event_id]) if key}
    if not events or any(event is None for event in events.values()):
        return False
    sources = [event for event in events.values() if event is not None]
    for event in sources:
        if event.event_type in {"manual", "host_memory_write"}:
            return False
        if event.event_type == "user_message" and EXPLICIT_MEMORY_INTENT_RE.search(event.content):
            return False
        if event.event_type == "assistant_message" and not is_runtime_error(event):
            return False
    quote = events.get(candidate.quote_event_id)
    return is_runtime_error(quote) if quote is not None else all(is_runtime_error(event) for event in sources)
