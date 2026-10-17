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

## Run manually

From this folder:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Backup.ps1" -ShowReport
```

`-ShowReport` displays a final Windows message, including failures.
Without it, suitable for Task Scheduler, the results are written to console and JSON.

## Daily 21:00 schedule

For quick setup, run **Установить расписание.ps1** once on the Windows PC (sets a daily 21:00 task), or create the task manually in Windows Task Scheduler with a daily trigger at 21:00.
Program: `powershell.exe`
Arguments:
`-NoProfile -ExecutionPolicy Bypass -File "FULL_ABSOLUTE_PATH_TO_Backup.ps1"`

Set **Start only if the following network connection is available** only if needed by your setup, and enable running missed tasks on next startup. Do not use `-ShowReport` for an unattended task: dialog boxes may be invisible. Review the JSON report or Scheduler exit code 2 for individual failed files. The scheduler has **not** been installed remotely.

## Extend

Edit `backup.json`: add an item/group and a `files` entry with `source` and `target`.
Make unique targets, use Windows environment variables in `source`, and do not add passwords, tokens, or sensitive files to the public repository config. Targets must be relative to the destination folder.

## Restore after reinstall

Close the program before restoring its configuration files. Copy each backed up file to its original `source` path (after expanding `%APPDATA%`); install the relevant application first. Do not automatically overwrite new installs without checking versions.

## Not yet automated

- Bitwarden export: manual, securely encrypted export recommended; do not automatically export unencrypted vaults.
- Notion workspace export: manual, account-based export; check export completeness.
- CorelDRAW GMS: separate future entry, only copy after CorelDRAW closes and the exact macro location is verified.
