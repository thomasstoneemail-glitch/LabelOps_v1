# AI-Assisted Address Correction (Optional, Review-First)

This module provides **optional** AI suggestions for cleaning address records, focusing on obvious corrections (country typos, postcode formatting, and common misspellings). It is **review-first by default**: suggestions are produced with confidence and risk levels, and changes are not auto-applied unless you explicitly enable it.

## Why AI Is Optional
- AI can help catch obvious errors quickly, but it can also make mistakes.
- Address data can be sensitive; you decide when and how to use AI.
- The system never auto-applies changes above your configured risk threshold.

## Environment Setup (Windows PowerShell)
Set your OpenAI API key and optional model override:

```powershell
$env:OPENAI_API_KEY = "your-api-key"
$env:OPENAI_MODEL = "gpt-4o-mini"
```

If `OPENAI_MODEL` is not set, the default is `gpt-4o-mini`.

## Name Redaction
Set `AI_REDACT_NAMES=1` to remove name fields before sending the record to the model:

```powershell
$env:AI_REDACT_NAMES = "1"
```

When enabled, the AI only sees address-related fields (line1/line2/town/county/postcode/country, etc.). By default, names are included because they sometimes affect formatting or validation.

## Risk Levels and Review Guidance
- **low**: High-confidence suggestions. Safe to auto-apply if you opt in.
- **medium**: Some uncertainty. Human review strongly recommended.
- **high**: Model failed or uncertain. Do not auto-apply.

The system will **never** auto-apply changes above the configured risk threshold.

## Recommended Workflow
1. Parse or import addresses into LabelOps.
2. Generate an XLSX export.
3. Run AI assistance to flag potential fixes.
4. Open the review panel (future GUI) and approve or reject suggestions.
5. Apply accepted corrections and re-export labels.

This keeps AI strictly in a review role while improving data quality over time.
