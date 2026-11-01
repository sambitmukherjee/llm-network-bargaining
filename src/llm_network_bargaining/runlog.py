"""Flushed JSONL attempts, reproducible gzip files and their shared reader."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
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
    """Return one of the three documented filenames within a condition folder."""
    stem = f"episode_{index:03d}"
    if status == "completed":
        suffix = ".jsonl.gz"
    elif status == "failed":
        suffix = f".failed{attempt}.jsonl.gz"
    elif status == "partial":
        suffix = ".partial.jsonl"
    else:
        raise ValueError(f"Unknown log status: {status!r}.")
    return Path(folder) / (stem + suffix)


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
        if destination.exists():
            raise FileExistsError(destination)
        temporary = destination.with_name(destination.name + ".tmp")
        try:
            with self.path.open("rb") as source, temporary.open("wb") as output:
                with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as compressed:
                    shutil.copyfileobj(source, compressed)
            temporary.replace(destination)
            self.path.unlink()
        finally:
            temporary.unlink(missing_ok=True)
        return destination


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
    """Read gzip or plain JSONL; tolerate only a torn final line in a partial file."""
    path = Path(path)
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
            if path.name.endswith(".partial.jsonl") and number == len(lines) and not line.endswith(b"\n"):
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
    if not result.header and not path.name.endswith(".partial.jsonl"):
        raise ValueError(f"Missing header in {path}.")
    if path.suffix == ".gz" and result.footer is None:
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
