"""AI-assisted address correction utilities for LabelOps."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from openai import OpenAI

POSTCODE_REGEX = re.compile(r"^[A-Z0-9][A-Z0-9\s-]{2,12}$")
COUNTRY_TYPO_VARIANTS = {
    "UNITED KINGSOM": "UNITED KINGDOM",
    "UNITED STAES": "UNITED STATES",
    "UNITED STATSE": "UNITED STATES",
    "UNITED ARAB EMRITES": "UNITED ARAB EMIRATES",
}
RISK_ORDER = {"low": 0, "medium": 1, "high": 2}
SENSITIVE_NAME_FIELDS = {"name", "recipient", "full_name"}
ADDRESS_FIELDS = {
    "line1",
    "line2",
    "line3",
    "town",
    "city",
    "county",
    "state",
    "postcode",
    "zip",
    "country",
}


@dataclass
class AddressSuggestion:
    """Single field suggestion from the AI model."""

    field: str
    original: str
    suggested: str
    reason: str
    confidence: float


@dataclass
class AIResult:
    """AI response wrapper for a single record."""

    record_id: str
    suggestions: list[AddressSuggestion] = field(default_factory=list)
    overall_risk: str = "high"
    raw_model_output: str | None = None


def _normalize_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _contains_unknown(value: str) -> bool:
    upper = value.upper()
    return "?" in value or "UNKNOWN" in upper


def _postcode_invalid(postcode: str) -> bool:
    if not postcode:
        return True
    return POSTCODE_REGEX.match(postcode.upper()) is None


def should_use_ai(record: dict) -> bool:
    """Return True if the record exhibits obvious issues."""
    postcode = _normalize_str(record.get("postcode") or record.get("zip"))
    country = _normalize_str(record.get("country"))

    if not postcode or _postcode_invalid(postcode):
        return True

    if not country:
        return True

    if country.upper() in COUNTRY_TYPO_VARIANTS:
        return True

    for value in record.values():
        if isinstance(value, str) and _contains_unknown(value):
            return True

    return False


def redact_record(record: dict) -> dict:
    """Return a redacted version of the record if AI_REDACT_NAMES=1."""
    if os.getenv("AI_REDACT_NAMES") != "1":
        return record

    redacted: dict[str, Any] = {}
    for key, value in record.items():
        if key in SENSITIVE_NAME_FIELDS:
            continue
        if key in ADDRESS_FIELDS:
            redacted[key] = value
    return redacted


def build_prompt(record: dict) -> str:
    """Build a strict JSON-only prompt for address suggestions."""
    record_payload = json.dumps(record, ensure_ascii=False, indent=2)
    return (
        "You are an address correction assistant."
        " Do NOT invent missing fields."
        " Only suggest changes when you are highly confident."
        " Output STRICT JSON only, no prose."
        "\n\n"
        "JSON schema:\n"
        "{\n"
        "  \"suggestions\": [\n"
        "    {\"field\": \"country\", \"suggested\": \"UNITED KINGDOM\", "
        "\"reason\": \"typo fix\", \"confidence\": 0.92}\n"
        "  ],\n"
        "  \"overall_risk\": \"low|medium|high\"\n"
        "}\n\n"
        "Record:\n"
        f"{record_payload}"
    )


def _extract_json(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", stripped)
        stripped = stripped.replace("```", "").strip()

    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if match:
        return match.group(0)

    raise ValueError("No JSON object found in model output.")


def call_openai(prompt: str) -> dict:
    """Call OpenAI and return parsed JSON response."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set.")

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    client = OpenAI(api_key=api_key)
    response = client.responses.create(model=model, input=prompt)
    output_text = response.output_text

    json_text = _extract_json(output_text)
    try:
        return json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise ValueError("Model output was not valid JSON.") from exc


def _parse_suggestions(data: dict, record: dict) -> tuple[list[AddressSuggestion], str]:
    suggestions_data = data.get("suggestions", [])
    overall_risk = str(data.get("overall_risk", "high")).lower()
    if overall_risk not in RISK_ORDER:
        overall_risk = "high"

    suggestions: list[AddressSuggestion] = []
    for item in suggestions_data:
        field_name = str(item.get("field", "")).strip()
        if not field_name:
            continue
        suggested = _normalize_str(item.get("suggested"))
        reason = _normalize_str(item.get("reason")) or "unspecified"
        confidence = float(item.get("confidence", 0.0))
        original_value = _normalize_str(record.get(field_name))
        suggestions.append(
            AddressSuggestion(
                field=field_name,
                original=original_value,
                suggested=suggested,
                reason=reason,
                confidence=confidence,
            )
        )

    return suggestions, overall_risk


def get_suggestions(record: dict, record_id: str) -> AIResult:
    """Obtain AI suggestions for a single record."""
    redacted = redact_record(record)
    prompt = build_prompt(redacted)
    raw_output = None
    try:
        data = call_openai(prompt)
        raw_output = json.dumps(data, ensure_ascii=False)
        suggestions, overall_risk = _parse_suggestions(data, record)
    except Exception as exc:  # noqa: BLE001 - return high risk on any failure
        return AIResult(
            record_id=record_id,
            suggestions=[],
            overall_risk="high",
            raw_model_output=str(exc),
        )

    return AIResult(
        record_id=record_id,
        suggestions=suggestions,
        overall_risk=overall_risk,
        raw_model_output=raw_output,
    )


def _risk_allows_apply(overall_risk: str, max_risk: str) -> bool:
    return RISK_ORDER.get(overall_risk, 2) <= RISK_ORDER.get(max_risk, 0)


def apply_suggestions(
    record: dict,
    ai_result: AIResult,
    *,
    auto_apply_max_risk: str = "low",
) -> dict:
    """Apply suggestions if risk threshold allows; otherwise attach review."""
    updated = dict(record)
    if _risk_allows_apply(ai_result.overall_risk, auto_apply_max_risk):
        for suggestion in ai_result.suggestions:
            if suggestion.suggested:
                updated[suggestion.field] = suggestion.suggested
        return updated

    updated["ai_review"] = {
        "overall_risk": ai_result.overall_risk,
        "suggestions": [suggestion.__dict__ for suggestion in ai_result.suggestions],
    }
    return updated


def _iter_records(records: Iterable[dict]) -> Iterable[tuple[int, dict]]:
    for idx, record in enumerate(records):
        yield idx, record


def process_batch(
    records: list[dict],
    *,
    max_calls: int = 50,
    auto_apply_max_risk: str = "low",
) -> tuple[list[dict], list[AIResult]]:
    """Process a batch of records with AI suggestions."""
    processed: list[dict] = []
    results: list[AIResult] = []
    calls = 0

    for idx, record in _iter_records(records):
        if should_use_ai(record) and calls < max_calls:
            calls += 1
            ai_result = get_suggestions(record, record_id=str(idx))
            results.append(ai_result)
            processed.append(
                apply_suggestions(
                    record,
                    ai_result,
                    auto_apply_max_risk=auto_apply_max_risk,
                )
            )
        elif should_use_ai(record) and calls >= max_calls:
            ai_result = AIResult(
                record_id=str(idx),
                suggestions=[],
                overall_risk="high",
                raw_model_output="max_calls limit reached",
            )
            results.append(ai_result)
            processed.append(
                apply_suggestions(
                    record,
                    ai_result,
                    auto_apply_max_risk=auto_apply_max_risk,
                )
            )
        else:
            processed.append(dict(record))

    return processed, results


def _pretty_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    sample_records = [
        {
            "name": "Jane Doe",
            "line1": "10 Downing St",
            "town": "London",
            "postcode": "SW1A 2AA",
            "country": "UNITED KINGSOM",
        },
        {
            "name": "John Smith",
            "line1": "1600 Pennsylvania Ave",
            "town": "Washington",
            "postcode": "",
            "country": "United States",
        },
        {
            "name": "Alex Lee",
            "line1": "1 Infinite Loop",
            "town": "Cupertino",
            "postcode": "95014",
            "country": "United States",
        },
    ]

    if not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set; skipping AI calls in demo.")
        processed_records, ai_results = process_batch(sample_records, max_calls=0)
    else:
        processed_records, ai_results = process_batch(sample_records, max_calls=2)

    print("Before:\n", _pretty_json(sample_records))
    print("After:\n", _pretty_json(processed_records))
    print("Suggestions:\n", _pretty_json([result.__dict__ for result in ai_results]))
