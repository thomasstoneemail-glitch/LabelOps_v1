# LabelOps GUI Usage (Module 10)

## How to run

```bash
python app/gui_main.py
```

## Install dependencies

```bash
pip install PySide6 openpyxl pyyaml watchdog python-telegram-bot openai
```

> Note: `openai` is only required if you enable AI assist.

## Workflow

1. **Choose client**
   - Use the client dropdown to select `client_XX`.
   - Click **Refresh clients** if you added or updated `clients.yaml`.

2. **Paste or load input**
   - **Paste Input**: paste raw Telegram addresses.
   - **Load File**: select a `.txt` file and preview the contents.

3. **Preview**
   - Click **Parse Preview** to parse the input and populate the preview table.
   - The status bar shows record counts and a sample record.

4. **Process**
   - Click **Process Batch** to run the full pipeline.
   - Output files are written to the client folders:
     - `READY_XLSX` for the Click & Drop XLSX
     - `TRACKING_OUT` for the tracking CSV
     - `D:\LabelOps\Logs` for the manifest JSON

5. **Find outputs**
   - The output panel shows file paths after processing.
   - Use **Open Output Folder** or **Copy Paths** for quick access.

## AI assist

- **Use AI assist**: when enabled, the GUI calls the AI correction module.
- **Auto-apply max risk**: controls which risk levels can be auto-applied.
  - `low`: only low-risk suggestions are applied.
  - `medium` or `high`: allows broader auto-apply (use with caution).
- If AI returns **medium** or **high** risk suggestions, the GUI shows a warning
  modal with the count of flagged records.

## Notes and safety

- The GUI does **not** auto-send anything; it only writes local files.
- If `clients.yaml` is missing or the Click & Drop template is not found, the GUI
  will display an error with the expected path.
