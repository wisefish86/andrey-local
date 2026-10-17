# Settings backup → Yandex Disk

This tool copies selected application configuration files to:
`D:\YandexDisk\Архив\Backup\Программы`.

- The backup contents are **not** kept in GitHub. Only the scripts and non-secret source list are versioned.
- Existing `Backup Bitwarden` and `Backup Notion` folders are untouched.
- A single latest copy is kept for each file. This is **not a versioned historical archive**; enable Yandex Disk version history separately if required.
- Missing source files are reported, never deleted from the destination.
- Unchanged files are skipped. Changed copies are verified by SHA-256 before replacement.
- Reports: `Программы\backup-last-report.json`. Errors also produce a non-zero exit code.
- Destination drive must be available. No fallback to another drive.
- `%APPDATA%` resolves dynamically to the Windows user profile.

## Currently backed up

| Program | Source | Backup target |
|---|---|---|
| Flow Launcher | `%APPDATA%\FlowLauncher\Settings\Favorites.conf` | `Программы\Flow Launcher\Favorites.conf` |
| Espanso | `%APPDATA%\espanso\match\base.yml` | `Программы\Espanso\match\base.yml` |
| Espanso | `%APPDATA%\espanso\config\default.yml` | `Программы\Espanso\config\default.yml` |

## Launchers (double-click)

- `Запустить резервное копирование настроек.bat` — run backup immediately, show a summary dialog, and pause console.
- `Установить расписание резервного копирования.bat` — install or update the Windows scheduled task from `backup.json`, then pause console.

Both BAT files invoke PowerShell relative to their own folder, so moving the repository does not require modifying a path inside the BAT. If you move the repository after task installation, rerun the installer BAT so the Task Scheduler points to the new path.

## Schedule in backup.json

```json
"schedule": {
  "mode": "daily",
  "time": "21:00",
  "intervalHours": 3
}
```

- `mode: "daily"`: run once every day at `time`; `intervalHours` is ignored.
- `mode: "every_hours"`: run every `intervalHours` (integer 1–24), starting at `time`. The repetition trigger is valid for 3650 days and can be renewed by running the installer BAT.
- After **any** change to the schedule, rerun `Установить расписание резервного копирования.bat`. Editing the JSON alone does **not** update an existing Windows task.
- The installer does not run the backup. It only registers/updates the daily or hourly task.
- Missed executions can run later via Task Scheduler's StartWhenAvailable; unattended tasks do not show pop-up dialogs. Inspect `Программы\backup-last-report.json` and Windows Task Scheduler history for failures.
- The schedule is **not yet installed on your Windows PC** until you run the BAT locally.

## Extend

Edit `backup.json`: add an item/group and a `files` entry with `source` and `target`.
Make unique targets, use Windows environment variables in `source`, and do not add passwords, tokens, or sensitive files to the public repository config. Targets must be relative to the destination folder.

## Restore after reinstall

Close the program before restoring its configuration files. Copy each backed up file to its original `source` path (after expanding `%APPDATA%`); install the relevant application first. Do not automatically overwrite new installs without checking versions.

## Not yet automated

- Bitwarden export: manual, securely encrypted export recommended; do not automatically export unencrypted vaults.
- Notion workspace export: manual, account-based export; check export completeness.
- CorelDRAW GMS: separate future entry, only copy after CorelDRAW closes and the exact macro location is verified.
