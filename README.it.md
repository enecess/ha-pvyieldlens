[English](README.md) | [中文](README.zh-CN.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Polski](README.pl.md) | **Italiano**

# PVYieldLens

Confronta la potenza stimata e quella effettiva dei pannelli. Segui il PR e l’energia stimata per oggi e in totale.

## Funzioni

- Panoramica con potenza, PR e produzione consolidata di oggi.
- Confronti di efficienza con contabilizzazioni originali di 1, 5 o 10 minuti.
- Energia stimata di oggi e dalla configurazione.
- Confronto energetico giornaliero per 7/30 giorni o un intervallo personalizzato fino a 90 date.
- Previsioni originali e corrette ogni 15 minuti.
- Sei lingue, con menu in alto a destra.

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

La **Panoramica** mostra potenza attuale e produzione di oggi, **Efficienza** confronta energia consolidata e PR, e **Previsioni** affianca valori originali e corretti. Le **Impostazioni** restano in alto a destra, con le tre viste dati disponibili. Le categorie coprono connessione HA, moduli PV, sensori, previsioni e monitoraggio.

La sezione **Monitoraggio** è chiusa all’apertura delle Impostazioni. Seleziona il titolo o la voce nell’elenco delle categorie per mostrare i controlli. Il pulsante **?** accanto al titolo mostra la guida su contabilizzazione, media, aggiornamento e timeout dei sensori anche quando i controlli sono chiusi.

**Salva configurazione** mantiene aperte le Impostazioni. **Scarta modifiche** ricarica dal server la configurazione salvata e sostituisce le modifiche; se il caricamento fallisce, la bozza resta disponibile per riprovare. Uscendo con modifiche non salvate puoi continuare a modificarle o scartarle. Rientrare nelle Impostazioni ricarica la configurazione salvata.

Il menu **Modalità tema**, in alto a destra, offre Auto, Chiaro e Scuro. Auto segue la modalità di Home Assistant nella sua interfaccia e usa la preferenza di sistema senza un contesto Home Assistant accessibile. Chiaro o Scuro imposta una scelta locale; Auto ripristina il comportamento automatico. Cambiare lingua o tema conserva la bozza.

| Impostazione | Valore da inserire |
| --- | --- |
| Potenza massima totale in STC | Somma delle potenze massime dei moduli in condizioni di prova standard (STC) in W, ad esempio `5000`. |
| Coefficiente di temperatura di Pmax | Coefficiente Pmax della scheda del modulo in %/°C, ad esempio `-0,35`. |
| Potenza effettiva | Sensore della potenza prodotta dai pannelli (W o kW). |
| Temperatura dei moduli | Sensore della temperatura dei pannelli (°C, °F o K). |
| Irradianza | Sensore sullo stesso piano dei pannelli (W/m² o kW/m²). |
| Intervallo di contabilizzazione | Salva energia e PR ogni 1, 5 o 10 minuti per la vista **Efficienza**. L’intervallo predefinito è di 5 minuti. |
| Media su | Calcola i valori in tempo reale dagli ultimi 60 secondi per impostazione predefinita. Un intervallo più lungo attenua le variazioni a breve termine. |
| Aggiorna ogni | Ricalcola e aggiorna i valori in tempo reale ogni 5 secondi per impostazione predefinita. |
| Tempo senza nuovi dati | Imposta quanto attendere la prossima lettura di ogni sensore. I periodi oltre il limite contano come mancanti e riducono la completezza dei dati. |

In **Impostazioni > Moduli fotovoltaici**, scegli **Valore fisso** o **Entità HA** separatamente per inclinazione e direzione. Salva e apri **Panoramica**. Il primo risultato consolidato appare in **Efficienza** alla fine del periodo in corso.

La Panoramica precarica gli ultimi dieci minuti all’apertura o alla riconnessione. I dati di produzione mostrano oggi potenza stimata/effettiva consolidata, irradianza e temperatura dei moduli. Il grafico energetico propone 7 giorni predefiniti, 30 giorni o un intervallo personalizzato inclusivo di massimo 90 date domestiche, non oltre oggi. I dati mancanti restano vuoti e lo zero misurato rimane zero; contabilizzazioni e energia cumulativa non cambiano.

Efficienza mostra PR del periodo, variazione dal periodo precedente comparabile in punti percentuali ed energia stimata meno effettiva. Oggi si confronta con ieri fino alla stessa ora locale, 24 ore con le 24 precedenti, 7/30 giorni con lo stesso intervallo spostato di 7/30 date domestiche. I due grafici condividono riepilogo giornaliero o intervallo di contabilizzazione configurato.

Lo smussamento riguarda solo il disegno. Mouse, tocco e tastiera mostrano i record originali, anche gli intervalli di previsione di 15 minuti. Energia e PR usano valori non smussati. Date e previsioni seguono l’ora domestica; gli orari di monitoraggio e download seguono la preferenza HA server/local del lettore o il browser con Docker autonomo. Gli scostamenti UTC distinguono, quando necessario, gli orari ripetuti.

## Previsioni di produzione

La posizione e il fuso orario provengono dalla connessione Home Assistant salvata e si impostano in HA.

L’inclinazione va da 0° a 90° inclusi. L’azimut si misura in senso orario dal nord (0°) fino a 360° esclusi. Le direzioni fisse comprendono anche est (90°), sud (180°) e ovest (270°). Le entità angolari sono `sensor.*`, `number.*` o `input_number.*` con unità `°`. Seleziona **Aggiorna entità** nelle impostazioni della connessione per trovarle.

In **Moduli fotovoltaici**, inserisci la NOCT della scheda tecnica (oltre 20°C, massimo 80°C, valore predefinito 45°C). La potenza massima totale in STC e il coefficiente di temperatura di Pmax servono anche al monitoraggio. Per moduli identici, moltiplica la potenza nominale di un modulo per il numero di moduli, ad esempio 500 W × 10 = 5000 W.

A ogni aggiornamento gli angoli HA selezionati vengono letti una volta. La stessa coppia di angoli viene usata per stimare tutti gli intervalli di 15 minuti della previsione a sette giorni, compresi quelli già trascorsi oggi. La pagina delle previsioni mostra gli angoli usati e l’ora di lettura separatamente dall’ora di acquisizione dei dati meteo. Se un’entità è indisponibile, la pagina la indica e mostra gli intervalli ancora utilizzabili dell’ultima previsione. Senza una previsione utilizzabile, l’energia appare come **—** ed è possibile riprovare.

Il monitoraggio usa la **Temperatura dei moduli** misurata. Le previsioni usano la **Temperatura dell’aria** e la **Temperatura nominale di funzionamento della cella (NOCT)** per calcolare la **Temperatura stimata delle celle**. Sono grandezze distinte; il monitoraggio non converte la temperatura dei moduli in temperatura delle celle.

Open-Meteo fornisce dati del modello ogni 15 minuti per oggi e i sei giorni domestici successivi. Alcune regioni o variabili interpolano modelli orari; il passo di uscita non garantisce maggiore accuratezza. Seleziona una data per energia originale/corretta, curve di potenza e dettagli. Oggi comprende tutto il giorno; **Rimanente oggi** va da adesso alla mezzanotte domestica e diminuisce tra i download. Un giorno normale ha 96 intervalli, uno con cambio dell’ora 92 o 100.

Le schede mantengono meteo e massima/minima delle previsioni orarie accanto a coppie di barre energetiche e kWh. Il segno caldo **Oggi** segue la mezzanotte domestica indipendentemente dalla selezione blu. I riepiloghi meteo usano ancora campioni orari della stessa richiesta, cache e ora di download. Meteo ed energia possono mancare indipendentemente; zero resta valido.

Il meteo si aggiorna normalmente ogni ora o con **Aggiorna previsione**. La cache corrispondente sopravvive al riavvio. Un errore conserva l’ora di download, viene mostrato e comporta un nuovo tentativo dopo 15 minuti. Dati mancanti rendono indisponibili i totali interessati (**—**). Restano indicati posizione assente, caricamento e nessun dato.

La **Previsione originale** conserva il modello meteo/NOCT. La **Previsione corretta** lo moltiplica per il PR recente ponderato per energia, con più peso alle date domestiche completate più recenti. In **Impostazioni > Previsioni**, i giorni storici PR sono n=14 per default, intero 3–90; l’emivita è n/2 giorni. Servono almeno 3 date idonee con energia stimata positiva. Energia effettiva e stimata usano gli stessi periodi validi dopo l’ultima configurazione di monitoraggio comparabile. Lo zero effettivo è valido e il PR oltre 100% non è limitato. Senza abbastanza storico, la correzione mostra **—**, mentre i valori originali restano disponibili. Cambiare n ricalcola la correzione senza richiedere di nuovo il meteo.

La correzione riguarda solo pagina e API applicativa. I 13 identificatori e significati delle uscite HA restano invariati; le quattro entità di previsione conservano l’energia originale integrata dagli intervalli di 15 minuti.

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
