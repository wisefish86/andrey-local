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
| CorelDRAW | all `*.gms` beneath `%APPDATA%\Corel` | `Программы\CorelDRAW\<relative path under Corel>` |
| Adobe Photoshop | selected actions/settings/preset extensions beneath `%APPDATA%\Adobe\Adobe Photoshop *` | `Программы\Photoshop\<relative path under Adobe>` |

## CorelDRAW GMS auto-discovery

The `CorelDRAW GMS` entry in `backup.json` searches recursively for `*.gms` under `%APPDATA%\Corel`, so the exact CorelDRAW year/version does not need to be configured. It preserves the relative path from that directory (including version and `Draw\GMS`) when copying.

If `CorelDRW.exe` or `CorelDRAW.exe` is running, GMS copying is **deferred** for that run (not considered a failure). Flow Launcher and Espanso are still backed up. The scheduled run will retry next time; no file-trigger macro is needed. The final report has a `Deferred` count and per-source status. If CorelDRAW is always open at 21:00, run manual backup after closing it or use a more frequent schedule.

If `%APPDATA%\Corel` is missing, inaccessible or no GMS files are found, the report records an error; no guessed alternate location is used. These backups are intended to restore into the same version-specific folder after reinstalling CorelDRAW. Close CorelDRAW before restoring.

## Photoshop actions, preferences, presets

The `Adobe Photoshop` discovery entry searches version-independent folders under `%APPDATA%\Adobe`, **only** where the relative path starts with `Adobe Photoshop [version]\`. Original version and subfolders are preserved on Yandex Disk.

Captured file types: `Actions Palette.psp` (loaded actions), `*.atn` (saved action sets), `*.psp` (preferences, brushes, shortcuts, workspaces when stored as PSP), plus common presets `*.abr`, `*.asl`, `*.pat`, `*.grd`, `*.csh`, `*.tpl`, `*.aco`, `*.ase`, `*.kys`, `*.mnu`, `*.csf`, `*.psf`, `*.acv`, `*.jsx`, `*.jsxbin`, `*.json`.

If `Photoshop.exe` is running, the entire Photoshop group is deferred until the next scheduled run. This is important because Photoshop writes many settings when it exits. Missing Photoshop folders or no matching files produce an error in the report; other applications continue backing up.

**Important limitations:** This collects relevant user-profile files, not every installed Photoshop asset. Manually exported `.atn` actions or scripts stored outside `%APPDATA%\Adobe\Adobe Photoshop *` (e.g. under `Program Files`, custom external folders or other Adobe paths) are not included. Add their known paths as explicit `files` entries later. For reliable portability, explicitly save action *sets* to `.atn` from the Actions panel. Restoring `Actions Palette.psp` may help but is not a substitute for exported `.atn` sets.

Adobe reference: https://helpx.adobe.com/photoshop/desktop/get-started/settings-and-preferences/preference-and-preset-file-locations.html and https://helpx.adobe.com/photoshop/desktop/troubleshoot/tool-feature-issues/actions-are-missing.html.

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
- CorelDRAW GMS: enabled with dynamic discovery; actual runtime behavior requires verification on the Windows computer.
