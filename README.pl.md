[English](README.md) | [中文](README.zh-CN.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | **Polski** | [Italiano](README.it.md)

# PVYieldLens

Porównuj przewidywaną i rzeczywistą moc paneli. Sprawdzaj PR oraz przewidywaną energię dzisiaj i łącznie.

## Funkcje

- Moc, PR i różnica mocy na żywo.
- Historia mocy i PR co 1, 5 lub 10 minut.
- Przewidywana energia dzisiaj i od pierwszego uruchomienia.
- Wykresy z ostatnich 24 godzin, 7 dni lub 30 dni.
- Sześć języków do wyboru w prawym górnym rogu.

## Szybki start

### Aplikacja Home Assistant

Dla Home Assistant OS.

[![Dodaj repozytorium aplikacji PVYieldLens](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fenecess%2Fha-pvyieldlens%23dev_v0)

1. Kliknij przycisk powyżej i potwierdź **Dodaj** w Home Assistant.
2. Znajdź **PVYieldLens** w sklepie z aplikacjami, a następnie zainstaluj i uruchom aplikację.
3. Otwórz stronę Web i w **Ustawieniach** wybierz czujniki oraz podaj dane paneli.

Jeśli przycisk nie otwiera Home Assistant, przejdź do **Ustawienia > Aplikacje > Zainstaluj aplikację > menu w prawym górnym rogu > Repozytoria** i dodaj:

```text
https://github.com/enecess/ha-pvyieldlens#dev_v0
```

W wersjach Home Assistant wcześniejszych niż 2026.2 wybierz **Ustawienia > Dodatki > Sklep z dodatkami > menu w prawym górnym rogu > Repozytoria**. Aplikacja wymaga Home Assistant 2025.9.0 lub nowszego.

### Docker

Pobierz to repozytorium i otwórz jego folder. Utwórz plik ustawień:

```sh
cp .env.example .env
```

W pliku `.env` ustaw swoje hasło w `PVYL_WEB_PASSWORD`, a następnie uruchom aplikację:

```sh
docker compose up -d --build
```

Otwórz [localhost:8099](http://localhost:8099). Zaloguj się jako `admin`, używając ustawionego hasła. W **Ustawieniach** wpisz adres Home Assistant i długoterminowy token dostępu należący do **administratora** Home Assistant, a następnie kliknij **Wczytaj czujniki**. Publikowanie czujników wynikowych wymaga uprawnień administratora.

Domyślnie strona działa na komputerze z Dockerem. Aby otworzyć ją na innym urządzeniu, w `compose.yaml` zmień `127.0.0.1:8099:8099` na `8099:8099`.

## Ustawienia

| Ustawienie | Co wpisać |
| --- | --- |
| Łączna moc znamionowa | Suma mocy paneli w W, np. `5000`. |
| Współczynnik temperatury K | Wartość z karty panelu w %/°C, np. `-0,35`. |
| Moc fotowoltaiki | Czujnik mocy wytwarzanej przez panele (W lub kW). |
| Temperatura modułów | Czujnik temperatury paneli (°C, °F lub K). |
| Światło na panelach | Czujnik w tej samej płaszczyźnie co panele (W/m² lub kW/m²). |
| Odstęp w historii | 1, 5 lub 10 minut. Domyślnie 5 minut. |
| Średnia z | Czas do obliczenia średniej na żywo. Domyślnie 60 sekund. |
| Odświeżaj co | Czas między aktualizacjami. Domyślnie 5 sekund. |

Zapisz ustawienia i otwórz **Przegląd**. Pierwszy wynik w historii pojawi się po zakończeniu bieżącego okresu. W sekcji **Limit czasu bez danych** ustaw czas oczekiwania na każdy czujnik.

## Czujniki wynikowe

| Wynik | ID encji | Jednostka |
| --- | --- | --- |
| Moc przewidywana | `sensor.pvyieldlens_estimated_power` | W |
| Moc rzeczywista | `sensor.pvyieldlens_actual_power` | W |
| PR | `sensor.pvyieldlens_pr` | % |
| Energia przewidywana dzisiaj | `sensor.pvyieldlens_daily_estimated_energy` | kWh |
| Energia przewidywana łącznie | `sensor.pvyieldlens_total_estimated_energy` | kWh |
| Moc przewidywana na żywo | `sensor.pvyieldlens_realtime_estimated_power` | W |
| Moc rzeczywista na żywo | `sensor.pvyieldlens_realtime_actual_power` | W |
| PR na żywo | `sensor.pvyieldlens_realtime_pr` | % |
| Różnica mocy na żywo | `sensor.pvyieldlens_realtime_optimizable_power` | W |

## Wzór PR

Moc przewidywana zależy od mocy paneli, temperatury i światła słonecznego:

```text
P_expected = P_rated × [1 + (K / 100) × (T − 25)] × G / 1000
PR = P_actual / P_expected × 100%
```

`P_rated`: moc znamionowa (W); `K`: współczynnik temperatury (%/°C); `T`: temperatura paneli (°C); `G`: promieniowanie padające na panele (W/m²).

PR porównuje moc rzeczywistą z przewidywaną. Różnica mocy to moc przewidywana minus rzeczywista.

## Jak czytać wyniki

- PR może przekroczyć 100%. Gdy moc przewidywana wynosi zero, PR nie jest wyświetlany.
- Ujemna różnica oznacza, że moc rzeczywista jest większa od przewidywanej.
- Energia jest liczona tylko wtedy, gdy wszystkie trzy czujniki mają dane. Brakujące okresy są pomijane.
- Energia dzienna zeruje się o północy według strefy Home Assistant. Suma jest liczona od pierwszej konfiguracji.

Po przerwie dla niektórych okresów nadal może brakować danych. Zachowaj dane aplikacji podczas aktualizacji lub ponownej instalacji. Dla aplikacji używaj kopii zapasowych Home Assistant; przy samodzielnym Dockerze zatrzymaj kontener przed skopiowaniem katalogu `/data`.
