# Signal Chain Backtesting Lab

Laboratorio event-driven per replay/backtesting di chain di segnali trading, con adapter dal DB parser, policy configurabili, motore di simulazione, scenario runner, optimizer e reporting.

## Stato attuale (verifica: 2026-04-07, Incremento C completato)

Il repository contiene una pipeline backtesting completa lato core:

- adapter DB (`chain_builder`, `chain_adapter`, `validators`)
- dominio canonico (`domain/*`)
- engine (`state_machine`, `simulator`, `fill_model`, `timeout_manager`)
- market layer (`csv_provider`, `parquet_provider`, `intrabar_resolver`)
- policy layer (`policy_loader` + policy YAML baseline/custom)
- scenario runner + optimizer
- reporting (`event_log_report`, `trade_report`, `html_report`, `chain_plot`) — run singola: 5 artifact (JSONL, JSON, CSV, PNG, HTML); scenario: 4 artifact (JSON×2, CSV, HTML)
- GUI NiceGUI **MVP parziale** (`ui/app.py`, `ui/state.py`, `ui/components/*`; modularizzazione `ui/blocks/*` ancora aperta)
- suite test (unit, integration, golden)

### Limite ambiente noto

La suite non parte in questo ambiente perché Python runtime è **3.10**, mentre il progetto richiede **>=3.12** (`typing.Self` importato dal parser). Per questo motivo il primo errore avviene in collection.

## Setup rapido

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Comandi utili

```bash
# test completi
pytest -q

# run chain singola
python scripts/run_single_chain.py --help

# run scenario
python scripts/run_scenario.py --help

# run single-policy dataset report
python scripts/run_policy_report.py --help

# export parser report CSV
python parser_test/scripts/export_reports_csv.py --help
```

## Single-policy dataset report

Use `run_policy_report.py` when you want one policy over the whole dataset, with one aggregated report plus trade-level outputs.

```bash
python scripts/run_policy_report.py \
  --policy original_chain \
  --db-path db/backtest.sqlite3 \
  --market-dir data/market \
  --date-from 2025-01-01 \
  --date-to 2025-12-31 \
  --output-dir artifacts/policy_reports/original_chain \
  --write-trade-artifacts
```

Main outputs in `artifacts/policy_reports/<policy_name>/`:

- `policy_summary.json` and `policy_summary.csv`: aggregated metrics for the selected policy
- `trade_results.csv`: one row per simulated chain/trade
- `excluded_chains.csv`: excluded chains with validation reason
- `policy_report.html`: human-readable dataset report
- `trades/<signal_id>/...`: optional per-trade drill-down artifacts when `--write-trade-artifacts` is enabled

Implementation note:

- dataset loading and canonical adaptation reuse `adapters.chain_builder` and `adapters.chain_adapter`
- simulation and validation reuse `engine.simulator`, `adapters.validators`, and the existing policy/adapter path without changing scenario semantics
- per-trade drill-down artifacts reuse `reports.event_log_report`, `reports.trade_report`, and `reports.chain_plot`
- the single-policy report runner stays isolated in `src/signal_chain_lab/policy_report/*`, so existing `run_scenario.py` behavior remains unchanged


## Acquisizione Telegram (stato attuale)

- È disponibile l'import storico nel DB test con `parser_test/scripts/import_history.py`.
- L'import richiede `telethon` + credenziali `TELEGRAM_API_ID` / `TELEGRAM_API_HASH`.
- I moduli runtime live `src.telegram` non fanno parte di questo workspace: usare il flusso `parser_test` come ingestione offline/storica.

## Documentazione di riferimento

- Architettura: `docs/architecture.md`
- Piano operativo aggiornato: `docs/PIANO_OPERATIVO.md`
- Checklist sviluppo: `docs/CHECKLIST_SVILUPPO.md`
- Contratti dati: `docs/data-contracts.md`
- Audit DB: `docs/audit_db_report.md`

## Note di governance tecnica

- Aggiornare sempre checklist e piano operativo nella stessa PR quando cambia lo stato di uno sprint.
- Mantenere allineati i file `configs/policies/*.yaml` con i test di regressione.
- Usare golden test per evitare regressioni silenti su benchmark chain.
