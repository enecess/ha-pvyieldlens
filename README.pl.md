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

Otwórz [localhost:8099](http://localhost:8099). Zaloguj się jako `admin`, używając ustawionego hasła. Przy pierwszym połączeniu wpisz w **Ustawieniach** adres Home Assistant i długoterminowy token dostępu należący do **administratora** Home Assistant, a następnie kliknij **Odśwież czujniki**. Jeśli adres i token są już skonfigurowane, czujniki zostaną wczytane automatycznie przy pierwszym otwarciu **Ustawień**. Użyj przycisku **Odśwież czujniki** po zmianie połączenia, aby odświeżyć listę lub ponowić nieudaną próbę. Publikowanie czujników wynikowych wymaga uprawnień administratora.

Domyślnie strona działa na komputerze z Dockerem. Aby otworzyć ją na innym urządzeniu, w `compose.yaml` zmień `127.0.0.1:8099:8099` na `8099:8099`.

## Ustawienia

**Na żywo** pokazuje bieżące średnie i diagnostykę, **Historia** zakończone okresy oraz energię/PR wybranego zakresu, a **Prognoza** szacunki na podstawie pogody. Sumy dzienne i całkowite nie zależą od zakresu. Osobny przycisk **Ustawienia** z kołem zębatym i tekstem znajduje się u góry po prawej; trzy karty danych pozostają dostępne. Spis kategorii przewija jeden ciągły formularz: Połączenie z Home Assistant, Panele słoneczne, Czujniki, Monitorowanie i Prognoza.

**Zapisz** pozostawia otwarte Ustawienia. **Anuluj** ponownie pobiera zapisaną konfigurację z serwera i zastępuje zmiany; jeśli odczyt się nie powiedzie, szkic pozostaje do ponowienia próby. Przy opuszczaniu strony ze zmianami możesz kontynuować edycję lub je odrzucić. Powrót do Ustawień ponownie pobiera zapisaną konfigurację.

Menu **Tryb motywu** u góry po prawej oferuje Auto, Jasny i Ciemny. Auto śledzi tryb Home Assistant w jego interfejsie, a bez dostępnego kontekstu Home Assistant korzysta z ustawienia systemu. Jasny lub Ciemny zapisuje lokalne nadpisanie; Auto przywraca śledzenie. Zmiana języka lub motywu zachowuje szkic.

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

Zapisz ustawienia i otwórz **Na żywo**. Pierwszy rozliczony wynik pojawi się w widoku **Historia** po zakończeniu bieżącego okresu. W sekcji **Limit czasu bez danych** ustaw czas oczekiwania na każdy czujnik.

Widok na żywo wczytuje stałe ostatnie dziesięć minut przy otwarciu lub ponownym połączeniu. Każdy punkt nadal używa ustawienia **Średnia z**, a zbieranie danych — **Odświeżaj co**. Trend jest odtwarzany z zapisanych obserwacji według bieżących parametrów; nie jest dziennikiem opublikowanych migawek. Brakujące lub przeterminowane obserwacje i bieżący punkt offline pozostają lukami. Dawnych rozłączeń bez rozpoznawalnej luki obserwacji nie da się dokładnie odtworzyć. Historia zachowuje oryginalne rozliczenia. Wiek źródeł rośnie lokalnie co sekundę, bez dodatkowych zapytań do czujników.

Wygładzone krzywe służą tylko wyświetlaniu. Wskazówki myszy, dotyku i klawiatury pokazują oryginalne wartości; prognoza pokazuje oryginalny przedział godzinowy. Energia i PR używają oryginalnych danych. Czas domu określa sumy dzienne, daty prognozy, pogodę, Dzisiaj i przedziały godzinowe. Znaczniki czasu na żywo/historii oraz czasy aktualizacji/pobrania śledzą preferencję HA server/local użytkownika; samodzielny Docker używa czasu przeglądarki. Nieczytelna preferencja HA oznacza czas domu. Krótka uwaga wskazuje różne strefy; przesunięcia UTC rozróżniają tylko powtórzone godziny lub przedziały ze zmianą przesunięcia.

## Prognoza produkcji

Prognoza jest domyślnie wyłączona, również po aktualizacji. Włącz ją w **Ustawienia > Prognoza** i podaj nachylenie (0–90°), kierunek kompasowy (północ 0°, wschód 90°, południe 180°, zachód 270° lub własny azymut od 0° do mniej niż 360°) oraz NOCT z karty panelu (powyżej 20°C, do 80°C; domyślnie 45°C). Moc znamionowa i K są wspólne z monitorowaniem. Lokalizacja i strefa czasowa pochodzą automatycznie z zapisanego połączenia HA; zmieniaj je w HA.

Open-Meteo dostarcza pogodę co godzinę na dziś i sześć następnych lokalnych dni kalendarzowych. Wybierz datę, aby zobaczyć energię całego dnia, wykres godzinowy i tabelę przedziałów. Dzisiejsza prognoza obejmuje cały dzień, a **Pozostało dzisiaj** tylko czas od teraz do lokalnej północy. Obie korzystają z ostatniej poprawnie pobranej pogody i są odrębne od rozliczonej energii teoretycznej wyliczonej z danych czujników. Pozostała energia maleje z upływem czasu między pobraniami; nowe dane mogą też zmienić prognozę całego dnia.

Każda karta daty pokazuje pogodę, maksimum/minimum prognoz godzinowych, słupek energii i kWh. Ciepła etykieta **Dzisiaj** zmienia się o północy domu i pozostaje widoczna, gdy inna data jest zaznaczona na niebiesko. Temperatury to ekstrema surowych próbek godzinowych; pogoda reprezentatywna używa najwyższego znanego kodu WMO dnia. Każde pole wymaga wszystkich oczekiwanych próbek godzinowych UTC w dniu domu, również dla dni 23/25-godzinnych i stref ułamkowych. Niekompletne pole jest niedostępne, a drugie kompletne pozostaje widoczne. Zero jest poprawne; nieznana pogoda ma neutralną ikonę. Pogoda i moc współdzielą zapytanie, pamięć podręczną i czas pobrania, bez dodatkowego odświeżania. Stara pamięć zachowuje poprawną energię i otrzymuje pogodę przy następnym zwykłym odświeżeniu.

Pogoda odświeża się co godzinę lub przyciskiem **Odśwież prognozę**. Pasująca pamięć podręczna przetrwa restart. Nieudane pobranie zachowuje pierwotny czas i oznacza dane jako nieaktualne; ponowienie następuje po 15 minutach. Dane mające co najmniej dwie godziny także są nieaktualne. Brakujące przedziały czynią odpowiednie sumy niedostępnymi; kompletność jest pokazywana osobno, a braków nie zastępuje zero. Widoczne są stany wyłączenia, braku lokalizacji HA, pierwszego ładowania i niedostępności.

To teoretyczna wartość odniesienia DC dla jednego pola paneli, z promieniowaniem w ich płaszczyźnie i uproszczonym modelem temperatury NOCT. Nie uwzględnia sprawności/ograniczeń falownika, cienia, śniegu, zabrudzeń ani strat systemowych i nie gwarantuje rzeczywistego uzysku AC. Cztery encje prognozy mają kWh i klasę urządzenia energy, bez `state_class`; mogą maleć i są oddzielone od liczników skumulowanych. Nie zapewniają natywnej integracji prognoz HA ani panelu Energia.

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
| Prognoza na dzisiaj | `sensor.pvyieldlens_forecast_energy_today` | kWh |
| Prognoza pozostała dzisiaj | `sensor.pvyieldlens_forecast_energy_remaining_today` | kWh |
| Prognoza na jutro | `sensor.pvyieldlens_forecast_energy_tomorrow` | kWh |
| Prognoza na 7 dni | `sensor.pvyieldlens_forecast_energy_7d` | kWh |

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
