# Signal Chain Backtesting Lab

Laboratorio event-driven per replay/backtesting di chain di segnali trading, con adapter dal DB parser, policy configurabili, motore di simulazione, scenario runner, optimizer e reporting.

## Stato attuale (verifica: 2026-04-07)

Il repository contiene una pipeline backtesting completa lato core:

- adapter DB (`chain_builder`, `chain_adapter`, `validators`)
- dominio canonico (`domain/*`)
- engine (`state_machine`, `simulator`, `fill_model`, `timeout_manager`)
- market layer (`csv_provider`, `parquet_provider`, `intrabar_resolver`)
- policy layer (`policy_loader` + policy YAML baseline/custom)
- scenario runner + optimizer
- reporting (`event_log_report`, `trade_report`, `html_report`, `chain_plot`)
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

# export parser report CSV
python parser_test/scripts/export_reports_csv.py --help
```

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
