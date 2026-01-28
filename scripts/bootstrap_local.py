"""Bootstrap local runtime folders for LabelOps."""
from __future__ import annotations

import os
from pathlib import Path

from app import config
from app import pipeline


def _ensure_dir(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def main() -> None:
    cfg = config.load_config()
    clients = config.list_clients(cfg)

    for client_id in clients:
        resolved = config.resolve_client_settings(cfg, client_id)
        folders = resolved.get("folders", {})
        for folder_path in folders.values():
            if folder_path:
                _ensure_dir(folder_path)

    _ensure_dir(pipeline._default_log_dir())

    clients_root = os.getenv("LABELOPS_CLIENTS_ROOT") or config._default_clients_root()
    print("Local runtime ready.")
    print(f"Clients root: {clients_root}")
    print(f"Log dir: {pipeline._default_log_dir()}")


if __name__ == "__main__":
    main()
