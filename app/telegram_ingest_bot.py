"""Telegram ingestion bot for LabelOps (polling mode)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

ALLOWLIST_PATH = Path(r"D:\LabelOps\config\telegram_allowlist.json")
CLIENTS_ROOT = Path(r"D:\LabelOps\Clients")
DEFAULT_CLIENT_ID = "client_01"
CLIENT_ID_PATTERN = re.compile(r"^client_\d{2}$", re.IGNORECASE)

LOGGER = logging.getLogger(__name__)


@dataclass
class AllowlistConfig:
    """Allowlist configuration loaded from disk."""

    allowed_chat_ids: List[int]
    default_client_by_chat: Dict[str, str]

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "AllowlistConfig":
        return cls(
            allowed_chat_ids=[int(value) for value in payload.get("allowed_chat_ids", [])],
            default_client_by_chat={
                str(chat_id): str(client_id)
                for chat_id, client_id in payload.get("default_client_by_chat", {}).items()
            },
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed_chat_ids": self.allowed_chat_ids,
            "default_client_by_chat": self.default_client_by_chat,
        }


class AllowlistStore:
    """Thread-safe allowlist store backed by JSON on disk."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()

    async def load(self) -> AllowlistConfig:
        async with self._lock:
            return self._load_sync()

    async def save(self, config: AllowlistConfig) -> None:
        async with self._lock:
            self._save_sync(config)

    def _load_sync(self) -> AllowlistConfig:
        if not self._path.exists():
            self._create_empty_config()
        try:
            with self._path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            return AllowlistConfig.from_dict(payload)
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            LOGGER.error("Failed to read allowlist config: %s", exc)
            self._create_empty_config()
            return AllowlistConfig(allowed_chat_ids=[], default_client_by_chat={})

    def _save_sync(self, config: AllowlistConfig) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as handle:
            json.dump(config.to_dict(), handle, indent=2)

    def _create_empty_config(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "allowed_chat_ids": [],
            "default_client_by_chat": {},
            "instructions": "Add numeric chat IDs to allowed_chat_ids to permit ingestion.",
        }
        with self._path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)


class TelegramIngestBot:
    """Telegram ingestion bot that writes orders to IN_TXT folders."""

    def __init__(self, token: str) -> None:
        self._store = AllowlistStore(ALLOWLIST_PATH)
        self._application = Application.builder().token(token).build()
        self._register_handlers()

    def _register_handlers(self) -> None:
        self._application.add_handler(CommandHandler("start", self._handle_start))
        self._application.add_handler(CommandHandler("help", self._handle_help))
        self._application.add_handler(CommandHandler("status", self._handle_status))
        self._application.add_handler(CommandHandler("chatid", self._handle_chatid))
        self._application.add_handler(CommandHandler("setclient", self._handle_setclient))
        self._application.add_handler(CommandHandler("clients", self._handle_clients))
        self._application.add_handler(MessageHandler(filters.TEXT, self._handle_text))
        self._application.add_handler(
            MessageHandler(filters.PHOTO | filters.Document.ALL, self._handle_media)
        )

    async def run(self) -> None:
        """Start polling for updates."""
        LOGGER.info("Starting Telegram ingestion bot")
        await self._store.load()
        await self._application.initialize()
        await self._application.start()
        await self._application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        try:
            await self._application.updater.wait()
        finally:
            await self._application.updater.stop()
            await self._application.stop()
            await self._application.shutdown()

    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not await self._is_allowlisted(update):
            return
        message = (
            "LabelOps Telegram ingest bot. Send text-only orders. "
            "Optional first line: client_01."
        )
        await update.message.reply_text(message)

    async def _handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._handle_start(update, context)

    async def _handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not await self._is_allowlisted(update):
            return
        config = await self._store.load()
        clients = self._discover_clients()
        response = (
            "Bot running. "
            f"Allowlisted chats: {len(config.allowed_chat_ids)}. "
            f"Clients: {', '.join(clients) if clients else 'None found'}."
        )
        await update.message.reply_text(response)

    async def _handle_clients(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not await self._is_allowlisted(update):
            return
        clients = self._discover_clients()
        message = "\n".join(clients) if clients else "No client folders found."
        await update.message.reply_text(message)

    async def _handle_chatid(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not await self._is_allowlisted(update):
            return
        chat_id = update.effective_chat.id if update.effective_chat else None
        if chat_id is None:
            return
        await update.message.reply_text(str(chat_id))

    async def _handle_setclient(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._is_allowlisted(update):
            return
        if not context.args:
            await update.message.reply_text("Usage: /setclient client_01")
            return
        client_id = context.args[0].strip()
        if not CLIENT_ID_PATTERN.match(client_id):
            await update.message.reply_text("Invalid client ID. Use client_01 format.")
            return
        chat_id = update.effective_chat.id if update.effective_chat else None
        if chat_id is None:
            return
        config = await self._store.load()
        config.default_client_by_chat[str(chat_id)] = client_id.lower()
        await self._store.save(config)
        await update.message.reply_text(f"Default client set to {client_id.lower()}.")

    async def _handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not await self._is_allowlisted(update):
            return
        if not update.message or update.message.text is None:
            return
        raw_text = update.message.text.strip()
        if not raw_text:
            return
        chat_id = update.effective_chat.id if update.effective_chat else None
        if chat_id is None:
            return
        config = await self._store.load()
        client_id, content = self._route_message(raw_text, chat_id, config)
        filename = self._write_message(client_id, chat_id, content)
        await update.message.reply_text(f"Saved for {client_id}: {filename}")

    async def _handle_media(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not await self._is_allowlisted(update):
            return
        if update.message:
            await update.message.reply_text("Text only, paste addresses as text.")

    async def _is_allowlisted(self, update: Update) -> bool:
        chat_id = update.effective_chat.id if update.effective_chat else None
        if chat_id is None:
            return False
        config = await self._store.load()
        if chat_id not in config.allowed_chat_ids:
            LOGGER.info("Ignored message from chat_id=%s (not allowlisted)", chat_id)
            return False
        return True

    def _route_message(
        self, raw_text: str, chat_id: int, config: AllowlistConfig
    ) -> Tuple[str, str]:
        lines = [line for line in raw_text.splitlines()]
        client_id = None
        content_lines: List[str] = []
        for line in lines:
            if client_id is None and line.strip():
                if CLIENT_ID_PATTERN.match(line.strip()):
                    client_id = line.strip().lower()
                    continue
            content_lines.append(line)
        resolved_client = (
            client_id
            or config.default_client_by_chat.get(str(chat_id))
            or DEFAULT_CLIENT_ID
        )
        content = "\n".join(content_lines).strip()
        if not content:
            content = raw_text.strip()
        return resolved_client, content

    def _write_message(self, client_id: str, chat_id: int, content: str) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"telegram_{timestamp}_{chat_id}.txt"
        in_txt_dir = CLIENTS_ROOT / client_id / "IN_TXT"
        tmp_dir = in_txt_dir / ".tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        in_txt_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = tmp_dir / f"{filename}.{os.getpid()}.tmp"
        final_path = in_txt_dir / filename
        tmp_path.write_text(content, encoding="utf-8")
        os.replace(tmp_path, final_path)
        LOGGER.info(
            "Saved message chat_id=%s client_id=%s filename=%s length=%s",
            chat_id,
            client_id,
            filename,
            len(content),
        )
        return filename

    @staticmethod
    def _discover_clients() -> List[str]:
        if not CLIENTS_ROOT.exists():
            return []
        return sorted(
            [
                path.name
                for path in CLIENTS_ROOT.glob("client_*")
                if path.is_dir()
            ]
        )


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


async def _main() -> None:
    _configure_logging()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is required")
    bot = TelegramIngestBot(token)
    await bot.run()


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        LOGGER.info("Shutdown requested by user")
