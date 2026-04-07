# Benchmark fixtures (Sprint 4)

Questo set contiene 10 chain benchmark esportate in JSON.

## File
- `benchmark_chains.json`: eventi canonici per replay benchmark.
- `benchmark_expectations.json`: esito atteso per chain (status, close_reason, pnl indicativo, warning/ignored).

## Copertura casi
- chain completa con update
- signal-only nativa
- update incompatibili (ignored + warning)
- TP hit
- SL hit
- CANCELLED
- EXPIRED (pending timeout + chain timeout)
