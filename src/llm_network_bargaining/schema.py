"""Structured-output format and a forgiving parser that leaves rules to the engine."""

from collections.abc import Mapping
from dataclasses import dataclass
import json
import re
from typing import Any

from .actions import Action
from .names import _name_lookup


def response_format() -> dict[str, Any]:
    """Return a fresh strict JSON schema, without imposing game legality."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "bargaining_action",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["offer", "accept", "pass"]},
                    "to": {"type": ["string", "null"]},
                    "my_points": {"type": ["integer", "null"]},
                    "note": {"type": "string"},
                },
                "required": ["action", "to", "my_points", "note"],
                "additionalProperties": False,
            },
        },
    }


@dataclass(frozen=True)
class ParseResult:
    """An action on node IDs, or a parse error with JSON-ready diagnostics."""

    action: Action | None
    error: str | None
    details: Mapping[str, Any]


def parse_reply(content: str | None, names: Mapping[str, str], *,
                refusal: str | None = None) -> ParseResult:
    """Parse a reply, resolving display names but leaving invalid moves intact.

    Only duplicate names are checked here: a parser has no network or full
    roster. Unknown recipients get a '?' prefix so raw node IDs cannot pass
    as display names. Notes are counted for diagnostics, never truncated.
    """
    lookup = _name_lookup(names)
    if refusal:
        return ParseResult(None, "refusal", {"refusal": refusal})
    if content is None or not content.strip():
        return ParseResult(None, "empty", {})
    text = content.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence is not None:
        text = fence.group(1)
    try:
        data = json.loads(text)
    except ValueError:
        return ParseResult(None, "invalid_json", {})
    if not isinstance(data, dict):
        return ParseResult(None, "not_an_object", {})
    required = ("action", "to", "my_points", "note")
    details: dict[str, Any] = {}
    extras = [key for key in data if key not in required]
    if extras:
        details["extra_keys"] = extras
    missing = [key for key in required if key not in data]
    if missing:
        details["missing"] = missing
        return ParseResult(None, "missing_field", details)
    kind = data["action"]
    if isinstance(kind, str):
        kind = kind.strip().lower()
    raw = data["to"]
    recipient = None
    if raw is not None:
        recipient = lookup.get(raw.strip().casefold()) if isinstance(raw, str) else None
        if recipient is None:
            recipient = "?" + str(raw)
            details["to_raw"] = raw
        elif raw != names[recipient]:
            details["to_raw"] = raw
    note = data["note"] if isinstance(data["note"], str) else None
    words = len(note.split()) if note is not None else 0
    details["note_words"] = words
    details["note_over_limit"] = words > 30
    return ParseResult(Action(kind, recipient, data["my_points"], note), None, details)


def action_to_reply(action: Action | None, names: Mapping[str, str]) -> str:
    """Encode a bot request as compact JSON on display names, or '' for no action."""
    _name_lookup(names)
    if action is None:
        return ""
    recipient = action.to
    if isinstance(recipient, str) and recipient in names:
        recipient = names[recipient]
    data = dict(action=action.kind, to=recipient, my_points=action.my_points,
                note=action.note if action.note is not None else "")
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)
