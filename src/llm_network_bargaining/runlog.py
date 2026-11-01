"""Flushed JSONL attempts, reproducible gzip files and their shared reader."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import re
import shutil
from typing import Any

LOG_SCHEMA = 1
ENGINE_EVENTS = {"episode_start", "phase_start", "turn", "offer", "offer_status",
                 "deal", "round_end", "episode_end"}


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp; writers accept a replacement clock."""
    return datetime.now(timezone.utc)


def episode_path(folder: str | Path, index: int, *, status: str = "completed",
                 attempt: int = 1) -> Path:
    """Return a completed, failed, partial or archived-interruption filename."""
    stem = f"episode_{index:03d}"
    if status == "completed":
        suffix = ".jsonl.gz"
    elif status == "failed":
        suffix = f".failed{attempt}.jsonl.gz"
    elif status == "partial":
        suffix = ".partial.jsonl"
    elif status == "interrupted":
        suffix = f".interrupted{attempt}.jsonl.gz"
    else:
        raise ValueError(f"Unknown log status: {status!r}.")
    return Path(folder) / (stem + suffix)


def _compress_partial(source: Path, destination: Path) -> Path:
    """Replace a partial atomically, using a reproducible gzip header."""
    if destination.exists():
        raise FileExistsError(destination)
    temporary = destination.with_name(destination.name + ".tmp")
    try:
        with source.open("rb") as input_file, temporary.open("wb") as output:
            with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as compressed:
                shutil.copyfileobj(input_file, compressed)
        temporary.replace(destination)
        source.unlink()
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def archive_interrupted(folder: str | Path, index: int) -> Path:
    """Retain an interrupted attempt before its episode starts over."""
    folder = Path(folder)
    number = len(list(folder.glob(f"episode_{index:03d}.interrupted*.jsonl.gz"))) + 1
    return _compress_partial(episode_path(folder, index, status="partial"),
                             episode_path(folder, index, status="interrupted", attempt=number))


class EpisodeLogWriter:
    """Write each record immediately; leave a partial file when interrupted."""

    def __init__(self, folder: str | Path, episode_index: int, attempt: int, *,
                 clock: Callable[[], datetime] = utc_now) -> None:
        self.folder = Path(folder)
        self.episode_index = episode_index
        self.attempt = attempt
        self.clock = clock
        self.started = clock()
        self.path = episode_path(folder, episode_index, status="partial")
        self.folder.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("x", encoding="utf-8")

    def write(self, record: dict[str, Any]) -> None:
        """Append a strict JSON object and flush before play continues."""
        text = json.dumps(record, sort_keys=True, ensure_ascii=False, allow_nan=False)
        self._file.write(text + "\n")
        self._file.flush()

    def close(self) -> None:
        """Close the file without discarding interrupted work."""
        self._file.close()

    def finalize(self, status: str) -> Path:
        """Compress atomically with no filename or timestamp in the gzip header."""
        if status not in ("completed", "failed"):
            raise ValueError("Only completed or failed attempts can be finalized.")
        self.close()
        destination = episode_path(self.folder, self.episode_index, status=status, attempt=self.attempt)
        return _compress_partial(self.path, destination)


@dataclass
class LogRecords:
    """Decoded attempt records; failure is the first of any concurrent failures."""

    header: dict[str, Any]
    quizzes: list[dict[str, Any]]
    events: list[dict[str, Any]]
    failure: dict[str, Any] | None
    footer: dict[str, Any] | None
    failures: list[dict[str, Any]] = field(default_factory=list)

    def to_list(self) -> list[dict[str, Any]]:
        """Return the records in their documented order."""
        return ([self.header] if self.header else []) + self.quizzes + self.events + self.failures + (
            [self.footer] if self.footer else [])


def read_log(path: str | Path) -> LogRecords:
    """Read JSONL, tolerating a torn final line only on interrupted attempts."""
    path = Path(path)
    interrupted = path.name.endswith(".partial.jsonl") or bool(re.search(r"\.interrupted\d+\.jsonl\.gz$", path.name))
    opener = gzip.open if path.suffix == ".gz" else open
    # JSON accepts bytes, so even a torn UTF-8 character in the last line can
    # be handled below without losing the earlier complete records.
    with opener(path, "rb") as source:
        lines = source.readlines()
    result = LogRecords({}, [], [], None, None)
    stage = 0  # header, quizzes, events, failures, footer
    for number, line in enumerate(lines, 1):
        try:
            record = json.loads(line)
        except ValueError as exc:
            if interrupted and number == len(lines) and not line.endswith(b"\n"):
                break
            raise ValueError(f"Invalid JSON in {path}, line {number}.") from exc
        if not isinstance(record, dict):
            raise ValueError(f"Expected an object in {path}, line {number}.")
        kind = record.get("type")
        if number == 1 and kind == "header":
            result.header = record
        elif not result.header:
            raise ValueError(f"Missing first header in {path}.")
        elif kind == "quiz" and stage <= 1:
            stage = 1
            result.quizzes.append(record)
        elif kind in ENGINE_EVENTS and stage <= 2:
            stage = 2
            result.events.append(record)
        elif kind == "failure" and stage <= 3:
            stage = 3
            result.failures.append(record)
            if result.failure is None:
                result.failure = record
        elif kind == "footer" and stage <= 3:
            stage = 4
            result.footer = record
        else:
            raise ValueError(f"Unexpected record {kind!r} in {path}, line {number}.")
    if not result.header and not interrupted:
        raise ValueError(f"Missing header in {path}.")
    if path.suffix == ".gz" and not interrupted and result.footer is None:
        raise ValueError(f"Missing footer in finalized log {path}.")
    return result


def find_logs(paths: Iterable[str | Path]) -> list[Path]:
    """Find logs beneath directories or accept explicitly named files, once each."""
    found: set[Path] = set()
    for value in paths:
        path = Path(value)
        if not path.exists():
            raise FileNotFoundError(path)
        candidates = path.rglob("episode_*") if path.is_dir() else [path]
        for candidate in candidates:
            if candidate.is_file() and (candidate.name.endswith(".jsonl.gz") or candidate.name.endswith(".jsonl")):
                found.add(candidate)
    return sorted(found)


def attempt_costs(records: LogRecords) -> dict[str, Any]:
    """Read finalized totals or reconstruct known costs from an interrupted log."""
    from .costs import CostTracker
    from .model_client import Usage

    if records.footer:
        return {name: records.footer[name] for name in ("cost_usd", "cost_by_alias", "usage_by_alias")}
    tracker = CostTracker()
    for record in [*records.quizzes, *records.events, *records.failures]:
        node = record.get("node", record.get("agent"))
        meta = record if record["type"] == "failure" else record.get("meta", {})
        for attempt in meta.get("attempts", []):
            tracker.add(records.header["node_models"][node], Usage(**attempt["usage"]), attempt["cost_usd"])
    totals = tracker.to_dict()
    return dict(cost_usd=tracker.total_usd,
                cost_by_alias={alias: entry["cost_usd"] for alias, entry in totals.items()},
                usage_by_alias={alias: {"calls": entry["calls"], **entry["usage"]} for alias, entry in totals.items()})


def read_attempt_logs(roots: Iterable[str | Path]) -> list[tuple[Path, LogRecords]]:
    """Read attempts once, ignoring a leftover partial already archived as gzip."""
    logs = [(path, read_log(path)) for path in find_logs(roots)]
    archived = {(path.parent, record.header.get("episode_index"), record.header.get("attempt"))
                for path, record in logs if path.suffix == ".gz"}
    return [(path, record) for path, record in logs if record.header and not
            (path.name.endswith(".partial.jsonl") and
             (path.parent, record.header.get("episode_index"), record.header.get("attempt")) in archived)]
