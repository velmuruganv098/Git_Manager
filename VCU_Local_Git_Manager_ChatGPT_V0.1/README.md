# VCU Local Git Manager

A local-only HTTP UI with a Python backend intended to replace repetitive CMD Git operations for the VCU/Zitto_MB_V1 workflow.

## Start
1. Install Python 3.10+ and Git.
2. Run `python server.py`.
3. Open `http://127.0.0.1:8765`.
4. Enter/save your project and Git settings.
5. Compare before pushing. Generate the revision difference TXT and review it.
6. Use the Git buttons instead of CMD.

## Persistent configuration
`config.json` stores editable settings and is loaded automatically on every start.

## Difference reports
Reports are written to `reports/` and can be committed with a full revision, e.g. `DIFFERENCE_V1_TO_V2.txt`.

## Safety
The UI is local-only. It uses the installed Git executable and does not store GitHub passwords. Push has confirmation gates. Backups are created in `backups/` before a destructive replacement workflow.

## Important limitation
A browser cannot directly browse arbitrary PC folders without additional OS integration. Enter the paths in the UI. The current comparison engine compares two local folders; GitHub comparison is represented through Git fetch/diff/status operations. A future version can add a true remote-tree download/comparison and an OS folder picker.
