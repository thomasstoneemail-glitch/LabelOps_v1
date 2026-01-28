# Logging and Batch Manifest

## Logging overview
LabelOps writes logs to both the console and a rotating log file. The suggested location for log files is:

```
D:\LabelOps\Logs
```

### Rotation behavior
Logs are stored in `labelops.log` and rotated automatically when the file reaches 5 MB. The system keeps up to five backups (`labelops.log.1`, `labelops.log.2`, etc.), ensuring recent history is preserved without unbounded growth.

## Manifest (audit trail) overview
Each processing run emits a batch manifest JSON file. The manifest provides a lightweight audit trail so that you can verify what was processed without storing sensitive raw address content.

### What the manifest stores
- Client identifier
- Input source (telegram, watch folder, or GUI)
- Input filenames
- Output XLSX filename (and future PDF placeholder)
- Timestamp for the batch
- Defaults and services used
- Record count
- AI corrections applied or flagged
- SHA-256 hash of the input text (for verification without storing the text)

### What the manifest does NOT store
- Raw addresses or input text
- Any PII beyond identifiers already used operationally

## Correlating outputs to manifests
To trace a client PDF/XLSX back to its source:

1. Locate the output XLSX (or PDF) file.
2. Find the manifest with a matching `client_id` and date in the filename format:
   ```
   <client>_<YYYY-MM-DD>_<batchid>.manifest.json
   ```
3. Open the manifest and check `input_files` and `input_text_sha256` to confirm the batch contents without exposing sensitive data.

This approach keeps a verifiable audit trail while minimizing sensitive data retention.
