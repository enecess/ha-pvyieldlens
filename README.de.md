[English](README.md) | [中文](README.zh-CN.md) | [Français](README.fr.md) | **Deutsch** | [Polski](README.pl.md) | [Italiano](README.it.md)

# PVYieldLens

## Überblick

PVYieldLens vergleicht den gemessenen Solarertrag mit dem Ertrag, den Ihre PV-Anlage unter den beobachteten Bedingungen liefern könnte. Verfolgen Sie die Performance Ratio (PR) in Home Assistant und sehen Sie die Ertragsprognose für sieben Tage.

## Installation

### Home Assistant OS

Die App benötigt Home Assistant 2025.9.0 oder neuer.

[![PVYieldLens-App-Repository hinzufügen](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fenecess%2Fha-pvyieldlens%23dev_v0)

1. Klicken Sie oben auf die Schaltfläche und bestätigen Sie **Hinzufügen** in Home Assistant. Zum manuellen Hinzufügen öffnen Sie **Einstellungen > Apps > App installieren > ⋮ > Repositorys** und geben `https://github.com/enecess/ha-pvyieldlens#dev_v0` ein.
2. Suchen Sie **PVYieldLens** im **App-Store** und wählen Sie **Installieren**.
3. Wählen Sie **Starten** und dann **Benutzeroberfläche öffnen**.

Vor Home Assistant 2026.2 öffnen Sie **Einstellungen > Add-ons > Add-on Store** und fügen das Repository über das ⋮-Menü hinzu.

### Docker

1. Laden Sie dieses Repository herunter und öffnen Sie den Ordner. Kopieren Sie `.env.example` nach `.env` und setzen Sie Ihr Passwort in `PVYL_WEB_PASSWORD`.
2. Führen Sie `docker compose up -d --build` aus.
3. Öffnen Sie [localhost:8099](http://localhost:8099) auf dem Docker-Host und melden Sie sich als `admin` mit dem gewählten Passwort an.

Für den Zugriff von einem anderen Gerät ändern Sie in `compose.yaml` die Portzuordnung von `127.0.0.1:8099:8099` auf `8099:8099`.

## Konfiguration

Öffnen Sie in PVYieldLens die **Einstellungen**. Das Menü **Sprache** oben rechts wechselt die Sprache der Oberfläche.

### Home-Assistant-Verbindung

Die Home-Assistant-App verbindet sich automatisch. Geben Sie bei Docker die **Home-Assistant-URL** und ein **Langlebiges Zugriffstoken** eines Home-Assistant-Administrators ein. Wählen Sie dann **Entitäten aktualisieren**. Zum Veröffentlichen der Ausgabesensoren sind Administratorrechte erforderlich.

Geben Sie bei der ersten Einrichtung und nach einem URL-Wechsel ein Token ein. Bei derselben URL können Sie das Feld leer lassen, um das gespeicherte Token weiterzuverwenden.

### PV-Module

| Einstellung | Eingabe |
| --- | --- |
| **Gesamte Maximalleistung unter STC** | Addieren Sie die Modulleistungen in W. Zehn Module mit je 500 W ergeben 5.000 W. |
| **Temperaturkoeffizient von Pmax** | Wert aus dem Datenblatt in %/°C, z. B. −0,35. |
| **Modulneigung** | 0° bis 90°. |
| **Modulausrichtung** | Azimut im Uhrzeigersinn ab Norden (0°), unter 360°. Wählen Sie eine Himmelsrichtung oder **Benutzerdefiniert**. |
| **Nominale Zellbetriebstemperatur (NOCT)** | Datenblattwert über 20 °C und bis 80 °C. Standardwert 45 °C. |

Wählen Sie für Neigung und Ausrichtung jeweils **Fester Wert** oder **HA-Entität**. Als Winkelquelle dient eine Entität `sensor.*`, `number.*` oder `input_number.*` mit der Einheit Grad (°). Bei einer nachgeführten Anlage verwendet jede Aktualisierung die zu diesem Zeitpunkt gelesenen Winkel für die gesamte Prognose.

*Die 5.000-W-Anlage in Berlin Demo ist um 35° geneigt und nach **Süd · 180°** ausgerichtet.*

<!-- screenshot: settings-pv-modules.png -->

### Sensoren

| Einstellung | Sensor und unterstützte Einheiten |
| --- | --- |
| **Tatsächliche Leistung** | PV-Erzeugungsleistung in W oder kW. |
| **Bestrahlungsstärke** | Bestrahlungsstärke in der Modulebene in W/m² oder kW/m². |
| **Modultemperatur (optional)** | Modultemperatur in °C, °F oder K. Wenn das Feld leer bleibt, wird sie anhand der Open-Meteo-Lufttemperatur, der gemessenen Bestrahlungsstärke und der NOCT geschätzt. |

*Berlin Demo verwendet simulierte Sensoren für Leistung, Bestrahlungsstärke und Modultemperatur.*

<!-- screenshot: settings-sensors.png -->

### Prognose

Prüfen Sie den Standort und die Zeitzone unter **Prognose** in den **Einstellungen**. Änderungen nehmen Sie in Home Assistant vor. **PR-Verlauf in Tagen** bestimmt den Zeitraum für die Prognosekorrektur. Der Standardwert beträgt 14 Tage.

### Überwachung

Standardmäßig berechnet PVYieldLens Energie und PR je 5 Minuten. Live-Werte mitteln die letzten 60 Sekunden und werden alle 5 Sekunden aktualisiert. Überschreitet ein Sensor seine **Zeit ohne neue Daten**, gilt der betroffene Zeitraum als fehlend.

Wählen Sie **Konfiguration speichern**.

## Ergebnisse

### Übersicht

Vergleichen Sie tatsächliche und geschätzte Leistung, den **PR** und die **Optimierbare Leistung**. **Live-Daten** zeigt den Leistungsverlauf der letzten zehn Minuten.

*Live-Leistung und PR in Berlin Demo.*

<!-- screenshot: dashboard.png -->

Unter **Ertragsdaten** finden Sie Leistung, Bestrahlungsstärke und Modultemperatur für die abgeschlossenen Intervalle des heutigen Tages.

*Heutige Ertragsdaten und Sensorwerte für abgeschlossene Intervalle in Berlin Demo.*

<!-- screenshot: dashboard-generation.png -->

**Bisheriger Energieertrag** vergleicht die tägliche tatsächliche und geschätzte Energie. Wählen Sie **7 Tage**, **30 Tage** oder **Benutzerdefiniert** für bis zu 90 Kalendertage. Für die letzten sieben vollständigen Tage wie in Berlin Demo wählen Sie **Benutzerdefiniert**. Setzen Sie das Ende auf gestern und den Beginn sechs Tage davor.

*Täglicher Energieertrag in Berlin Demo für sieben vollständige Tage.*

<!-- screenshot: dashboard-history.png -->

Der Live-PR ist der Quotient aus tatsächlicher und geschätzter Leistung in Prozent. Er kann über 100 % liegen. Die **Optimierbare Leistung** (geschätzte minus tatsächliche Leistung) kann negativ sein. Fehlende Messwerte hinterlassen Lücken. Ein gemessener Nullwert bleibt null. Bei geschätzter Leistung von null erscheint **—** für den PR.

### Effizienz

Wählen Sie **Heute**, **24 Stunden**, **7 Tage** oder **30 Tage**. **Heute** vergleicht den Ertrag mit gestern bis zur gleichen Ortszeit. **7 Tage** schließt heute ein.

Sehen Sie den PR im Zeitraum, seine Änderung in Prozentpunkten und die Differenz zwischen geschätzter und tatsächlicher Energie. **PR-Verlauf** und **Ertragsvergleich** zeigen die Entwicklung. Bei Kalenderzeiträumen können Sie zwischen der Ansicht **Tägliche Zusammenfassung** und der Anzeige nach Abrechnungsintervall wechseln. Der PR im Zeitraum ergibt sich aus tatsächlicher geteilt durch geschätzte Energie derselben gültigen abgeschlossenen Intervalle.

*Heutige Effizienz in Berlin Demo im Vergleich zu gestern bis zur gleichen Uhrzeit.*

<!-- screenshot: efficiency.png -->

### Prognose

Vergleichen Sie die Werte unter **Ursprüngliche Prognose** und **Korrigierte Prognose** für heute und die nächsten sechs Tage. Die ursprüngliche Prognose verwendet Open-Meteo-Wetterdaten und Ihre Anlageneinstellungen. Die Korrektur verwendet den jüngsten energiegewichteten PR und benötigt mindestens drei geeignete vollständige Tage mit positiver geschätzter Energie. Bis dahin zeigen die korrigierten Werte **—**.

Die Karten zeigen den ganzen heutigen Tag, **Heute verbleibend** und **Prognose für morgen**. **Tägliche Energieprognose** vergleicht die sieben Tage und zeigt die **Summe für 7 Tage**. Wählen Sie **Prognose aktualisieren**, um neue Wetterdaten anzufordern.

*Ursprüngliche und korrigierte Energieprognosen in Berlin Demo mit Datumsauswahl und **CSV exportieren**.*

<!-- screenshot: forecast.png -->

Wählen Sie ein Datum für den Vergleich der Leistungskurven. Öffnen Sie **15-Minuten-Details** für Leistung, Energie, Bestrahlungsstärke und Temperaturen je Intervall.

*Leistungskurven und 15-Minuten-Details für das ausgewählte Datum in Berlin Demo.*

<!-- screenshot: forecast-details.png -->

Für EMHASS mit einem einzelnen PV-Wechselrichter wählen Sie **CSV exportieren** und die ursprüngliche oder korrigierte Reihe. Stimmen Sie Start, Intervall und Schrittzahl auf den Optimierungslauf ab. Speichern Sie `data_weather_forecast.csv` im EMHASS-Verzeichnis `data_path` und setzen Sie `set_use_pv=true` sowie `weather_forecast_method=csv`. [EMHASS-Einrichtung](pvyieldlens/DOCS.md#export-a-pv-power-forecast-to-emhass)

### Ausgabesensoren in Home Assistant

| Messgröße | HA-Entitätsname | Einheit |
| --- | --- | --- |
| Abgerechnete geschätzte Leistung | `settled_estimated_power` | W |
| Abgerechnete tatsächliche Leistung | `settled_actual_power` | W |
| Abgerechneter PR | `settled_pr` | % |
| Geschätzte Energie heute | `estimated_energy_today` | kWh |
| Geschätzte Energie insgesamt | `estimated_energy_lifetime` | kWh |
| Geschätzte Live-Leistung | `live_estimated_power` | W |
| Tatsächliche Live-Leistung | `live_actual_power` | W |
| Live-PR | `live_pr` | % |
| Optimierbare Live-Leistung | `live_optimizable_power` | W |
| Prognostizierte Energie heute | `forecast_energy_today` | kWh |
| Prognostizierte Energie für den Rest des Tages | `forecast_energy_remaining_today` | kWh |
| Prognostizierte Energie morgen | `forecast_energy_tomorrow` | kWh |
| Prognostizierte Energie für 7 Tage | `forecast_energy_7d` | kWh |

Die Tabelle zeigt die Anzeigenamen in Home Assistant. Verwenden Sie in Automatisierungen die vollständige ID, z. B. `sensor.pvyieldlens_settled_estimated_power`. Die vier Prognosesensoren melden die unter **Ursprüngliche Prognose** angezeigte Energie. Die geschätzte Tagesenergie startet um Mitternacht in der Zeitzone des Zuhauses bei null. Der Gesamtwert zählt ab der Ersteinrichtung.
