# PMO Compliance Dashboard

Live dashboard: https://YOUR-ORG.github.io/pmo-dashboard/dashboard/

## Structure
- `scripts/generate_data.py` — generates the compliance JSON from source data
- `data/pmo_data.json` — latest data snapshot (auto-generated, do not edit manually)
- `dashboard/index.html` — the interactive HTML dashboard

## Updating data
```bash
cd scripts
python3 generate_data.py
cd ..
git add data/pmo_data.json
git commit -m "data: refresh snapshot $(date +%Y-%m-%d)"
git push
```
Dashboard updates automatically within ~60 seconds of push.
