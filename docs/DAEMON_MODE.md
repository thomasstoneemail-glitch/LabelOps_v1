# Daemon Mode (Headless Runner)

Daemon mode is a headless, always-on service that watches client IN_TXT folders and
processes incoming batches automatically. It is the recommended option for continuous
operations, while the GUI remains best for manual review or one-off batches.

## When to Use Daemon Mode vs GUI/CLI

**Use daemon mode when:**
- You want continuous processing without opening the GUI.
- Multiple users or systems are dropping `.txt` files into client folders.
- You want a “set-and-forget” workflow that runs all day.

**Use the GUI/CLI when:**
- You need to preview or tweak a batch manually.
- You want to run a single batch in a controlled session.
- You’re troubleshooting or testing a new client configuration.

Recommended workflow: run the daemon continuously, and use the GUI only for manual
batches or special cases.

## How to Run

From the project root:

```bash
python app/daemon.py \
  --clients all \
  --use-telegram 1 \
  --use-ai 0 \
  --auto-apply-max-risk low \
  --max-ai-calls 50 \
  --recursive 0
```

### Common Options

- `--clients all` or `client_01,client_02`
- `--use-telegram 0|1` (default 1)
- `--use-ai 0|1` (default 0)
- `--auto-apply-max-risk low|medium|high`
- `--max-ai-calls N`
- `--recursive 0|1`

### Telegram Bot (Optional)

If `--use-telegram=1`, the daemon starts the Telegram bot in the same process. The bot
saves incoming messages into the correct `IN_TXT` folder, where the watcher detects and
processes them.

Set the bot token before starting:

```bash
set TELEGRAM_BOT_TOKEN=your-token-here
```

## Failure Handling

If a file fails to process:
- The input `.txt` file is moved to:
  `D:\LabelOps\Clients\<client_id>\FAILURES`
- A sibling `.error.txt` file is written with the full traceback.
- The daemon logs the failure and continues processing the next file.

## Logs and Manifests

- Logs are written to `D:\LabelOps\Logs\labelops.log` by default.
- Manifests are written alongside logs in the same directory.
- Output artifacts are written to client folders:
  - `READY_XLSX`
  - `TRACKING_OUT`
  - `ARCHIVE`

You can override the log directory with `LABELOPS_LOG_DIR` or `--log-dir`.

## Auto-start on Login (AWS WorkSpaces)

### Option A: Windows Startup Folder
1. Press `Win + R`, type `shell:startup`, and press Enter.
2. Create a shortcut to a `.bat` file that runs the daemon.

Example `start_labelops_daemon.bat`:

```bat
@echo off
cd /d D:\LabelOps\LabelOps_v1
python app\daemon.py --clients all --use-telegram 1 --use-ai 0
```

### Option B: Task Scheduler
1. Open **Task Scheduler**.
2. Create a **Basic Task** called `LabelOps Daemon`.
3. Trigger: **At log on**.
4. Action: **Start a program**.
5. Program/script: `python`
6. Add arguments: `app\daemon.py --clients all --use-telegram 1 --use-ai 0`
7. Start in: `D:\LabelOps\LabelOps_v1`

## Notes

- Daemon mode processes one file at a time per process to keep behavior safe and
  deterministic.
- If multiple files land while a batch is running, they are queued and processed in
  order.
