"""Configuration system for LabelOps client-specific rules."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import yaml

DEFAULT_CONFIG_PATH = r"D:\LabelOps\config\clients.yaml"
DEFAULT_CLIENTS_ROOT = r"D:\LabelOps\Clients"
CLIENT_ID_PATTERN = re.compile(r"^client_\d{2}$")

REQUIRED_MAPPING_FIELDS = {
    "full_name",
    "address_line_1",
    "address_line_2",
    "town_city",
    "county",
    "postcode",
    "country",
    "service",
    "weight_kg",
}

OPTIONAL_MAPPING_FIELDS = {"reference", "phone", "email"}


@dataclass(frozen=True)
class ServiceRule:
    """Defines a service rule and trigger behavior."""

    name: str
    code: Optional[str]
    trigger_type: str
    trigger_tag: Optional[str]


@dataclass(frozen=True)
class ColumnMapping:
    """Defines a single column mapping entry."""

    field: str
    column_index: int


@dataclass(frozen=True)
class ClientConfig:
    """Container for a client's configuration."""

    client_id: str
    display_name: str
    defaults: Dict[str, Any]
    services: List[ServiceRule]
    clickdrop: Dict[str, Any]
    folders: Dict[str, str]


def load_config(path: str = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    """Load the YAML config file."""

    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    if not isinstance(data, dict):
        raise ValueError("Config root must be a mapping of client IDs to settings.")

    return data


def list_clients(cfg: Dict[str, Any]) -> List[str]:
    """Return a sorted list of client IDs in the config."""

    if not isinstance(cfg, dict):
        raise ValueError("Config must be a dictionary.")

    return sorted(cfg.keys())


def get_client(cfg: Dict[str, Any], client_id: str) -> Dict[str, Any]:
    """Fetch a single client's configuration section."""

    if client_id not in cfg:
        raise KeyError(f"Client ID not found: {client_id}")

    client_cfg = cfg[client_id]
    if not isinstance(client_cfg, dict):
        raise ValueError(f"Client config for {client_id} must be a mapping.")

    return client_cfg


def validate_config(cfg: Dict[str, Any]) -> None:
    """Validate the configuration structure and values."""

    if not isinstance(cfg, dict):
        raise ValueError("Config root must be a dictionary.")

    for client_id, client_cfg in cfg.items():
        if not CLIENT_ID_PATTERN.match(client_id):
            raise ValueError(f"Invalid client ID format: {client_id}")

        if not isinstance(client_cfg, dict):
            raise ValueError(f"Client config for {client_id} must be a mapping.")

        required_sections = {"display_name", "defaults", "services", "clickdrop"}
        missing = required_sections - client_cfg.keys()
        if missing:
            missing_list = ", ".join(sorted(missing))
            raise ValueError(f"Client {client_id} missing sections: {missing_list}")

        defaults = client_cfg.get("defaults")
        if not isinstance(defaults, dict):
            raise ValueError(f"Client {client_id} defaults must be a mapping.")
        for key in ("service", "weight_kg"):
            if key not in defaults:
                raise ValueError(f"Client {client_id} defaults missing '{key}'.")

        services = client_cfg.get("services")
        if not isinstance(services, list) or not services:
            raise ValueError(f"Client {client_id} services must be a non-empty list.")
        for idx, service in enumerate(services, start=1):
            if not isinstance(service, dict):
                raise ValueError(
                    f"Client {client_id} service entry {idx} must be a mapping."
                )
            if "name" not in service:
                raise ValueError(f"Client {client_id} service entry {idx} missing name.")
            trigger = service.get("trigger")
            if not isinstance(trigger, dict) or "type" not in trigger:
                raise ValueError(
                    f"Client {client_id} service entry {idx} missing trigger type."
                )
            if trigger.get("type") == "tag" and not trigger.get("tag"):
                raise ValueError(
                    f"Client {client_id} service entry {idx} tag trigger missing tag."
                )

        clickdrop = client_cfg.get("clickdrop")
        if not isinstance(clickdrop, dict):
            raise ValueError(f"Client {client_id} clickdrop must be a mapping.")
        if "column_mapping" not in clickdrop:
            raise ValueError(f"Client {client_id} clickdrop missing column_mapping.")

        column_mapping = clickdrop.get("column_mapping")
        if not isinstance(column_mapping, dict):
            raise ValueError(
                f"Client {client_id} clickdrop column_mapping must be a mapping."
            )

        missing_fields = REQUIRED_MAPPING_FIELDS - column_mapping.keys()
        if missing_fields:
            missing_list = ", ".join(sorted(missing_fields))
            raise ValueError(
                f"Client {client_id} column_mapping missing fields: {missing_list}"
            )

        for field, column in column_mapping.items():
            if field not in REQUIRED_MAPPING_FIELDS | OPTIONAL_MAPPING_FIELDS:
                continue
            if not isinstance(column, int) or column < 1:
                raise ValueError(
                    f"Client {client_id} column_mapping for '{field}' must be an int >= 1."
                )


def _is_windows_absolute(path: str) -> bool:
    return bool(re.match(r"^[A-Za-z]:\\", path))


def _resolve_folder_path(
    client_id: str, folder_value: Optional[str], default_suffix: str
) -> str:
    base_path = os.path.join(DEFAULT_CLIENTS_ROOT, client_id)
    default_path = os.path.join(base_path, default_suffix)
    if not folder_value:
        return default_path
    if _is_windows_absolute(folder_value) or os.path.isabs(folder_value):
        return folder_value
    return os.path.join(base_path, folder_value)


def resolve_client_settings(cfg: Dict[str, Any], client_id: str) -> Dict[str, Any]:
    """Resolve a client's settings with defaults and folder paths."""

    client_cfg = get_client(cfg, client_id)
    defaults = dict(client_cfg.get("defaults", {}))

    clickdrop = dict(client_cfg.get("clickdrop", {}))
    column_mapping = dict(clickdrop.get("column_mapping", {}))
    clickdrop["column_mapping"] = column_mapping

    services = list(client_cfg.get("services", []))

    folders_cfg = client_cfg.get("folders", {}) or {}
    if not isinstance(folders_cfg, dict):
        raise ValueError(f"Client {client_id} folders must be a mapping if provided.")

    folders = {
        "in_txt": _resolve_folder_path(client_id, folders_cfg.get("in_txt"), "IN_TXT"),
        "ready_xlsx": _resolve_folder_path(
            client_id, folders_cfg.get("ready_xlsx"), "READY_XLSX"
        ),
        "archive": _resolve_folder_path(client_id, folders_cfg.get("archive"), "ARCHIVE"),
        "tracking_out": _resolve_folder_path(
            client_id, folders_cfg.get("tracking_out"), "TRACKING_OUT"
        ),
    }

    resolved = {
        "client_id": client_id,
        "display_name": client_cfg.get("display_name"),
        "defaults": defaults,
        "services": services,
        "clickdrop": clickdrop,
        "folders": folders,
    }

    return resolved


def _print_example(cfg: Dict[str, Any]) -> None:
    validate_config(cfg)
    print("Clients:", list_clients(cfg))
    example = resolve_client_settings(cfg, "client_01")
    print(json.dumps(example, indent=2))


if __name__ == "__main__":
    config = load_config()
    _print_example(config)
