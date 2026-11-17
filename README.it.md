[English](README.md) | [中文](README.zh-CN.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Polski](README.pl.md) | **Italiano**

# PVYieldLens

Confronta la potenza stimata e quella effettiva dei pannelli. Segui il PR e l’energia stimata per oggi e in totale.

## Funzioni

- Potenza, PR e potenza ottimizzabile in tempo reale.
- Storico di potenza e PR ogni 1, 5 o 10 minuti.
- Energia stimata per oggi e dal primo avvio.
- Grafici delle ultime 24 ore, 7 giorni o 30 giorni.
- Sei lingue, da scegliere nel menu in alto a destra.

## Avvio rapido

### App Home Assistant

Per Home Assistant OS.

[![Aggiungi il repository di app PVYieldLens](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fenecess%2Fha-pvyieldlens%23dev_v0)

1. Premi il pulsante qui sopra e conferma **Aggiungi** in Home Assistant.
2. Trova **PVYieldLens** nello store delle app, poi installa e avvia l’app.
3. Apri la pagina Web e vai in **Impostazioni** per scegliere i sensori e inserire i dati dei pannelli.

Se il pulsante non apre Home Assistant, vai in **Impostazioni > App > Installa app > menu in alto a destra > Repository** e aggiungi:

```text
https://github.com/enecess/ha-pvyieldlens#dev_v0
```

Nelle versioni di Home Assistant precedenti alla 2026.2, usa **Impostazioni > Componenti aggiuntivi > Store dei componenti aggiuntivi > menu in alto a destra > Repository**. L’app richiede Home Assistant 2025.9.0 o successivo.

### Docker

Scarica questo repository e apri la sua cartella. Crea il file delle impostazioni:

```sh
cp .env.example .env
```

In `.env`, scegli una password per `PVYL_WEB_PASSWORD`, poi avvia l’app:

```sh
docker compose up -d --build
```

Apri [localhost:8099](http://localhost:8099). Accedi come `admin` con la password scelta. Per il primo collegamento, inserisci in **Impostazioni** l’indirizzo di Home Assistant e un token di accesso a lunga durata di un **amministratore** di Home Assistant, poi premi **Aggiorna sensori**. Se indirizzo e token sono già configurati, i sensori vengono caricati automaticamente alla prima apertura delle **Impostazioni**. Usa **Aggiorna sensori** dopo aver modificato il collegamento, per aggiornare l’elenco o per riprovare dopo un errore. Per pubblicare i sensori di uscita sono necessari i diritti di amministratore.

La pagina è accessibile dal computer con Docker. Per aprirla da un altro dispositivo, cambia `127.0.0.1:8099:8099` in `8099:8099` nel file `compose.yaml`.

## Impostazioni

**Tempo reale** mostra medie attuali e diagnostica, **Storico** i periodi conclusi e l’energia/PR dell’intervallo scelto, **Previsioni** le stime meteo. La voce separata **Impostazioni**, con ingranaggio e testo, è in alto a destra; le tre schede dati restano disponibili. L’indice delle categorie scorre un unico modulo continuo: Connessione a Home Assistant, Moduli fotovoltaici, Sensori, Monitoraggio e Previsioni.

**Salva configurazione** mantiene aperte le Impostazioni. **Scarta modifiche** ricarica dal server la configurazione salvata e sostituisce le modifiche; se il caricamento fallisce, la bozza resta disponibile per riprovare. Uscendo con modifiche non salvate puoi continuare a modificarle o scartarle. Rientrare nelle Impostazioni ricarica la configurazione salvata.

Il menu **Modalità tema**, in alto a destra, offre Auto, Chiaro e Scuro. Auto segue la modalità di Home Assistant nella sua interfaccia e usa la preferenza di sistema senza un contesto Home Assistant accessibile. Chiaro o Scuro imposta una scelta locale; Auto ripristina il comportamento automatico. Cambiare lingua o tema conserva la bozza.

| Impostazione | Valore da inserire |
| --- | --- |
| Potenza massima totale in STC | Somma delle potenze massime dei moduli in condizioni di prova standard (STC) in W, ad esempio `5000`. |
| Coefficiente di temperatura di Pmax | Coefficiente Pmax della scheda del modulo in %/°C, ad esempio `-0,35`. |
| Potenza effettiva | Sensore della potenza prodotta dai pannelli (W o kW). |
| Temperatura dei moduli | Sensore della temperatura dei pannelli (°C, °F o K). |
| Irradianza | Sensore sullo stesso piano dei pannelli (W/m² o kW/m²). |
| Intervallo di contabilizzazione | 1, 5 o 10 minuti. Predefinito: 5 minuti. |
| Media su | Tempo usato per la media in tempo reale. Predefinito: 60 secondi. |
| Aggiorna ogni | Tempo tra gli aggiornamenti. Predefinito: 5 secondi. |

Salva e apri **Tempo reale**. Il primo risultato consolidato appare nello **Storico** alla fine del periodo in corso. In **Tempo senza nuovi dati**, imposta quanto attendere un aggiornamento da ogni sensore.

La vista dal vivo precarica dieci minuti fissi all’apertura o alla riconnessione. Ogni punto usa ancora **Media su** e la raccolta segue **Aggiorna ogni**. Il trend è ricostruito dalle osservazioni salvate con i parametri attuali; non è un registro delle istantanee pubblicate. Osservazioni mancanti o scadute e il punto attualmente offline rimangono lacune. Le disconnessioni precedenti senza una lacuna riconoscibile non sono ricostruibili con precisione. Lo Storico conserva i risultati consolidati originali. Quando la diagnostica è aperta nella pagina Tempo reale visibile, i tre sensori configurati vengono letti da Home Assistant circa una volta al secondo. Chiudere la diagnostica, cambiare pagina o nascondere la scheda del browser sospende queste richieste. L’età usa l’ora di Home Assistant e avanza localmente tra le letture; l’intervallo di monitoraggio e gli aggiornamenti del grafico restano invariati.

Le curve smussate servono solo alla visualizzazione. I dettagli con mouse, tocco e tastiera mostrano i valori originali; le previsioni mostrano l’intervallo orario originale. Energia e PR usano i dati originali. L’ora domestica determina totali giornalieri, date delle previsioni, meteo, Oggi e intervalli orari. Gli orari dal vivo/dello storico e di aggiornamento/download seguono la preferenza HA server/local del lettore; Docker autonomo usa il fuso del browser. Una preferenza HA illeggibile ripiega sull’ora domestica. Una nota indica fusi diversi; gli scostamenti UTC distinguono solo ore ripetute o intervalli con un cambio di scostamento.

## Previsioni di produzione

Le previsioni sono disattivate per impostazione predefinita alla prima installazione. In **Impostazioni > Previsioni**, attivale e inserisci inclinazione (0–90°), direzione (nord 0°, est 90°, sud 180°, ovest 270° o azimut personalizzato da 0° a meno di 360°) e NOCT della scheda tecnica (oltre 20°C, massimo 80°C; predefinito 45°C). Potenza massima totale in STC e coefficiente di temperatura di Pmax sono condivisi con il monitoraggio. Posizione e fuso provengono automaticamente dalla connessione HA salvata; modificali in HA.

Il monitoraggio usa la **Temperatura dei moduli** misurata. Le previsioni usano la **Temperatura dell’aria** e la **Temperatura nominale di funzionamento della cella (NOCT)** per calcolare la **Temperatura stimata delle celle**. Sono grandezze distinte; il monitoraggio non converte la temperatura dei moduli in temperatura delle celle.

Open-Meteo fornisce il meteo orario per oggi e i sei giorni di calendario locali successivi. Scegli una data per energia giornaliera, curva oraria e tabella degli intervalli. La previsione di oggi comprende tutto il giorno; **Rimanente oggi** solo il tempo da adesso alla mezzanotte locale. Entrambe usano l’ultimo meteo scaricato correttamente e sono distinte dall’energia stimata consolidata calcolata dai sensori. L’energia rimanente diminuisce con il tempo tra i download; nuovi dati possono anche modificare la stima dell’intera giornata.

Ogni scheda mostra meteo, massima/minima delle previsioni orarie, barra energetica e kWh. L’etichetta calda **Oggi** segue la mezzanotte domestica e rimane visibile quando un’altra data è selezionata in blu. Le temperature usano gli estremi dei campioni orari grezzi; il meteo rappresentativo usa il massimo codice WMO noto del giorno. Ogni campo richiede tutti i campioni UTC orari attesi nel giorno domestico, anche con giornate di 23/25 ore e fusi frazionari. Un campo incompleto è indisponibile, mentre l’altro completo rimane visibile. Zero è valido; il meteo sconosciuto ha un’icona neutra. Meteo e potenza condividono richiesta, cache e ora di download, senza ulteriori aggiornamenti.

Il meteo si aggiorna ogni ora o con **Aggiorna previsione**. La cache corrispondente resta dopo il riavvio. Un errore conserva l’ora del download e segnala dati obsoleti; nuovo tentativo dopo 15 minuti. Anche i dati vecchi di almeno due ore sono obsoleti. Gli intervalli mancanti rendono indisponibili i totali interessati; la completezza dei dati è mostrata separatamente e i dati mancanti non valgono zero. Sono indicati disattivazione, posizione HA assente, primo caricamento e indisponibilità.

Sono riferimenti stimati in corrente continua per un solo campo di pannelli, con irradianza sul loro piano e modello termico NOCT semplificato. Non includono efficienza/limitazione dell’inverter, ombre, neve, sporco o perdite e non garantiscono la produzione reale in corrente alternata. Le quattro entità hanno kWh e classe energy, senza `state_class`; possono diminuire e restano separate dai contatori cumulativi. Non forniscono un’integrazione nativa con previsioni HA o dashboard Energia.

## Sensori di uscita

| Indicatore | Nome entità HA | Unità |
| --- | --- | --- |
| Potenza stimata consolidata | `settled_estimated_power` | W |
| Potenza effettiva consolidata | `settled_actual_power` | W |
| PR consolidato | `settled_pr` | % |
| Energia stimata oggi | `estimated_energy_today` | kWh |
| Energia stimata cumulativa | `estimated_energy_lifetime` | kWh |
| Potenza stimata in tempo reale | `live_estimated_power` | W |
| Potenza effettiva in tempo reale | `live_actual_power` | W |
| PR in tempo reale | `live_pr` | % |
| Potenza ottimizzabile in tempo reale | `live_optimizable_power` | W |
| Energia prevista oggi | `forecast_energy_today` | kWh |
| Energia prevista rimanente oggi | `forecast_energy_remaining_today` | kWh |
| Energia prevista domani | `forecast_energy_tomorrow` | kWh |
| Energia prevista per 7 giorni | `forecast_energy_7d` | kWh |

Il nome entità HA è il nome visualizzato. L’ID completo è `sensor.pvyieldlens_` seguito da questo nome, ad esempio `sensor.pvyieldlens_settled_estimated_power`.

## Formula del PR

La potenza stimata tiene conto della potenza massima totale in STC, della temperatura dei moduli e dell’irradianza:

```text
P_estimated = P_stc × [1 + (K / 100) × (T − 25)] × G / 1000
PR = P_actual / P_estimated × 100%
```

`P_stc`: potenza massima totale in STC (W); `K`: coefficiente di temperatura di Pmax (%/°C), percentuale della scheda tecnica, ad esempio `-0,35`; `T`: temperatura dei moduli (°C); `G`: irradianza sul piano dei moduli (W/m²). L’app divide K per 100 una sola volta.

Il rapporto di prestazione (PR) confronta la potenza effettiva con quella stimata. La potenza ottimizzabile è la potenza stimata meno quella effettiva e può essere negativa.

## Leggere i risultati

- Il PR può superare il 100%. Quando la potenza stimata è zero, il PR non è mostrato.
- Una potenza ottimizzabile negativa indica che la potenza effettiva è maggiore di quella stimata.
- L’energia è contata solo quando tutti e tre i sensori hanno dati. I periodi mancanti sono esclusi.
- L’energia del giorno si azzera a mezzanotte nel fuso di Home Assistant. Il totale parte dalla prima configurazione.

Dopo un’interruzione, alcuni periodi possono rimanere senza dati. Conserva i dati dell’app durante gli aggiornamenti o la reinstallazione. Per l’app usa i backup di Home Assistant; con Docker autonomo, arresta il contenitore prima di copiare la cartella `/data`.
