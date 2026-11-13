[English](README.md) | [中文](README.zh-CN.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Polski](README.pl.md) | **Italiano**

# PVYieldLens

Confronta la potenza prevista e quella effettiva dei pannelli. Segui il PR e l’energia prevista per oggi e in totale.

## Funzioni

- Potenza, PR e differenza di potenza in tempo reale.
- Storico di potenza e PR ogni 1, 5 o 10 minuti.
- Energia prevista per oggi e dal primo avvio.
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

**Tempo reale** mostra medie attuali e diagnostica, **Storico** i periodi conclusi e l’energia/PR dell’intervallo scelto, **Previsioni** le stime meteo. I totali del giorno e dall’avvio restano indipendenti dall’intervallo. L’ingranaggio apre **Impostazioni**: Connessione a Home Assistant, Pannelli solari, Sensori, Monitoraggio e Previsioni. Poi puoi tornare alla vista precedente; la lingua si sceglie sempre in alto a destra.

| Impostazione | Valore da inserire |
| --- | --- |
| Potenza nominale totale | Somma delle potenze dei pannelli in W, ad esempio `5000`. |
| Coefficiente di temperatura K | Valore della scheda del pannello in %/°C, ad esempio `-0,35`. |
| Potenza fotovoltaica | Sensore della potenza prodotta dai pannelli (W o kW). |
| Temperatura dei moduli | Sensore della temperatura dei pannelli (°C, °F o K). |
| Luce sui pannelli | Sensore sullo stesso piano dei pannelli (W/m² o kW/m²). |
| Intervallo dello storico | 1, 5 o 10 minuti. Predefinito: 5 minuti. |
| Media su | Tempo usato per la media in tempo reale. Predefinito: 60 secondi. |
| Aggiorna ogni | Tempo tra gli aggiornamenti. Predefinito: 5 secondi. |

Salva e apri **Tempo reale**. Il primo risultato consolidato appare nello **Storico** alla fine del periodo in corso. In **Tempo senza nuovi dati**, imposta quanto attendere un aggiornamento da ogni sensore.

## Previsioni di produzione

Le previsioni sono disattivate per impostazione predefinita, anche dopo un aggiornamento. In **Impostazioni > Previsioni**, attivale e inserisci inclinazione (0–90°), direzione (nord 0°, est 90°, sud 180°, ovest 270° o azimut personalizzato da 0° a meno di 360°) e NOCT della scheda tecnica (oltre 20°C, massimo 80°C; predefinito 45°C). Potenza nominale e K sono condivisi con il monitoraggio. Posizione e fuso provengono automaticamente dalla connessione HA salvata; modificali in HA.

Open-Meteo fornisce il meteo orario per oggi e i sei giorni di calendario locali successivi. Scegli una data per energia giornaliera, curva oraria e tabella degli intervalli con scostamenti UTC. La previsione di oggi comprende tutto il giorno; **Rimanente oggi** solo il tempo da adesso alla mezzanotte locale. Entrambe usano l’ultimo meteo scaricato correttamente e sono distinte dall’energia teorica consolidata calcolata dai sensori. L’energia rimanente diminuisce con il tempo tra i download; nuovi dati possono anche modificare la stima dell’intera giornata.

Il meteo si aggiorna ogni ora o con **Aggiorna previsione**. La cache corrispondente resta dopo il riavvio. Un errore conserva l’ora del download e segnala dati obsoleti; nuovo tentativo dopo 15 minuti. Anche i dati vecchi di almeno due ore sono obsoleti. Gli intervalli mancanti rendono indisponibili i totali interessati; la completezza è mostrata separatamente e i dati mancanti non valgono zero. Sono indicati disattivazione, posizione HA assente, primo caricamento e indisponibilità.

Sono riferimenti teorici in corrente continua per un solo campo di pannelli, con irraggiamento sul loro piano e modello termico NOCT semplificato. Non includono efficienza/limitazione dell’inverter, ombre, neve, sporco o perdite e non garantiscono la produzione reale in corrente alternata. Le quattro entità hanno kWh e classe energy, senza `state_class`; possono diminuire e restano separate dai contatori cumulativi. Non forniscono un’integrazione nativa con previsioni HA o dashboard Energia.

## Sensori di uscita

| Risultato | ID entità | Unità |
| --- | --- | --- |
| Potenza prevista | `sensor.pvyieldlens_estimated_power` | W |
| Potenza effettiva | `sensor.pvyieldlens_actual_power` | W |
| PR | `sensor.pvyieldlens_pr` | % |
| Energia prevista oggi | `sensor.pvyieldlens_daily_estimated_energy` | kWh |
| Energia prevista totale | `sensor.pvyieldlens_total_estimated_energy` | kWh |
| Potenza prevista in tempo reale | `sensor.pvyieldlens_realtime_estimated_power` | W |
| Potenza effettiva in tempo reale | `sensor.pvyieldlens_realtime_actual_power` | W |
| PR in tempo reale | `sensor.pvyieldlens_realtime_pr` | % |
| Differenza di potenza in tempo reale | `sensor.pvyieldlens_realtime_optimizable_power` | W |
| Previsione oggi | `sensor.pvyieldlens_forecast_energy_today` | kWh |
| Previsione restante oggi | `sensor.pvyieldlens_forecast_energy_remaining_today` | kWh |
| Previsione domani | `sensor.pvyieldlens_forecast_energy_tomorrow` | kWh |
| Previsione per 7 giorni | `sensor.pvyieldlens_forecast_energy_7d` | kWh |

## Formula del PR

La potenza prevista tiene conto della potenza nominale, della temperatura e della luce solare:

```text
P_expected = P_rated × [1 + (K / 100) × (T − 25)] × G / 1000
PR = P_actual / P_expected × 100%
```

`P_rated`: potenza nominale (W); `K`: coefficiente di temperatura (%/°C); `T`: temperatura dei pannelli (°C); `G`: radiazione ricevuta dai pannelli (W/m²).

Il PR confronta la potenza effettiva con quella prevista. La differenza è la potenza prevista meno quella effettiva.

## Leggere i risultati

- Il PR può superare il 100%. Quando la potenza prevista è zero, il PR non è mostrato.
- Una differenza negativa indica che la potenza effettiva è maggiore di quella prevista.
- L’energia è contata solo quando tutti e tre i sensori hanno dati. I periodi mancanti sono esclusi.
- L’energia del giorno si azzera a mezzanotte nel fuso di Home Assistant. Il totale parte dalla prima configurazione.

Dopo un’interruzione, alcuni periodi possono rimanere senza dati. Conserva i dati dell’app durante gli aggiornamenti o la reinstallazione. Per l’app usa i backup di Home Assistant; con Docker autonomo, arresta il contenitore prima di copiare la cartella `/data`.
