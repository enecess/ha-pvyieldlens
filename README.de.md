[English](README.md) | [中文](README.zh-CN.md) | [Français](README.fr.md) | **Deutsch** | [Polski](README.pl.md) | [Italiano](README.it.md)

# PVYieldLens

Vergleichen Sie die geschätzte und die tatsächliche Leistung Ihrer Solarmodule. Sehen Sie PR und geschätzte Energie für heute und insgesamt.

## Funktionen

- Übersicht mit Leistung, PR und heutiger abgeschlossener Erzeugung.
- Effizienzvergleiche mit ursprünglichen 1-, 5- oder 10-Minuten-Abrechnungen.
- Geschätzte Energie für heute und seit der Einrichtung.
- Täglicher Energievergleich für 7/30 Tage oder bis zu 90 eigene Kalenderdaten.
- Ursprüngliche und korrigierte 15-Minuten-Ertragsprognosen.
- Sechs Sprachen mit Auswahl oben rechts.

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

Die **Übersicht** zeigt aktuelle Leistung und heutige Erzeugung, **Effizienz** vergleicht abgeschlossene Energie und PR, **Prognose** zeigt ursprüngliche und korrigierte Wetterprognosen. **Einstellungen** bleibt oben rechts; alle drei Datenansichten sind erreichbar. Die Kategorien umfassen HA-Verbindung, PV-Module, Sensoren, Prognose und Überwachung.

**Überwachung** ist beim Öffnen der Einstellungen eingeklappt. Die Überschrift oder der Eintrag in der Kategorienliste öffnet die Einstellungen. Das **?** neben der Überschrift zeigt die Hilfe zur Abrechnung, Mittelung, Aktualisierung und Sensorfrist auch bei eingeklappten Einstellungen.

**Konfiguration speichern** lässt die Einstellungen geöffnet. **Änderungen verwerfen** lädt die gespeicherte Konfiguration vom Server neu und ersetzt Ihre Änderungen; bei einem Ladefehler bleibt der Entwurf zum erneuten Versuch erhalten. Beim Verlassen mit Änderungen können Sie weiterbearbeiten oder die Änderungen verwerfen. Erneutes Öffnen lädt die gespeicherte Konfiguration.

Der **Darstellungsmodus** oben rechts bietet Auto, Hell und Dunkel. Auto folgt dem Modus von Home Assistant in dessen Oberfläche und sonst der Systemeinstellung, wenn kein nutzbarer Home-Assistant-Kontext besteht. Hell oder Dunkel überschreibt Auto lokal; Auto stellt das Folgen wieder her. Sprach- und Designwechsel erhalten den Entwurf.

| Einstellung | Eingabe |
| --- | --- |
| Gesamte Maximalleistung unter STC | Summe der maximalen Modulleistungen unter Standardtestbedingungen (STC) in W, z. B. `5000`. |
| Temperaturkoeffizient von Pmax | Pmax-Koeffizient aus dem Moduldatenblatt in %/°C, z. B. `-0,35`. |
| Tatsächliche Leistung | Sensor für die erzeugte Solarleistung (W oder kW). |
| Modultemperatur | Temperatursensor am Modul (°C, °F oder K). |
| Bestrahlungsstärke | Sensor in der gleichen Ebene wie die Module (W/m² oder kW/m²). |
| Abrechnungsintervall | Speichert Energie und PR alle 1, 5 oder 10 Minuten für die Ansicht **Effizienz**. Standard sind 5 Minuten. |
| Mittelwert über | Berechnet Livewerte standardmäßig aus den letzten 60 Sekunden. Längere Zeitfenster glätten kurzfristige Schwankungen. |
| Update alle | Berechnet und aktualisiert Livewerte standardmäßig alle 5 Sekunden. |
| Zeit ohne neue Daten | Legt die Frist für den nächsten Messwert je Sensor fest. Nach Ablauf gelten die betroffenen Zeiträume als fehlend und verringern die Datenvollständigkeit. |

Speichern Sie die Werte und öffnen Sie **Übersicht**. Der erste abgeschlossene Eintrag erscheint unter **Effizienz** am Ende des laufenden Zeitraums.

Die Übersicht lädt beim Öffnen oder Wiederverbinden die letzten zehn Minuten. Die Erzeugungsdaten zeigen heute abgeschlossene geschätzte/tatsächliche Leistung, Bestrahlungsstärke und Modultemperatur. Das Energiediagramm bietet standardmäßig 7 Tage, außerdem 30 Tage oder einen eigenen Zeitraum mit einschließlich beider Grenzen höchstens 90 Hauskalendertagen bis maximal heute. Fehlende Werte bleiben leer, gemessene Null bleibt Null; gespeicherte Abrechnungen und kumulierte Energie bleiben erhalten.

Effizienz zeigt Zeitraum-PR, die Änderung gegenüber dem vergleichbaren Vorzeitraum in Prozentpunkten sowie geschätzte minus tatsächliche Energie. Heute wird mit gestern bis zur gleichen Ortszeit verglichen, 24 Stunden mit den vorangehenden 24 Stunden, 7/30 Tage mit dem um 7/30 Hauskalendertage verschobenen Bereich. Beide Diagramme teilen die Umschaltung zwischen Tageszusammenfassung und dem eingestellten Abrechnungsintervall.

Die Glättung betrifft nur die Zeichnung. Maus, Touch und Tastatur zeigen Originaldatensätze, auch die 15-Minuten-Prognoseintervalle. Energie und PR nutzen ungeglättete Werte. Hauszeit definiert Kalenderdaten und Prognosen; Überwachungs- und Abrufzeiten folgen der HA-Benutzerpräferenz server/local oder bei eigenständigem Docker der Browserzeit. UTC-Versätze unterscheiden bei Bedarf wiederholte Uhrzeiten.

## Ertragsprognose

Standort und Zeitzone stammen aus der gespeicherten Home-Assistant-Verbindung und werden in HA eingestellt.

Wählen Sie unter **Einstellungen > PV-Module** für Neigung und Ausrichtung jeweils **Fester Wert** oder **HA-Entität**. Die Neigung reicht von 0° bis einschließlich 90°. Der Kompassazimut zählt im Uhrzeigersinn ab Nord (0°) bis unter 360°. Als feste Richtungen stehen auch Ost (90°), Süd (180°) und West (270°) zur Auswahl. Winkelentitäten sind `sensor.*`, `number.*` oder `input_number.*` mit der Einheit `°`. Über **Entitäten aktualisieren** in den Verbindungseinstellungen finden Sie passende Entitäten.

Tragen Sie unter **PV-Module** die NOCT laut Datenblatt ein (über 20°C bis einschließlich 80°C, Standard 45°C). Die maximale Gesamtleistung unter STC und der Temperaturkoeffizient von Pmax gelten auch für die Überwachung. Bei identischen Modulen ergibt sich die Gesamtleistung aus Nennleistung pro Modul mal Modulanzahl, zum Beispiel 500 W × 10 = 5000 W.

Bei jeder Aktualisierung werden die ausgewählten HA-Winkel einmal gelesen. Diese Winkel gelten für alle 15-Minuten-Abschnitte der Sieben-Tage-Prognose, einschließlich der früheren Abschnitte des heutigen Tages. Die Prognoseseite zeigt die verwendeten Winkel und ihre Lesezeit getrennt vom Wetterabruf an. Ist eine Entität vorübergehend nicht verfügbar, nennt die Seite die Entität und zeigt weiter verwendbare Abschnitte der letzten Prognose. Ohne verwendbare Prognose steht bei den Energiewerten **—** und die Aktualisierung kann wiederholt werden.

Die Überwachung nutzt die gemessene **Modultemperatur**. Die Prognose berechnet aus **Lufttemperatur** und **Nominaler Zellbetriebstemperatur (NOCT)** die **Geschätzte Zelltemperatur**. Diese Größen sind verschieden; die Überwachung rechnet Modultemperatur nicht in Zelltemperatur um.

Open-Meteo liefert 15-Minuten-Modelleingaben für heute und die nächsten sechs Hauskalendertage. Manche Regionen oder Felder interpolieren Stundenmodelle; der Ausgabeschritt garantiert keine höhere Genauigkeit. Ein Datum öffnet ursprüngliche/korrigierte Energie, Leistungskurven und Intervalldetails. Heute umfasst den ganzen Tag; **Heute verbleibend** reicht von jetzt bis zur Hausmitternacht und sinkt zwischen Wetterabrufen. Normale Tage haben 96 Intervalle, Sommerzeitwechseltage 92 oder 100.

Datumskarten behalten Wetter und stündlich prognostizierte Höchst-/Tiefsttemperaturen neben zwei Energiebalken und kWh-Werten. Die warme Markierung **Heute** folgt der Hausmitternacht unabhängig von der blauen Auswahl. Wetterzusammenfassungen verwenden weiterhin Stundensamples derselben Anfrage, desselben Caches und Abrufzeitpunkts. Wetter und Energie können unabhängig fehlen; Null bleibt gültig.

Wetter wird normalerweise stündlich oder über **Prognose aktualisieren** abgerufen. Passende Caches überstehen Neustarts. Ein Fehler erhält die Abrufzeit, wird angezeigt und nach 15 Minuten erneut versucht. Fehlende Eingaben machen betroffene Summen unverfügbar (**—**). Fehlender Standort, Laden und fehlende Daten bleiben sichtbar.

Die **Ursprüngliche Prognose** behält das Wetter-/NOCT-Modell. Die **Korrigierte Prognose** multipliziert es mit dem aktuellen energiegewichteten PR, wobei jüngere abgeschlossene Hauskalendertage stärker zählen. Unter **Einstellungen > Prognose** gilt standardmäßig n=14 historische PR-Tage, ganzzahlig 3–90; die Halbwertszeit ist n/2 Tage. Mindestens 3 geeignete Tage mit positiver geschätzter Energie sind erforderlich. Tatsächliche und geschätzte Energie nutzen dieselben gültigen Zeiträume seit der letzten vergleichbaren Überwachungskonfiguration. Tatsächliche Nullerträge zählen, PR über 100 % wird nicht begrenzt. Ohne genug Historie erscheint die Korrektur als **—**, die Originalprognose bleibt verfügbar. Eine Änderung von n berechnet die Korrektur ohne neuen Wetterabruf.

Die Korrektur gilt nur für Seite und Anwendungs-API. Alle 13 HA-Ausgabe-IDs und Bedeutungen bleiben unverändert; die vier Prognoseentitäten melden weiterhin die aus 15-Minuten-Intervallen integrierte ursprüngliche Energie.

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
