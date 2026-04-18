Aspetto genereale:
[x] 1. Fissare navbar sotto in modo fisso
[x] 2. eliminare titol h1 in altro, gia presente in card hero
[x] 3. eliminare in "card chats wrap" h2
[x] 4. legend dei market e livelli:
        -  verifica se tutti reapresentati sono effetivamente collegati ad eventi (vedi ME -levels - da eliminare)
        - posizione : aggiustare a visualizazione sempre al centro
        - vincolarli on/off solo a marker e livelli del chart e non a trail
        - Avg entry: fare linia trattegiata, normalmente disattivata in charts.    
[x] 6.  unificare i marker (colore e forme) su tra livelli charts, legend e trail

[x] 7. Nela chart:
        - verificare se il marker determinato a tf 1 e si lega alla candela poi si si sposta(si lega) a candela di Tf superiore quando si cambia TF, lostesso comportamento per le linee. 
        - verificare perche ultimo livello di TP non è visibile su chart, ma si vede suo label.

[]    8. Semplificare il label dei marker in trail:
        - SETUP OPENED -> SETUP
        - ADD ENTRY FILLED -> ENTRY N. FILLED
        - ENTRY_FILLED -> ENTRY N. FILLED
        - CANCELED -> PENDING CANCELED // si riferisce a ordini pendenti cancellati 
        - BREAK EVEN ACTIVATED -> BE
        - STOP LOSS HIT  -> SL
        - TAKE PROFIT HIT -> TP n. // n. nuemro di tp
        - FULL CLOSE (TP) -> TP n. (EXIT)
 
[]    9. Modificare info su Tooltip:
        - x Livelli > eliminare "range"



Altri aspetti da chiarire aggiornare/aggiornare:
    - Funding %: il totale come viene calcolato? possivile aggiungere in "metric compact" o trasformalo in  card compact + card detail con frecci che apre il detagli e vengono scritte i detagli di funding, tutti eventi (stesso pricipio per "Return net%, "Return Gross", cost total, fee%)


Altro:
[x]  verificare i parser, mettere il normalizatore in core a tutti per  "LDOUSDT.P" -> "LDOUSDT"