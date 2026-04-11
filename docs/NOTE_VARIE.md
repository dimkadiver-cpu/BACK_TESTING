MODIFICHE DA FARE:


Verificare il parser:
 - per .P in simbolo
 - per entry a zone (forse range??)>>> conseguente operation rules e esecuzione

Blocco 3 : aggiornamento del dataset, 
 - Scaricare il data set:
    - in base a symbolo
    - TF maggiori

Note: indicare ora del segnale UTC e alineare al dataset (altrimenti falsi positivi/negativi e sopratutto se seguo la update della catena ) ????? VErificare i tempi di messaggi



 ALTRO:
- "ATOMUSDT.P" verificare perche parser produce P e non lo normalizza a "ATOMUSDT"
- Note: indicare ora del segnale UTC e alineare al dataset (altrimenti falsi positivi/negativi e sopratutto se seguo la update della catena ) ????? VErificare i tempi di messaggi


TODO:

1) Capire come avvine il baktest: Logica di bektesting. Prima vedi il backtest su th maggiore e poi sciendi sotto per abigueta o chiusure al comando 

2) Capire il funzionamento DEL BLOCCO 3:
    - La GUI: comandi +  sistemare 
    - Che report Produce: deve fare solo un report completo per polycy compreso i trade.
    - Miglioramento il report:
        - Intradurre il grafico interattivo e reale, in base alle impostazioni (C:\Back_Testing\docs\PRD_single_trade_interactive_report.md)
        - Perche in Signal ID ho "trader_c:trader_c:rm1571" "trader_c" due volte?
        - In elementi di Event Timeline: (rivedere la logica)
            - In "new signal": aggiungere i dati estratti come livelli di entru, sl e tp , al posto   di  "Price reference"
            - in LAtri tipi di eventi registrati 
    
    
    
    - Custom report - Creare un menu  impostazioni che mi permettano di mofificare il report_frinale della polycu
         Varibili modificabili:
            - In report riasuntivo: mostrare meta dati in policy
            - In Single Trade Report: se il grafico chart deve essere statico o dinamico (sara implimitato in futuro)
            
         


3) Blocco 4: da definire // dedicato solo alla ottimazione
     -   Aggiungere menu a tendina (ce gia) che mi permette sciegliere le policy per simulatore da cartella "C:\Back_Testing\configs\policies"
    - Che report Produce:
    - 



Da