# Release Build (Windows / AWS WorkSpaces)

This guide documents how to build LabelOps executables and (optionally) create an installer on Windows WorkSpaces/Server.

## Prerequisites

1. **Install Python 3.10+ (64-bit)**
   - Download from https://www.python.org/downloads/windows/
   - Ensure **"Add Python to PATH"** is enabled.

2. **(Optional) Install Inno Setup**
   - Download from https://jrsoftware.org/isinfo.php
   - Inno Setup is only needed if you want a Windows installer (`LabelOpsInstaller.exe`).

3. **Clone the repository**
   ```powershell
   git clone <your-repo-url>
   cd LabelOps_v1
   ```

## Build the executables

Run the PowerShell build script from the repo root:

```powershell
.\scripts\build.ps1
```

### What the script does

- Creates a build virtual environment in `.venv_build`
- Installs dependencies from `pyproject.toml`
- Uses PyInstaller (one-folder builds) to generate:
  - `LabelOpsGUI.exe`
  - `LabelOpsDaemon.exe`
  - `LabelOpsPipeline.exe`
- Produces a versioned release folder:
  - `D:\LabelOps\dist\LabelOps_<version>_<YYYYMMDD>\`
- Copies starter config/assets into the release folder
- Writes `BUILD_INFO.txt`

### Build output

You should see:

```
D:\LabelOps\dist\LabelOps_0.1.0_YYYYMMDD\
├─ LabelOpsGUI\LabelOpsGUI.exe
├─ LabelOpsDaemon\LabelOpsDaemon.exe
├─ LabelOpsPipeline\LabelOpsPipeline.exe
├─ config\clients.yaml
├─ config\telegram_allowlist.json
├─ assets\ClickDrop_import_template_no_header.xlsx
└─ BUILD_INFO.txt
```

## Optional: Build the installer (Inno Setup)

1. Open `scripts\inno\LabelOps.iss` in the Inno Setup Compiler.
2. Update the `ReleaseDir` constant to match your release output:
   ```pascal
   #define ReleaseDir "D:\\LabelOps\\dist\\LabelOps_0.1.0_YYYYMMDD"
   ```
3. Click **Build > Compile**.

The installer will:
- Install executables into `C:\Program Files\LabelOps\...`
- Create folders on `D:\LabelOps\`:
  - `config`, `assets`, `Clients`, `Logs`
- Copy starter config and assets to `D:\LabelOps\config` and `D:\LabelOps\assets`
- Add Start Menu shortcuts for the GUI and Daemon

## Updating the ClickDrop template safely

The file `D:\LabelOps\assets\ClickDrop_import_template_no_header.xlsx` is a placeholder.
To update it safely:

1. Replace the file on disk with the new template.
2. Keep the exact filename intact.
3. Re-run the installer only if you need to distribute the template to other machines.

## Environment variables

Set these environment variables on the machine that runs LabelOps:

- `TELEGRAM_BOT_TOKEN` – required for the Telegram ingest bot
- `OPENAI_API_KEY` – optional, only if enabling OpenAI features

### Example (PowerShell)

```powershell
[Environment]::SetEnvironmentVariable("TELEGRAM_BOT_TOKEN", "<token>", "Machine")
[Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "<token>", "Machine")
```

Restart the workstation or log out/in for system-wide variables to take effect.
