# Module 13: Operations hardening + deployment checklist + smoke tests

This checklist covers a practical, secure deployment of LabelOps on AWS WorkSpaces, plus smoke testing for end-to-end validation.

## 1) AWS account security
- [ ] **MFA required** for every human IAM user (or use AWS SSO with MFA enforced).
- [ ] **Least privilege IAM** for administrators, support, and deployment automation. Remove unused roles and access keys.
- [ ] **Billing alerts** configured (e.g., Budgets + SNS email) for unexpected spend.
- [ ] **Root account** protected: MFA enabled, no access keys, alert on root usage.

## 2) WorkSpace security
- [ ] **No inbound ports** are required (LabelOps runs locally). Keep security groups with no inbound rules.
- [ ] **OS updates** enabled and patched regularly (Windows Update schedule documented).
- [ ] **Microsoft Defender** enabled and current.
- [ ] **Local firewall** enabled with default deny inbound.
- [ ] **Disk encryption** enabled on the WorkSpace volume.

## 3) Secrets management
- [ ] Store **`TELEGRAM_BOT_TOKEN`** and **`OPENAI_API_KEY`** as environment variables (System or User level).
- [ ] **Never** commit secrets to Git, copy them into config files, or paste into issue trackers.
- [ ] **Never** paste secrets into logs or console output (sanitise before sharing logs).
- [ ] Rotate secrets if exposed; update environment variables and restart the daemon.

## 4) Data handling
- **Raw input TXT location**: `D:\LabelOps\Clients\<client_id>\IN_TXT`.
- **Archive location**: `D:\LabelOps\Clients\<client_id>\ARCHIVE`.
- **Retention**: keep raw TXT only as long as needed for audit or customer support.
  - Recommended default: **retain 30 days** in ARCHIVE, then purge.
- **Purge policy**: delete TXT/ARCHIVE after X days (document the number and schedule).
  - Example: scheduled task runs weekly to delete files older than 30 days.

## 5) Audit & traceability
- **Manifests** are written per batch in `D:\LabelOps\Logs` (JSON files).
- Each manifest includes:
  - Client ID, batch ID, input files, timestamps.
  - Output files generated (XLSX, tracking CSV).
  - AI usage summary (if enabled).
- Use manifests to prove what was generated and when.

## 6) Disaster recovery
- **Backup**:
  - `D:\LabelOps\config` (especially `clients.yaml`)
  - `D:\LabelOps\assets` (Click & Drop template)
  - `D:\LabelOps\Clients` (per-client IN/ARCHIVE/READY/TRACKING folders)
- **Rebuild**:
  1. Deploy a new WorkSpace.
  2. Install LabelOps using the standard installer.
  3. Restore `config`, `assets`, and `Clients` from backup.
  4. Run smoke tests to validate end-to-end functionality.

## 7) Recommended startup
- Configure the LabelOps **daemon** to start at login using **Windows Task Scheduler**.
  - Trigger: **At log on** for the WorkSpace user.
  - Action: `python D:\LabelOps\app\daemon.py --clients all --use-telegram 1 --use-ai 0`.
  - Start in: `D:\LabelOps`.

---

## Deployment checklist (summary)
- [ ] AWS account hardened (MFA, least privilege, billing alerts).
- [ ] WorkSpace security baseline applied (no inbound ports, OS updates, Defender, firewall).
- [ ] Secrets stored in environment variables only (no repo/log leakage).
- [ ] Data retention + purge policy documented and scheduled.
- [ ] Backup plan for config/assets/Clients folders.
- [ ] Daemon set to auto-start via Task Scheduler.
- [ ] Smoke test executed and PASS recorded.
