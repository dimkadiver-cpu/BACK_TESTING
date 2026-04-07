# Verifica fase 1 preparazione DB backtesting (2026-04-07)

## Fonte PRD esterna consultata
- Repository: https://github.com/dimkadiver-cpu/back_testing
- Documento: `PRD_consolidato_signal_chain_lab.md` (versione draft-2, generata 2026-04-05)

## Requisiti PRD rilevanti per la prima fase (preparazione DB)
Dalla lettura del PRD, la fase iniziale di integrazione con DB esistente richiede:
1. approccio **adapter-first** su DB già esistente;
2. passaggi iniziali: **audit del DB**, **adapter canonico**, **validazione del mapping**;
3. workflow dati iniziale: acquisizione sorgente -> parser -> costruzione/verifica chain.

## Moduli presenti nel repository corrente collegati alla preparazione DB

### 1) Acquisizione dati in DB separato di test
- `parser_test/scripts/import_history.py`
  - importa storico Telegram su DB dedicato `parser_test`;
  - applica migration allo startup;
  - blocca esplicitamente l'uso del DB live.

### 2) Popolamento parse_results su DB test
- `parser_test/scripts/replay_parser.py`
  - rilegge `raw_messages`;
  - esegue parser/trader resolution/eligibility;
  - persiste `parse_results` con JSON normalizzato.

### 3) Harness operativo documentato per preparazione dataset
- `parser_test/README.md`
  - descrive flusso operativo: import storico -> replay parser;
  - conferma che gli script operano su DB test e non live.

### 4) Adapter dal DB esistente verso catena canonica backtesting
- `src/backtesting/chain_builder.py`
  - costruisce `SignalChain` direttamente dal DB esistente;
  - collega UPDATE via `resolved_target_ids` con fallback `reply_to_message_id`;
  - scarta con warning gli UPDATE orfani e le chain non valide.

### 5) Validazione mapping/chain tramite test dedicati
- `src/backtesting/tests/test_chain_builder.py`
  - copre linkage UPDATE, ordinamento temporale, filtri e casi orfani.
- `src/backtesting/tests/conftest.py`
  - fornisce schema completo di test (tabelle operative + backtest) per verifiche repeatable.

### 6) Schema risultati backtest nel DB
- `db/migrations/015_backtest_runs.sql`
- `db/migrations/016_backtest_trades.sql`

Queste migration coprono la persistenza output run/trade, utili dopo la fase di preparazione dataset/chain.

## Esito sintetico
- **Copertura buona** sulla preparazione tecnica del DB di backtesting tramite pipeline `parser_test` + `chain_builder` + test di mapping.
- **Gap rispetto al PRD esterno**: nel repository corrente non emerge uno script esplicito tipo `audit_existing_db.py` (citato nella checklist PRD), quindi l'audit iniziale del DB sembra distribuito nei test e nelle verifiche indirette, non in un comando dedicato unico.
