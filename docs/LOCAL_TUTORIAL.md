# LabelOps Local Run Tutorial

This guide sets up LabelOps in a local repo checkout with safe default paths and a
bootstrapped runtime folder.

## 1) Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

## 2) Install dependencies

```bash
pip install -e .
```

Optional AI dependencies:

```bash
pip install -e ".[openai]"
```

## 3) Configure local paths

The repo includes a local-ready config at `config/clients.local.yaml`. The app will
prefer it automatically if `D:\LabelOps\config\clients.yaml` is missing, but you can
also set explicit environment variables.

Create a `.env` file (based on `.env.example`) or export env vars directly:

```bash
export LABELOPS_CONFIG_PATH=config/clients.local.yaml
export LABELOPS_CLIENTS_ROOT=runtime/clients
export LABELOPS_LOG_DIR=runtime/logs
export LABELOPS_TEMPLATE_PATH=assets/ClickDrop_import_template_no_header.xlsx
```

If you want AI assist, add your API key:

```bash
export OPENAI_API_KEY=your_api_key_here
export OPENAI_MODEL=gpt-4o-mini
```

## 4) Bootstrap runtime folders

```bash
python scripts/bootstrap_local.py
```

This creates the runtime output folders (per client) and the log directory.

## 5) Run the GUI

```bash
python app/gui_main.py
```

## 6) Quick test data

Paste the following into the GUI input panel to validate parsing:

```
Grace O'Neil
Flat 2, 10 High Street
Stonehaven
Aberdeenshire
AB538HY
UK

Martin Wilkie
Unit 7, Riverside Estate,
Dock Road
Barry
CF644BU
United Kingdom
```

Then click **Parse Preview** followed by **Process Batch** to write outputs into
`runtime/clients/<client_id>/READY_XLSX` and `runtime/clients/<client_id>/TRACKING_OUT`.

## Troubleshooting

- **Config not found**: verify `LABELOPS_CONFIG_PATH` or check that
  `config/clients.local.yaml` exists.
- **Template missing**: ensure `assets/ClickDrop_import_template_no_header.xlsx` exists
  or set `LABELOPS_TEMPLATE_PATH`.
- **GUI fails to launch**: confirm that `PySide6` is installed and your Python version
  is 3.10+.
