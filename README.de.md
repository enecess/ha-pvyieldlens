[English](README.md) | [中文](README.zh-CN.md) | [Français](README.fr.md) | **Deutsch** | [Polski](README.pl.md) | [Italiano](README.it.md)

# PVYieldLens

Vergleichen Sie die geschätzte und die tatsächliche Leistung Ihrer Solarmodule. Sehen Sie PR und geschätzte Energie für heute und insgesamt.

## Funktionen

- Leistung, PR und optimierbare Leistung in Echtzeit.
- Verlauf für Leistung und PR in 1, 5 oder 10 Minuten.
- Geschätzte Energie für heute und seit dem Start.
- Diagramme für 24 Stunden, 7 Tage oder 30 Tage.
- Sechs Sprachen, wählbar oben rechts.

## Schnellstart

### Home Assistant App

Für Home Assistant OS.

[![PVYieldLens-App-Repository hinzufügen](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fenecess%2Fha-pvyieldlens%23dev_v0)

1. Klicken Sie auf die Schaltfläche oben und bestätigen Sie **Hinzufügen** in Home Assistant.
2. Suchen Sie **PVYieldLens** im App Store, installieren und starten Sie die App.
3. Öffnen Sie die Web-Seite und wählen Sie unter **Einstellungen** Ihre Sensoren und Modulwerte.

Falls die Schaltfläche Home Assistant nicht öffnet, gehen Sie zu **Einstellungen > Apps > App installieren > Menü oben rechts > Repositories** und fügen Sie diese Adresse hinzu:

```text
https://github.com/enecess/ha-pvyieldlens#dev_v0
```

Bei Home Assistant vor Version 2026.2 verwenden Sie **Einstellungen > Add-ons > Add-on Store > Menü oben rechts > Repositories**. Die App benötigt Home Assistant 2025.9.0 oder neuer.

### Docker

Laden Sie dieses Repository herunter und öffnen Sie den Ordner. Erstellen Sie die Einstellungsdatei:

```sh
cp .env.example .env
```

Tragen Sie in `.env` Ihr Passwort bei `PVYL_WEB_PASSWORD` ein und starten Sie die App:

```sh
docker compose up -d --build
```

Öffnen Sie [localhost:8099](http://localhost:8099). Melden Sie sich als `admin` mit Ihrem Passwort an. Geben Sie für die erste Verbindung unter **Einstellungen** die Home-Assistant-Adresse und ein langlebiges Zugriffstoken eines Home-Assistant-**Administrators** ein und klicken Sie auf **Sensoren aktualisieren**. Wenn Adresse und Token bereits konfiguriert sind, werden die Sensoren beim ersten Öffnen der **Einstellungen** automatisch geladen. Verwenden Sie **Sensoren aktualisieren** nach einer Verbindungsänderung, zum Aktualisieren der Liste oder für einen erneuten Versuch nach einem Fehler. Zum Veröffentlichen der Ergebnis-Sensoren sind Administratorrechte erforderlich.

Die Seite ist zunächst nur auf dem Docker-Rechner erreichbar. Für andere Geräte ändern Sie `127.0.0.1:8099:8099` in `compose.yaml` zu `8099:8099`.

## Einstellungen

**Live** zeigt aktuelle Sensormittelwerte und Diagnosen, **Verlauf** abgeschlossene Zeiträume samt Energie/PR im gewählten Bereich und **Prognose** wetterbasierte Erträge. Der separate Eintrag **Einstellungen** mit Zahnrad und Text liegt oben rechts; alle drei Datenreiter bleiben erreichbar. Das Kategorienverzeichnis scrollt durch ein zusammenhängendes Formular: Home-Assistant-Verbindung, PV-Module, Sensoren, Überwachung und Prognose.

**Konfiguration speichern** lässt die Einstellungen geöffnet. **Änderungen verwerfen** lädt die gespeicherte Konfiguration vom Server neu und ersetzt Ihre Änderungen; bei einem Ladefehler bleibt der Entwurf zum erneuten Versuch erhalten. Beim Verlassen mit Änderungen können Sie weiterbearbeiten oder die Änderungen verwerfen. Erneutes Öffnen lädt die gespeicherte Konfiguration.

Der **Darstellungsmodus** oben rechts bietet Auto, Hell und Dunkel. Auto folgt dem Modus von Home Assistant in dessen Oberfläche und sonst der Systemeinstellung, wenn kein nutzbarer Home-Assistant-Kontext besteht. Hell oder Dunkel überschreibt Auto lokal; Auto stellt das Folgen wieder her. Sprach- und Designwechsel erhalten den Entwurf.

| Einstellung | Eingabe |
| --- | --- |
| Gesamte Maximalleistung unter STC | Summe der maximalen Modulleistungen unter Standardtestbedingungen (STC) in W, z. B. `5000`. |
| Temperaturkoeffizient von Pmax | Pmax-Koeffizient aus dem Moduldatenblatt in %/°C, z. B. `-0,35`. |
| Tatsächliche Leistung | Sensor für die erzeugte Solarleistung (W oder kW). |
| Modultemperatur | Temperatursensor am Modul (°C, °F oder K). |
| Bestrahlungsstärke | Sensor in der gleichen Ebene wie die Module (W/m² oder kW/m²). |
| Abrechnungsintervall | 1, 5 oder 10 Minuten. Standard: 5 Minuten. |
| Mittelwert über | Zeitraum für den aktuellen Mittelwert. Standard: 60 Sekunden. |
| Update alle | Abstand zwischen Updates. Standard: 5 Sekunden. |

Speichern Sie die Werte und öffnen Sie **Live**. Der erste abgeschlossene Eintrag erscheint unter **Verlauf** am Ende des laufenden Zeitraums. Unter **Zeit ohne neue Daten** legen Sie die Wartezeit für jeden Sensor fest.

Live lädt beim Öffnen oder Wiederverbinden feste zehn Minuten vor. Jeder Punkt nutzt weiterhin **Mittelwert über**, die Erfassung folgt **Update alle**. Der Trend wird mit aktuellen Überwachungsparametern aus gespeicherten Beobachtungen rekonstruiert und ist kein Protokoll veröffentlichter Momentaufnahmen. Fehlende oder veraltete Beobachtungen und der aktuelle Offline-Endpunkt bleiben Lücken. Frühere Verbindungsabbrüche ohne erkennbare Beobachtungslücke lassen sich zeitlich nicht genau rekonstruieren. Der Verlauf behält die ursprünglichen abgeschlossenen Ergebnisse. Das Alter der Quellen wird lokal jede Sekunde aktualisiert, ohne zusätzliche Sensorabfragen.

Geglättete Kurven dienen nur der Anzeige. Maus-, Touch- und Tastaturdetails zeigen ursprüngliche Messwerte; Prognosedetails das ursprüngliche Stundenintervall. Energie und PR verwenden Originaldaten. Hauszeit bestimmt Tagessummen, Prognosedaten, Wetter, Heute und Stundenintervalle. Live-/Verlaufszeiten und Aktualisierungen/Abrufe folgen der HA-Benutzereinstellung server/local; eigenständiges Docker nutzt Browserzeit. Ohne lesbare HA-Präferenz gilt Hauszeit. Ein Hinweis erscheint nur bei unterschiedlichen Zeitzonen; UTC-Versätze unterscheiden wiederholte Sommerzeit-Uhrzeiten oder Intervalle mit Versatzwechsel.

## Ertragsprognose

Die Prognose ist bei der ersten Installation standardmäßig deaktiviert. Aktivieren Sie sie unter **Einstellungen > Prognose** und tragen Sie Neigung (0–90°), Kompassrichtung (Nord 0°, Ost 90°, Süd 180°, West 270° oder eigener Azimut von 0° bis unter 360°) und NOCT laut Datenblatt ein (über 20°C, höchstens 80°C; Standard 45°C). Gesamte Maximalleistung unter STC und Temperaturkoeffizient von Pmax werden mit der Überwachung geteilt. Standort und Zeitzone stammen automatisch aus der gespeicherten HA-Verbindung; ändern Sie diese in HA.

Die Überwachung nutzt die gemessene **Modultemperatur**. Die Prognose berechnet aus **Lufttemperatur** und **Nominaler Zellbetriebstemperatur (NOCT)** die **Geschätzte Zelltemperatur**. Diese Größen sind verschieden; die Überwachung rechnet Modultemperatur nicht in Zelltemperatur um.

Open-Meteo liefert stündliches Wetter für heute und die folgenden sechs lokalen Kalendertage. Wählen Sie ein Datum für Tagesenergie, stündliche Leistungskurve und Intervalltabelle. Die heutige Prognose umfasst den ganzen Tag, **Heute verbleibend** nur die Zeit ab jetzt bis zur lokalen Mitternacht. Beide beruhen auf dem letzten erfolgreichen Wetterabruf und sind von der abgeschlossenen, aus Sensorwerten berechneten geschätzten Energie getrennt. Die verbleibende Energie sinkt zwischen Abrufen mit der Zeit; neue Wetterdaten können auch die Tagesprognose ändern.

Jede Datumskarte zeigt Wetter, Höchst-/Tiefsttemperatur der Stundenprognosen, Energiebalken und kWh. Das warme Label **Heute** folgt Mitternacht der Hauszeit und bleibt bei einer anderen, blau markierten Auswahl sichtbar. Tagestemperaturen stammen aus unvermittelten Stundenwerten, das repräsentative Wetter aus dem höchsten bekannten WMO-Code des Tages. Jedes Feld benötigt alle erwarteten UTC-Stundenwerte innerhalb des Haustages, auch bei 23/25 Stunden oder nicht ganzstündigen Zeitzonen. Unvollständige Felder sind nicht verfügbar, vollständige andere Felder bleiben sichtbar. Nullwerte sind gültig; unbekanntes Wetter erhält ein neutrales Symbol. Wetter und Leistung teilen Abruf, Cache und Abrufzeit ohne zusätzliche Aktualisierungen.

Das Wetter wird stündlich oder über **Prognose aktualisieren** abgerufen. Passende Cache-Daten bleiben nach Neustart erhalten. Bei Fehlern bleiben Abrufzeit und ältere Werte sichtbar; ein neuer Versuch folgt nach 15 Minuten. Daten ab zwei Stunden Alter gelten ebenfalls als veraltet. Fehlende Wetterintervalle machen betroffene Summen nicht verfügbar; die Datenvollständigkeit bleibt sichtbar, fehlende Werte zählen nicht als null. Deaktivierung, fehlender HA-Standort, erstes Laden und nicht verfügbare Daten werden angezeigt.

Die Werte sind eine geschätzte Gleichstromreferenz für ein Modulfeld mit Bestrahlungsstärke in Modulebene und vereinfachtem NOCT-Temperaturmodell. Wechselrichterwirkungsgrad/Begrenzung, Schatten, Schnee, Schmutz und Systemverluste sind nicht enthalten; tatsächlicher Wechselstromertrag ist nicht garantiert. Die vier Prognoseentitäten haben kWh und Geräteklasse energy, aber keine `state_class`; sie können sinken und bleiben von kumulierten Zählern getrennt. Eine native HA-Prognose- oder Energie-Dashboard-Integration wird nicht bereitgestellt.

## Ergebnis-Sensoren

| Messgröße | HA-Entitätsname | Einheit |
| --- | --- | --- |
| Abgeschlossene geschätzte Leistung | `settled_estimated_power` | W |
| Abgeschlossene tatsächliche Leistung | `settled_actual_power` | W |
| Abgeschlossener PR | `settled_pr` | % |
| Geschätzte Energie heute | `estimated_energy_today` | kWh |
| Geschätzte Energie seit Beginn | `estimated_energy_lifetime` | kWh |
| Geschätzte Live-Leistung | `live_estimated_power` | W |
| Tatsächliche Live-Leistung | `live_actual_power` | W |
| Live-PR | `live_pr` | % |
| Optimierbare Live-Leistung | `live_optimizable_power` | W |
| Prognostizierte Energie heute | `forecast_energy_today` | kWh |
| Prognostizierte verbleibende Energie heute | `forecast_energy_remaining_today` | kWh |
| Prognostizierte Energie morgen | `forecast_energy_tomorrow` | kWh |
| Prognostizierte Energie für 7 Tage | `forecast_energy_7d` | kWh |

Der HA-Entitätsname ist der Anzeigename. Die vollständige Entitäts-ID besteht aus `sensor.pvyieldlens_` und diesem Namen, zum Beispiel `sensor.pvyieldlens_settled_estimated_power`.

## PR-Formel

Die geschätzte Leistung hängt von gesamter Maximalleistung unter STC, Modultemperatur und Bestrahlungsstärke ab:

```text
P_estimated = P_stc × [1 + (K / 100) × (T − 25)] × G / 1000
PR = P_actual / P_estimated × 100%
```

`P_stc`: Gesamte Maximalleistung unter STC (W); `K`: Temperaturkoeffizient von Pmax (%/°C), als Prozentwert aus dem Datenblatt, z. B. `-0,35`; `T`: Modultemperatur (°C); `G`: Bestrahlungsstärke in Modulebene (W/m²). Die App teilt K genau einmal durch 100.

Die Performance Ratio (PR) vergleicht die tatsächliche mit der geschätzten Leistung. Optimierbare Leistung ist geschätzte minus tatsächliche Leistung und kann negativ sein.

## Ergebnisse verstehen

- PR kann über 100 % liegen. Bei geschätzter Leistung null wird kein PR angezeigt.
- Eine negative optimierbare Leistung heißt: Die tatsächliche Leistung ist höher als geschätzt.
- Energie wird nur gezählt, wenn alle drei Sensoren Daten haben. Fehlende Zeiten werden ausgelassen.
- Die Tagesenergie wird um Mitternacht in der Home-Assistant-Zeitzone auf null gesetzt. Die Gesamtenergie zählt seit der ersten Einrichtung.

Nach einem Ausfall können Daten für manche Zeiträume fehlen. Behalten Sie die App-Daten bei Updates oder einer Neuinstallation. Verwenden Sie für die App die Backups von Home Assistant; bei eigenständigem Docker stoppen Sie den Container, bevor Sie das Verzeichnis `/data` kopieren.
