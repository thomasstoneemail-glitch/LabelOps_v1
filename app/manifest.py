"""Batch manifest utilities for audit trails."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Dict, List


@dataclass
class AiSummary:
    """Summary of AI assistance used in a batch."""

    enabled: bool
    auto_apply_max_risk: str
    flagged_count: int
    applied_count: int


@dataclass
class BatchManifest:
    """Audit manifest for a processing batch."""

    manifest_version: str
    batch_id: str
    created_utc: str
    client_id: str
    source: str
    input_files: List[str]
    input_text_sha256: str
    output_xlsx: str
    output_pdf: str
    record_count: int
    defaults_used: Dict[str, Any]
    services_used_summary: Dict[str, int]
    ai: AiSummary
    notes: List[str] = field(default_factory=list)


def sha256_text(text: str) -> str:
    """Return SHA-256 hex digest for the provided text."""
    if text is None:
        raise ValueError("text must be provided")
    return sha256(text.encode("utf-8")).hexdigest()


def compute_services_summary(
    records: List[Dict[str, Any]],
    service_field: str = "service",
) -> Dict[str, int]:
    """Compute a summary of service counts from records."""
    summary: Dict[str, int] = {}
    for record in records:
        service = record.get(service_field) if isinstance(record, dict) else None
        key = str(service) if service else "unknown"
        summary[key] = summary.get(key, 0) + 1
    return summary


def _safe_filename(value: str) -> str:
    value = value.strip().replace(" ", "_")
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value) or "client"


def _manifest_to_dict(manifest: BatchManifest) -> Dict[str, Any]:
    data = asdict(manifest)
    data["ai"] = asdict(manifest.ai)
    return data


def write_manifest(manifest: BatchManifest, out_dir: str) -> str:
    """Write manifest JSON to the output directory and return its path."""
    if not out_dir:
        raise ValueError("out_dir must be provided")

    os.makedirs(out_dir, exist_ok=True)

    try:
        created = datetime.fromisoformat(manifest.created_utc.replace("Z", "+00:00"))
    except ValueError:
        created = datetime.now(timezone.utc)

    date_str = created.date().isoformat()
    client_safe = _safe_filename(manifest.client_id)
    filename = f"{client_safe}_{date_str}_{manifest.batch_id}.manifest.json"
    path = os.path.join(out_dir, filename)

    payload = _manifest_to_dict(manifest)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
    return path


if __name__ == "__main__":
    sample_records = [
        {"service": "standard"},
        {"service": "standard"},
        {"service": "express"},
    ]
    demo_manifest = BatchManifest(
        manifest_version="1.0",
        batch_id=str(uuid.uuid4()),
        created_utc=datetime.now(timezone.utc).isoformat(),
        client_id="demo-client",
        source="watch_folder",
        input_files=["input_001.txt"],
        input_text_sha256=sha256_text("Example input text"),
        output_xlsx="demo_output.xlsx",
        output_pdf="",
        record_count=len(sample_records),
        defaults_used={"service": "standard"},
        services_used_summary=compute_services_summary(sample_records),
        ai=AiSummary(
            enabled=True,
            auto_apply_max_risk="low",
            flagged_count=2,
            applied_count=1,
        ),
        notes=["Demo manifest"],
    )

    out_path = write_manifest(demo_manifest, r"D:\LabelOps\_demo_out\manifests")
    print(out_path)
