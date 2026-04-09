MODIFICHE DA FARE:

In Gui:

     
 Blocco 4: da definire // dedicato solo alla ottimazione
 -   Aggiungere menu a tendina (ce gia) che mi permette sciegliere le policy per simulatore da cartella "C:\Back_Testing\configs\policies"

    
Report: 
    - Ridefinire il report Polycy (esempio "policy_report_full_example.zip", PRD_REPORT.md)


- Verificare se blocco 3 funziona solo come Backtest e non ottimizatore vede essere solo come semplice backtester in base alla policy selezionata, puoi lasciare la funzionalita di selezione di piu polici, che producano un report separati 
- Verifichi che il processo di backtest applica il filtro del dataset.

- Quando fa back_testing:
    Sotto LOG deve creare la lista Artifact: artifacts/scenarios
        - dove ongi item e un backtest, che ha minimo di meta datti, un riepilago (nn in valori assaluti ma in %) e link verso il report html, che quando clicco mi apre in brovser il file 
        html del report
        - ogni backtest mi deve generare nuova cartella identificata. 


- /

Blocco 3 : aggiornamento del dataset, 
 - Scaricare il data set:
    - in base a symbolo
    - TF maggiori

Note: indicare ora del segnale UTC e alineare al dataset (altrimenti falsi positivi/negativi e sopratutto se seguo la update della catena ) ????? VErificare i tempi di messaggi

Logica di bektesting. Prima vedi il backtest su th maggiore e poi sciendi sotto per abigueta o chiusure al comando 


 ALTRO:
 "ATOMUSDT.P" verificare perche parser produce P e non lo normalizza a "ATOMUSDT"


 Miglioramento il report:

 - Perche in Signal ID ho "trader_c:trader_c:rm1571" "trader_c" due volte?

 - In elementi di Event Timeline:
    - In new signal: 