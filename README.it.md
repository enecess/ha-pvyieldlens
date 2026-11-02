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

[![Aggiungi il repository di app PVYieldLens](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fenecess%2Fha-pvyieldlens)

1. Premi il pulsante qui sopra e conferma **Aggiungi** in Home Assistant.
2. Trova **PVYieldLens** nello store delle app, poi installa e avvia l’app.
3. Apri la pagina Web e vai in **Impostazioni** per scegliere i sensori e inserire i dati dei pannelli.

Se il pulsante non apre Home Assistant, vai in **Impostazioni > App > Installa app > menu in alto a destra > Repository** e aggiungi:

```text
https://github.com/enecess/ha-pvyieldlens
```

### Docker

Scarica questo repository e apri la sua cartella. Crea il file delle impostazioni:

```sh
cp .env.example .env
```

In `.env`, scegli una password per `PVYL_WEB_PASSWORD`, poi avvia l’app:

```sh
docker compose up -d --build
```

Apri [localhost:8099](http://localhost:8099). Accedi come `admin` con la password scelta. In **Impostazioni**, inserisci l’indirizzo di Home Assistant e il token di accesso, poi premi **Carica sensori**.

La pagina è accessibile dal computer con Docker. Per aprirla da un altro dispositivo, cambia `127.0.0.1:8099:8099` in `8099:8099` nel file `compose.yaml`.

## Impostazioni

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

Salva e apri **Panoramica**. Il primo risultato nello storico appare alla fine del periodo in corso. In **Tempo senza nuovi dati**, imposta quanto attendere un aggiornamento da ogni sensore.

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
