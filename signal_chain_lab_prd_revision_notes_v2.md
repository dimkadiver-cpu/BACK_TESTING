# Signal Chain Backtesting Lab — revision notes v4

Questa revisione consolida il PRD dopo la revisione completa dei punti 1–25.

## Cambiamenti principali

- chiarita la distinzione tra **chain completa** e **signal-only nativa** come due forme dati entrambe valide
- separata la logica di **configurazione globale** da quella di **policy di simulazione**
- rafforzato il modello di dominio con:
  - `CanonicalChain`
  - `EventLogEntry`
  - `PolicyConfig`
  - `TradeState` più ricco
- trasformato l’**event log** nel record canonico del replay
- chiarita la gerarchia degli artifact:
  - event log
  - trade result
  - scenario result
  - report / visual
- rese più rigide roadmap, planning, acceptance criteria e test strategy
- rafforzato l’handoff finale all’agente di sviluppo con vincoli non negoziabili
- riclassificate le domande aperte fuori MVP in categorie più utili per le fasi successive

## Decisioni chiave preservate

- partire da **DB esistente -> adapter -> validator -> simulator**
- non riscrivere parser o chain reconstruction salvo audit negativo strutturato
- trattare il sistema come **event-driven replay lab** e non come backtester indicator-based
- mantenere **optimizer** separato dal simulation core
- mettere **correctness + auditabilità** prima di reporting e realism avanzato

## File principali

- `signal_chain_lab_full_handoff_v4.md` — PRD completo consolidato
- `signal_chain_lab_prd_revision_notes_v2.md` — note sintetiche di revisione
