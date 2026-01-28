"""
Watch-folder service for new .txt files.

Setup:
    pip install watchdog

Demo:
    python -m app.file_watcher
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable

from watchdog.events import FileSystemEventHandler, FileSystemEvent, FileMovedEvent
from watchdog.observers import Observer

STABLE_CHECKS = 3
STABLE_DELAY = 0.4
STABLE_TIMEOUT = 10.0
RECENT_TTL_SECONDS = 300.0
RECENT_MAX = 500

logger = logging.getLogger(__name__)


@dataclass
class _RecentPaths:
    ttl_seconds: float = RECENT_TTL_SECONDS
    max_entries: int = RECENT_MAX

    def __post_init__(self) -> None:
        self._items: OrderedDict[str, float] = OrderedDict()
        self._lock = threading.Lock()

    def seen(self, path: str) -> bool:
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            return path in self._items

    def add(self, path: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._items[path] = now
            self._items.move_to_end(path)
            self._prune(now)

    def _prune(self, now: float) -> None:
        expired = [p for p, ts in self._items.items() if now - ts > self.ttl_seconds]
        for p in expired:
            self._items.pop(p, None)
        while len(self._items) > self.max_entries:
            self._items.popitem(last=False)


class WatchService:
    """Watch one or more folders and call a callback when new .txt files arrive."""

    def __init__(
        self,
        paths: list[str],
        on_file: Callable[[str], None],
        recursive: bool = False,
    ) -> None:
        if not paths:
            raise ValueError("paths must not be empty")
        self._paths = [str(Path(p)) for p in paths]
        self._on_file = on_file
        self._recursive = recursive
        self._observer = Observer()
        self._recent = _RecentPaths()
        self._handler = _WatchHandler(self._handle_path)

    def start(self) -> None:
        for path in self._paths:
            self._observer.schedule(self._handler, path, recursive=self._recursive)
        self._observer.start()
        logger.info("WatchService started for %s", ", ".join(self._paths))

    def stop(self) -> None:
        self._observer.stop()
        logger.info("WatchService stopping")

    def join(self) -> None:
        self._observer.join()
        logger.info("WatchService stopped")

    def _handle_path(self, path: str) -> None:
        if not _is_valid_txt(path):
            return
        if self._recent.seen(path):
            return
        if _wait_for_stable(path):
            self._recent.add(path)
            logger.info("Processing file: %s", path)
            try:
                self._on_file(path)
            except Exception:
                logger.exception("Error processing file: %s", path)
        else:
            logger.warning("File never became stable: %s", path)


class _WatchHandler(FileSystemEventHandler):
    def __init__(self, on_path: Callable[[str], None]) -> None:
        self._on_path = on_path

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._on_path(event.src_path)

    def on_moved(self, event: FileMovedEvent) -> None:
        if event.is_directory:
            return
        self._on_path(event.dest_path)


def _is_valid_txt(path: str) -> bool:
    name = Path(path).name
    lower = name.lower()
    if lower.endswith((".tmp", ".part")):
        return False
    if lower.endswith("~") or lower.startswith("~"):
        return False
    if not lower.endswith(".txt"):
        return False
    return True


def _wait_for_stable(path: str) -> bool:
    start = time.monotonic()
    last_size: int | None = None
    stable_hits = 0
    while time.monotonic() - start < STABLE_TIMEOUT:
        try:
            size = os.path.getsize(path)
        except FileNotFoundError:
            time.sleep(STABLE_DELAY)
            continue
        if _can_open_exclusive(path):
            return True
        if last_size is None or size != last_size:
            stable_hits = 0
            last_size = size
        else:
            stable_hits += 1
            if stable_hits >= STABLE_CHECKS:
                return True
        time.sleep(STABLE_DELAY)
    return False


def _can_open_exclusive(path: str) -> bool:
    try:
        if os.name == "nt":
            import msvcrt

            with open(path, "rb") as handle:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    return True
                except OSError:
                    return False
        else:
            with open(path, "rb"):
                return True
    except OSError:
        return False


def _simulate_drop(target_dir: Path) -> Path:
    staging = target_dir.parent / "STAGING"
    staging.mkdir(parents=True, exist_ok=True)
    tmp_path = staging / "incoming.txt"
    final_path = target_dir / "incoming.txt"
    tmp_path.write_text("Hello from watcher demo.\n", encoding="utf-8")
    time.sleep(0.1)
    tmp_path.replace(final_path)
    return final_path


def _run_demo() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with TemporaryDirectory() as tmp_root:
        in_txt = Path(tmp_root) / "IN_TXT"
        in_txt.mkdir(parents=True, exist_ok=True)

        def on_file(path: str) -> None:
            print(f"Demo received: {path}")

        service = WatchService([str(in_txt)], on_file)
        service.start()
        try:
            _simulate_drop(in_txt)
            time.sleep(2)
        finally:
            service.stop()
            service.join()


if __name__ == "__main__":
    _run_demo()
