"""Core batch processing pipeline for LabelOps."""
from __future__ import annotations

import csv
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from app import address_ai, address_parser, clickdrop_xlsx, logging_utils, manifest

AI_RISK_LEVELS = ["low", "medium", "high"]
SERVICE_TAG_RE = re.compile(r"\bSERVICE\s*=\s*(\w+)\b", re.IGNORECASE)


@dataclass
class ParsedRecord:
    """Container for parsed record details."""

    record: dict
    matched_tag: Optional[str] = None


def _split_chunks(raw_text: str) -> list[str]:
    return [
        chunk
        for chunk in re.split(r"\n\s*\n+", raw_text.strip())
        if chunk.strip()
    ]


def _find_service_tag(chunk: str, services: Iterable[dict]) -> tuple[str | None, str | None]:
    upper_chunk = chunk.upper()

    service_override = SERVICE_TAG_RE.search(chunk)
    if service_override:
        tag_value = service_override.group(1).strip()
        for service in services:
            trigger = service.get("trigger", {})
            if trigger.get("type") == "tag" and str(trigger.get("tag", "")).upper() == tag_value.upper():
                return service.get("name"), trigger.get("tag")

    for service in services:
        trigger = service.get("trigger", {})
        if trigger.get("type") != "tag":
            continue
        tag = str(trigger.get("tag", "")).strip()
        if not tag:
            continue
        patterns = [
            rf"\b{re.escape(tag)}\b",
            rf"\[{re.escape(tag)}\]",
        ]
        for pattern in patterns:
            if re.search(pattern, upper_chunk, re.IGNORECASE):
                return service.get("name"), tag

    return None, None


def _default_service(services: Iterable[dict], fallback: str) -> str:
    for service in services:
        trigger = service.get("trigger", {})
        if trigger.get("type") == "default":
            return str(service.get("name", fallback))
    return fallback


def parse_records(
    raw_text: str,
    services: list[dict],
    defaults: dict,
) -> list[ParsedRecord]:
    """Parse raw input text into records with service tagging."""
    if not raw_text.strip():
        return []

    parsed: list[ParsedRecord] = []
    fallback_service = str(defaults.get("service", ""))
    default_service = _default_service(services, fallback_service)
    default_weight = defaults.get("weight_kg", 1.0)

    for chunk in _split_chunks(raw_text):
        record_list = address_parser.parse_batch(chunk)
        if not record_list:
            continue
        record = record_list[0]
        service_name, matched_tag = _find_service_tag(chunk, services)
        record["service"] = service_name or default_service
        record["weight_kg"] = default_weight
        if matched_tag:
            existing_notes = record.get("notes", "").strip()
            tag_note = f"Tag matched: {matched_tag}"
            record["notes"] = f"{existing_notes} {tag_note}".strip()
        parsed.append(ParsedRecord(record=record, matched_tag=matched_tag))

    return parsed


def write_tracking_csv(records: list[dict], output_path: str) -> str:
    """Write a tracking CSV for downstream tracking systems."""
    if not records:
        raise ValueError("No records provided for tracking CSV.")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "full_name",
        "postcode",
        "service",
        "weight_kg",
        "reference",
        "notes",
        "ai_flag",
    ]

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({key: record.get(key, "") for key in fieldnames})

    return str(path)


def _now_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _default_log_dir() -> str:
    return os.getenv("LABELOPS_LOG_DIR", r"D:\LabelOps\Logs")


def _resolve_template_path(client_settings: dict) -> str:
    template_path = client_settings.get("clickdrop", {}).get("template_path")
    if template_path:
        return str(template_path)
    return clickdrop_xlsx.generate_clickdrop_xlsx.__defaults__[0]


def run_pipeline(
    *,
    client_id: str,
    client_settings: dict,
    raw_text: str,
    input_files: list[str],
    use_ai: bool,
    auto_apply_max_risk: str,
    max_ai_calls: int,
    source: str,
    log_dir: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Run the batch pipeline and return output metadata."""
    if auto_apply_max_risk not in AI_RISK_LEVELS:
        raise ValueError("auto_apply_max_risk must be low, medium, or high")

    parsed = parse_records(
        raw_text,
        services=client_settings.get("services", []),
        defaults=client_settings.get("defaults", {}),
    )
    if not parsed:
        raise ValueError("No valid records were parsed from the input.")

    records = [entry.record for entry in parsed]
    ai_results: list[address_ai.AIResult] = []
    flagged_count = 0
    applied_count = 0

    if use_ai:
        records, ai_results = address_ai.process_batch(
            records,
            max_calls=max_ai_calls,
            auto_apply_max_risk=auto_apply_max_risk,
        )

        for ai_result in ai_results:
            if ai_result.suggestions:
                if ai_result.overall_risk in {"medium", "high"}:
                    flagged_count += 1
                if address_ai.RISK_ORDER.get(ai_result.overall_risk, 2) <= address_ai.RISK_ORDER.get(
                    auto_apply_max_risk,
                    0,
                ):
                    applied_count += 1

    timestamp = _now_timestamp()
    base_name = f"{client_id}_{timestamp}"
    folders = client_settings.get("folders", {})
    output_xlsx = os.path.join(folders.get("ready_xlsx", ""), f"{base_name}.xlsx")
    tracking_csv = os.path.join(folders.get("tracking_out", ""), f"{base_name}_tracking.csv")
    resolved_log_dir = log_dir or _default_log_dir()

    if not dry_run:
        logging_utils.setup_logging(resolved_log_dir)
        template_path = _resolve_template_path(client_settings)
        if not Path(template_path).exists():
            raise FileNotFoundError(f"Click & Drop template not found: {template_path}")
        clickdrop_xlsx.generate_clickdrop_xlsx(
            records,
            output_xlsx,
            template_path=template_path,
            defaults=client_settings.get("defaults", {}),
        )

        ai_lookup = {result.record_id: result for result in ai_results}
        for idx, record in enumerate(records):
            ai_result = ai_lookup.get(str(idx))
            record["ai_flag"] = "Yes" if ai_result and ai_result.suggestions else "No"
        write_tracking_csv(records, tracking_csv)

        ai_summary = manifest.AiSummary(
            enabled=use_ai,
            auto_apply_max_risk=auto_apply_max_risk,
            flagged_count=flagged_count,
            applied_count=applied_count,
        )
        batch_manifest = manifest.BatchManifest(
            manifest_version="1.0",
            batch_id=str(uuid.uuid4()),
            created_utc=datetime.now(timezone.utc).isoformat(),
            client_id=client_id,
            source=source,
            input_files=input_files,
            input_text_sha256=manifest.sha256_text(raw_text),
            output_xlsx=output_xlsx,
            output_pdf="",
            record_count=len(records),
            defaults_used=client_settings.get("defaults", {}),
            services_used_summary=manifest.compute_services_summary(records),
            ai=ai_summary,
            notes=["Dry run"] if dry_run else [],
        )
        manifest_path = manifest.write_manifest(batch_manifest, resolved_log_dir)
    else:
        manifest_path = ""

    return {
        "records": records,
        "ai_results": ai_results,
        "output_xlsx": output_xlsx,
        "tracking_csv": tracking_csv,
        "manifest_path": manifest_path,
        "record_count": len(records),
        "flagged_count": flagged_count,
        "applied_count": applied_count,
        "dry_run": dry_run,
    }
