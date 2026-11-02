[English](README.md) | [中文](README.zh-CN.md) | [Français](README.fr.md) | **Deutsch** | [Polski](README.pl.md) | [Italiano](README.it.md)

# PVYieldLens

Vergleichen Sie die erwartete und die tatsächliche Leistung Ihrer Solarmodule. Sehen Sie PR und erwartete Energie für heute und insgesamt.

## Funktionen

- Leistung, PR und Differenz in Echtzeit.
- Verlauf für Leistung und PR in 1, 5 oder 10 Minuten.
- Erwartete Energie für heute und seit dem Start.
- Diagramme für 24 Stunden, 7 Tage oder 30 Tage.
- Sechs Sprachen, wählbar oben rechts.

## Schnellstart

### Home Assistant App

Für Home Assistant OS.

[![PVYieldLens-App-Repository hinzufügen](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fenecess%2Fha-pvyieldlens)

1. Klicken Sie auf die Schaltfläche oben und bestätigen Sie **Hinzufügen** in Home Assistant.
2. Suchen Sie **PVYieldLens** im App Store, installieren und starten Sie die App.
3. Öffnen Sie die Web-Seite und wählen Sie unter **Einstellungen** Ihre Sensoren und Modulwerte.

Falls die Schaltfläche Home Assistant nicht öffnet, gehen Sie zu **Einstellungen > Apps > App installieren > Menü oben rechts > Repositories** und fügen Sie diese Adresse hinzu:

```text
https://github.com/enecess/ha-pvyieldlens
```

### Docker

Laden Sie dieses Repository herunter und öffnen Sie den Ordner. Erstellen Sie die Einstellungsdatei:

```sh
cp .env.example .env
```

Tragen Sie in `.env` Ihr Passwort bei `PVYL_WEB_PASSWORD` ein und starten Sie die App:

```sh
docker compose up -d --build
```

Öffnen Sie [localhost:8099](http://localhost:8099). Melden Sie sich als `admin` mit Ihrem Passwort an. Geben Sie unter **Einstellungen** die Home-Assistant-Adresse und das Zugriffstoken ein. Klicken Sie auf **Sensoren laden**.

Die Seite ist zunächst nur auf dem Docker-Rechner erreichbar. Für andere Geräte ändern Sie `127.0.0.1:8099:8099` in `compose.yaml` zu `8099:8099`.

## Einstellungen

| Einstellung | Eingabe |
| --- | --- |
| Gesamtnennleistung | Summe der Modulleistungen in W, z. B. `5000`. |
| Temperaturfaktor K | Wert aus dem Modul-Datenblatt in %/°C, z. B. `-0,35`. |
| PV-Leistung | Sensor für die erzeugte Solarleistung (W oder kW). |
| Modultemperatur | Temperatursensor am Modul (°C, °F oder K). |
| Strahlung am Modul | Sensor in der gleichen Ebene wie die Module (W/m² oder kW/m²). |
| Verlauf: Zeitabstand | 1, 5 oder 10 Minuten. Standard: 5 Minuten. |
| Mittelwert über | Zeitraum für den aktuellen Mittelwert. Standard: 60 Sekunden. |
| Update alle | Abstand zwischen Updates. Standard: 5 Sekunden. |

Speichern Sie die Werte und öffnen Sie **Übersicht**. Der erste Verlaufseintrag erscheint am Ende des laufenden Zeitraums. Unter **Zeit ohne neue Daten** legen Sie die Wartezeit für jeden Sensor fest.

## Ergebnis-Sensoren

| Ergebnis | Entitäts-ID | Einheit |
| --- | --- | --- |
| Erwartete Leistung | `sensor.pvyieldlens_estimated_power` | W |
| Tatsächliche Leistung | `sensor.pvyieldlens_actual_power` | W |
| PR | `sensor.pvyieldlens_pr` | % |
| Erwartete Energie heute | `sensor.pvyieldlens_daily_estimated_energy` | kWh |
| Erwartete Energie gesamt | `sensor.pvyieldlens_total_estimated_energy` | kWh |
| Erwartete Live-Leistung | `sensor.pvyieldlens_realtime_estimated_power` | W |
| Tatsächliche Live-Leistung | `sensor.pvyieldlens_realtime_actual_power` | W |
| Live-PR | `sensor.pvyieldlens_realtime_pr` | % |
| Live-Differenz | `sensor.pvyieldlens_realtime_optimizable_power` | W |

## PR-Formel

Die erwartete Leistung hängt von Modulgröße, Temperatur und Strahlung ab:

```text
P_expected = P_rated × [1 + (K / 100) × (T − 25)] × G / 1000
PR = P_actual / P_expected × 100%
```

`P_rated`: Nennleistung (W); `K`: Temperaturfaktor (%/°C); `T`: Modultemperatur (°C); `G`: Strahlung auf die Module (W/m²).

PR vergleicht die tatsächliche mit der erwarteten Leistung. Die Differenz ist die erwartete minus die tatsächliche Leistung.

## Ergebnisse verstehen

- PR kann über 100 % liegen. Bei erwarteter Leistung null wird kein PR angezeigt.
- Eine negative Differenz heißt: Die tatsächliche Leistung ist höher als erwartet.
- Energie wird nur gezählt, wenn alle drei Sensoren Daten haben. Fehlende Zeiten werden ausgelassen.
- Die Tagesenergie wird um Mitternacht in der Home-Assistant-Zeitzone auf null gesetzt. Die Gesamtenergie zählt seit der ersten Einrichtung.
