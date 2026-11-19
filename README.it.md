[English](README.md) | [中文](README.zh-CN.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Polski](README.pl.md) | **Italiano**

# PVYieldLens

## Panoramica del progetto

PVYieldLens confronta la produzione solare misurata con quella che il tuo impianto fotovoltaico potrebbe generare nelle condizioni osservate. Segui l’indice di prestazione (PR) in Home Assistant e consulta le previsioni di produzione per sette giorni.

## Installazione

### Home Assistant OS

L’app richiede Home Assistant 2025.9.0 o una versione successiva.

[![Aggiungi il repository di app PVYieldLens](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fenecess%2Fha-pvyieldlens%23dev_v0)

1. Usa il pulsante qui sopra e conferma con **Aggiungi** in Home Assistant. Per aggiungere il repository a mano, apri **Impostazioni > Applicazioni > Installa app > ⋮ > Archivi digitali** e inserisci `https://github.com/enecess/ha-pvyieldlens#dev_v0`.
2. Cerca **PVYieldLens** nella **Raccolta delle app** e seleziona **Installa**.
3. Seleziona **Avvia**, poi **Apri interfaccia utente Web**.

Prima di Home Assistant 2026.2, apri **Impostazioni > Componenti aggiuntivi > Negozio dei componenti aggiuntivi** e aggiungi il repository dal menu ⋮.

### Docker

1. Scarica il repository e apri la cartella. Copia `.env.example` in `.env` e imposta la password in `PVYL_WEB_PASSWORD`.
2. Esegui `docker compose up -d --build`.
3. Sul computer che esegue Docker, apri [localhost:8099](http://localhost:8099) e accedi come `admin` con la password scelta.

Per accedere da un altro dispositivo, cambia la mappatura delle porte in `compose.yaml` da `127.0.0.1:8099:8099` a `8099:8099`.

## Configurazione

Apri **Impostazioni** in PVYieldLens. Usa il menu **Lingua** in alto a destra per cambiare la lingua dell’interfaccia.

### Connessione a Home Assistant

L’app Home Assistant si collega automaticamente. Con Docker, inserisci l’**URL di Home Assistant** e un **Token di accesso a lunga durata** di un amministratore di Home Assistant. Poi seleziona **Aggiorna entità**. Per pubblicare i sensori di uscita servono i permessi di amministratore.

Inserisci il token al primo avvio o quando cambi l’URL. Se l’URL è lo stesso, lascia vuoto il campo per riutilizzare il token salvato.

### Moduli fotovoltaici

| Impostazione | Valore da inserire |
| --- | --- |
| **Potenza massima totale in STC** | Somma le potenze nominali dei moduli in W. Dieci moduli da 500 W danno 5.000 W. |
| **Coefficiente di temperatura di Pmax** | Valore riportato nella scheda tecnica in %/°C, per esempio −0,35. |
| **Inclinazione dei moduli** | Da 0° a 90°. |
| **Orientamento dei moduli** | Azimut in senso orario dal nord (0°), inferiore a 360°. Scegli un punto cardinale o **Personalizzato**. |
| **Temperatura nominale di funzionamento della cella (NOCT)** | Valore della scheda tecnica superiore a 20 °C e fino a 80 °C. Il valore predefinito è 45 °C. |

Per inclinazione e orientamento puoi scegliere separatamente **Valore fisso** o **Entità HA**. Seleziona un’entità `sensor.*`, `number.*` o `input_number.*` che restituisce un angolo in gradi (°). Con un inseguitore, ogni aggiornamento usa gli angoli letti in quel momento per l’intera previsione.

*L’impianto Berlin Demo da 5.000 W è inclinato di 35° e orientato a **Sud · 180°**.*

<!-- screenshot: settings-pv-modules.png -->

### Sensori

| Impostazione | Sensore e unità supportate |
| --- | --- |
| **Potenza effettiva** | Potenza fotovoltaica in W o kW. |
| **Irradianza** | Irradianza sul piano dei moduli in W/m² o kW/m². |
| **Temperatura dei moduli (facoltativa)** | Temperatura dei moduli in °C, °F o K. Lascia vuoto per stimarla a partire da temperatura dell’aria di Open-Meteo, irradianza misurata e NOCT. |

*Berlin Demo usa sensori simulati per potenza, irradianza e temperatura dei moduli.*

<!-- screenshot: settings-sensors.png -->

### Previsioni

Apri **Previsioni** dentro **Impostazioni** per controllare posizione e fuso orario. Modificali in Home Assistant. **Giorni di storico PR** imposta il periodo considerato per la correzione. L’impostazione predefinita è 14 giorni.

### Monitoraggio

Per impostazione predefinita, PVYieldLens contabilizza energia e PR ogni 5 minuti. I valori in tempo reale sono la media degli ultimi 60 secondi e si aggiornano ogni 5 secondi. Quando un sensore supera il proprio **Tempo senza nuovi dati**, il periodo interessato risulta privo di dati.

Seleziona **Salva configurazione**.

## Risultati

### Panoramica

Confronta potenza effettiva e stimata, **PR** e **Potenza ottimizzabile**. **Dati in tempo reale** mostra la potenza degli ultimi dieci minuti.

*Potenza in tempo reale e PR in Berlin Demo.*

<!-- screenshot: dashboard.png -->

In **Dati di produzione** trovi potenza, irradianza e temperatura dei moduli per gli intervalli contabilizzati della giornata.

*Produzione contabilizzata di oggi e letture dei sensori in Berlin Demo.*

<!-- screenshot: dashboard-generation.png -->

**Produzione storica** confronta l’energia giornaliera effettiva e stimata. Seleziona **7 giorni**, **30 giorni** o **Personalizzato** per un massimo di 90 giorni di calendario. Per vedere gli ultimi sette giorni completi come in Berlin Demo, seleziona **Personalizzato**, imposta ieri come data finale e inizia sei giorni prima.

*Produzione giornaliera in Berlin Demo per sette giorni completi.*

<!-- screenshot: dashboard-history.png -->

Il PR in tempo reale è il rapporto percentuale tra potenza effettiva e stimata. Può superare il 100%. La **Potenza ottimizzabile** (potenza stimata meno potenza effettiva) può essere negativa. I dati mancanti lasciano spazi vuoti. Un valore misurato pari a zero resta zero. Se la potenza stimata è zero, il PR mostra **—**.

### Efficienza

Seleziona **Oggi**, **24 ore**, **7 giorni** o **30 giorni**. **Oggi** confronta la produzione con ieri fino alla stessa ora locale. **7 giorni** include oggi.

Consulta il PR del periodo, la variazione in punti percentuali e la differenza tra energia stimata ed effettiva. **Andamento PR** e **Confronto produzione** mostrano come cambiano i valori. Per intervalli di calendario, puoi passare da **Riepilogo giornaliero** alla visualizzazione per intervallo di contabilizzazione. Il PR del periodo divide l’energia effettiva per quella stimata negli stessi intervalli validi e contabilizzati.

*Efficienza di oggi in Berlin Demo, confrontata con ieri fino alla stessa ora.*

<!-- screenshot: efficiency.png -->

### Previsioni

Confronta la **Previsione originale** e la **Previsione corretta** per oggi e i prossimi sei giorni. La previsione originale usa il meteo di Open-Meteo e le impostazioni dell’impianto. La correzione si basa sul PR recente ponderato per l’energia e richiede almeno tre giorni completi idonei con energia stimata positiva. Fino ad allora i valori corretti mostrano **—**.

Le schede mostrano la giornata di oggi per intero, **Rimanente oggi** e **Previsione di domani**. La sezione **Energia prevista per giorno** confronta i sette giorni e mostra il **Totale di 7 giorni**. Seleziona **Aggiorna previsione** per richiedere nuovi dati meteo.

*Previsioni di energia originali e corrette in Berlin Demo, selezione della data e pulsante **Esporta CSV**.*

<!-- screenshot: forecast.png -->

Seleziona una data per confrontare le curve di potenza. Apri **Dettagli ogni 15 minuti** per vedere potenza, energia, irradianza e temperature per ogni intervallo.

*Curve di potenza e dettagli ogni 15 minuti della data selezionata in Berlin Demo.*

<!-- screenshot: forecast-details.png -->

Con EMHASS e un solo inverter fotovoltaico, seleziona **Esporta CSV** e scegli la serie originale o corretta. Imposta inizio, intervallo e numero di passi in base alla tua ottimizzazione. Salva `data_weather_forecast.csv` nel `data_path` di EMHASS e imposta `set_use_pv=true` e `weather_forecast_method=csv`. [Configurazione di EMHASS](pvyieldlens/DOCS.md#export-a-pv-power-forecast-to-emhass)

### Sensori di uscita in Home Assistant

| Metrica | Nome entità HA | Unità |
| --- | --- | --- |
| Potenza stimata contabilizzata | `settled_estimated_power` | W |
| Potenza effettiva contabilizzata | `settled_actual_power` | W |
| PR contabilizzato | `settled_pr` | % |
| Energia stimata oggi | `estimated_energy_today` | kWh |
| Energia stimata cumulativa | `estimated_energy_lifetime` | kWh |
| Potenza stimata in tempo reale | `live_estimated_power` | W |
| Potenza effettiva in tempo reale | `live_actual_power` | W |
| PR in tempo reale | `live_pr` | % |
| Potenza ottimizzabile in tempo reale | `live_optimizable_power` | W |
| Energia prevista oggi | `forecast_energy_today` | kWh |
| Energia prevista per il resto di oggi | `forecast_energy_remaining_today` | kWh |
| Energia prevista domani | `forecast_energy_tomorrow` | kWh |
| Energia prevista in 7 giorni | `forecast_energy_7d` | kWh |

La tabella mostra i nomi visualizzati in Home Assistant. Nelle automazioni usa l’ID completo, per esempio `sensor.pvyieldlens_settled_estimated_power`. I quattro sensori di previsione riportano l’energia della **Previsione originale**. L’energia stimata di oggi si azzera a mezzanotte nel fuso orario di casa. Il totale parte dalla prima configurazione.
