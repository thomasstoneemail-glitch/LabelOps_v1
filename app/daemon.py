"""Daemon mode: watch client folders and process incoming batches."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import queue
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path

from app import config, file_watcher, logging_utils, pipeline
from app.telegram_ingest_bot import TelegramIngestBot

LOGGER = logging.getLogger(__name__)
DEFAULT_LOG_DIR = r"D:\LabelOps\Logs"
FAILURES_FOLDER_NAME = "FAILURES"


@dataclass
class ClientWatch:
    """Resolved client settings for watch operations."""

    client_id: str
    in_txt: str
    archive: str
    settings: dict


class TelegramRunner:
    """Run the Telegram bot in a dedicated asyncio loop."""

    def __init__(self, token: str) -> None:
        self._bot = TelegramIngestBot(token)
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="telegram-bot", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self._loop or not self._task:
            return

        def _cancel() -> None:
            if self._task and not self._task.done():
                self._task.cancel()

        self._loop.call_soon_threadsafe(_cancel)
        if self._thread:
            self._thread.join(timeout=10)

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._task = self._loop.create_task(self._bot.run())
        try:
            self._loop.run_until_complete(self._task)
        except asyncio.CancelledError:
            pass
        finally:
            self._loop.stop()
            self._loop.close()


class DaemonRunner:
    """Coordinates watchers, queue, and pipeline processing."""

    def __init__(
        self,
        client_watches: list[ClientWatch],
        *,
        use_ai: bool,
        auto_apply_max_risk: str,
        max_ai_calls: int,
        recursive: bool,
        log_dir: str,
    ) -> None:
        self._client_watches = client_watches
        self._use_ai = use_ai
        self._auto_apply_max_risk = auto_apply_max_risk
        self._max_ai_calls = max_ai_calls
        self._recursive = recursive
        self._log_dir = log_dir
        self._queue: queue.Queue[str] = queue.Queue()
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._watcher: file_watcher.WatchService | None = None
        self._processed: set[str] = set()
        self._processed_lock = threading.Lock()

    def start(self) -> None:
        watch_paths = [watch.in_txt for watch in self._client_watches]
        self._watcher = file_watcher.WatchService(
            watch_paths,
            self._enqueue_path,
            recursive=self._recursive,
        )
        self._watcher.start()
        self._worker_thread = threading.Thread(target=self._worker_loop, name="daemon-worker")
        self._worker_thread.start()
        LOGGER.info("Daemon started; watching %s", ", ".join(watch_paths))

    def stop(self) -> None:
        self._stop_event.set()
        if self._watcher:
            self._watcher.stop()
        if self._worker_thread:
            self._worker_thread.join(timeout=10)
        if self._watcher:
            self._watcher.join()
        LOGGER.info("Daemon stopped")

    def _enqueue_path(self, path: str) -> None:
        resolved = str(Path(path))
        if self._already_processed(resolved):
            LOGGER.debug("Skipping duplicate path: %s", resolved)
            return
        self._queue.put(resolved)
        LOGGER.info("Queued file: %s", resolved)

    def _already_processed(self, path: str) -> bool:
        with self._processed_lock:
            if path in self._processed:
                return True
            archive_path = self._find_archive_path(path)
            if archive_path and os.path.exists(archive_path):
                self._processed.add(path)
                return True
        return False

    def _mark_processed(self, path: str) -> None:
        with self._processed_lock:
            self._processed.add(path)

    def _find_archive_path(self, path: str) -> str | None:
        client_watch = self._resolve_client_watch(path)
        if not client_watch:
            return None
        return os.path.join(client_watch.archive, os.path.basename(path))

    def _resolve_client_watch(self, path: str) -> ClientWatch | None:
        path_obj = Path(path)
        for watch in self._client_watches:
            try:
                path_obj.relative_to(Path(watch.in_txt))
                return watch
            except ValueError:
                continue
        return None

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                path = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self._process_path(path)
            finally:
                self._queue.task_done()

    def _process_path(self, path: str) -> None:
        if self._already_processed(path):
            return
        client_watch = self._resolve_client_watch(path)
        if not client_watch:
            LOGGER.warning("No client matched for %s", path)
            return
        if not os.path.exists(path):
            LOGGER.warning("File disappeared before processing: %s", path)
            return

        LOGGER.info("Processing %s for %s", path, client_watch.client_id)
        try:
            raw_text = Path(path).read_text(encoding="utf-8")
            result = pipeline.run_pipeline(
                client_id=client_watch.client_id,
                client_settings=client_watch.settings,
                raw_text=raw_text,
                input_files=[path],
                use_ai=self._use_ai,
                auto_apply_max_risk=self._auto_apply_max_risk,
                max_ai_calls=self._max_ai_calls,
                source="daemon",
                log_dir=self._log_dir,
            )
            LOGGER.info(
                "Processed %s: %s records, outputs=%s",
                path,
                result.get("record_count"),
                result.get("output_xlsx"),
            )
            archived_path = _archive_file(path, client_watch.archive)
            LOGGER.info("Archived input to %s", archived_path)
            self._mark_processed(path)
        except Exception:
            LOGGER.exception("Pipeline failed for %s", path)
            failure_path = _move_to_failures(path, client_watch.client_id)
            _write_failure_details(failure_path)
            self._mark_processed(path)


def _archive_file(source_path: str, archive_dir: str) -> str:
    os.makedirs(archive_dir, exist_ok=True)
    src = Path(source_path)
    destination = Path(archive_dir) / src.name
    if destination.exists():
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        destination = Path(archive_dir) / f"{src.stem}_{timestamp}{src.suffix}"
    return str(src.replace(destination))


def _move_to_failures(source_path: str, client_id: str) -> str:
    failures_dir = Path(r"D:\LabelOps\Clients") / client_id / FAILURES_FOLDER_NAME
    failures_dir.mkdir(parents=True, exist_ok=True)
    src = Path(source_path)
    destination = failures_dir / src.name
    if destination.exists():
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        destination = failures_dir / f"{src.stem}_{timestamp}{src.suffix}"
    try:
        return str(src.replace(destination))
    except FileNotFoundError:
        return str(destination)


def _write_failure_details(failure_path: str) -> None:
    if not failure_path:
        return
    error_path = Path(failure_path).with_suffix(".error.txt")
    error_path.write_text(traceback.format_exc(), encoding="utf-8")


def _parse_bool_flag(value: str) -> bool:
    if value not in {"0", "1"}:
        raise argparse.ArgumentTypeError("Expected 0 or 1")
    return value == "1"


def _parse_clients(value: str) -> list[str]:
    if value.lower() == "all":
        return ["all"]
    clients = [item.strip() for item in value.split(",") if item.strip()]
    if not clients:
        raise argparse.ArgumentTypeError("No clients specified")
    return clients


def _build_client_watches(cfg: dict, client_ids: list[str]) -> list[ClientWatch]:
    if client_ids == ["all"]:
        client_ids = config.list_clients(cfg)
    watches: list[ClientWatch] = []
    for client_id in client_ids:
        settings = config.resolve_client_settings(cfg, client_id)
        folders = settings.get("folders", {})
        in_txt = folders.get("in_txt")
        archive = folders.get("archive")
        if not in_txt or not archive:
            LOGGER.warning("Client %s missing in_txt or archive folder", client_id)
            continue
        Path(in_txt).mkdir(parents=True, exist_ok=True)
        Path(archive).mkdir(parents=True, exist_ok=True)
        watches.append(
            ClientWatch(
                client_id=client_id,
                in_txt=str(in_txt),
                archive=str(archive),
                settings=settings,
            )
        )
    return watches


def _setup_logging(log_dir: str) -> None:
    logging_utils.setup_logging(log_dir)


def _load_config() -> dict:
    cfg = config.load_config()
    config.validate_config(cfg)
    return cfg


def _run_daemon(args: argparse.Namespace) -> int:
    cfg = _load_config()
    client_watches = _build_client_watches(cfg, args.clients)
    if not client_watches:
        LOGGER.error("No valid clients found to watch.")
        return 1

    daemon = DaemonRunner(
        client_watches,
        use_ai=args.use_ai,
        auto_apply_max_risk=args.auto_apply_max_risk,
        max_ai_calls=args.max_ai_calls,
        recursive=args.recursive,
        log_dir=args.log_dir,
    )

    telegram_runner: TelegramRunner | None = None
    if args.use_telegram:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            LOGGER.warning("TELEGRAM_BOT_TOKEN not set; Telegram bot disabled")
        else:
            telegram_runner = TelegramRunner(token)
            telegram_runner.start()

    try:
        daemon.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        LOGGER.info("Shutdown requested")
    finally:
        daemon.stop()
        if telegram_runner:
            telegram_runner.stop()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LabelOps daemon mode")
    parser.add_argument(
        "--clients",
        default="all",
        type=_parse_clients,
        help="Clients to watch: all or comma-separated list (client_01,client_02)",
    )
    parser.add_argument(
        "--use-telegram",
        default="1",
        type=_parse_bool_flag,
        help="Enable Telegram bot polling (0|1)",
    )
    parser.add_argument(
        "--use-ai",
        default="0",
        type=_parse_bool_flag,
        help="Enable AI assistance (0|1)",
    )
    parser.add_argument(
        "--auto-apply-max-risk",
        default="low",
        choices=pipeline.AI_RISK_LEVELS,
        help="Auto-apply max AI risk level",
    )
    parser.add_argument(
        "--max-ai-calls",
        default=50,
        type=int,
        help="Maximum AI calls per batch",
    )
    parser.add_argument(
        "--recursive",
        default="0",
        type=_parse_bool_flag,
        help="Watch folders recursively (0|1)",
    )
    parser.add_argument(
        "--log-dir",
        default=os.getenv("LABELOPS_LOG_DIR", DEFAULT_LOG_DIR),
        help="Directory for logs and manifests",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    _setup_logging(args.log_dir)
    return _run_daemon(args)


if __name__ == "__main__":
    raise SystemExit(main())
