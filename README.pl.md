[English](README.md) | [中文](README.zh-CN.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | **Polski** | [Italiano](README.it.md)

# PVYieldLens

Porównuj szacowaną i rzeczywistą moc paneli. Sprawdzaj PR oraz szacowaną energię dzisiaj i łącznie.

## Funkcje

- Pulpit z mocą, PR i dzisiejszą rozliczoną produkcją.
- Porównania sprawności z oryginalnych rozliczeń co 1, 5 lub 10 minut.
- Szacowana energia dzisiaj i od konfiguracji.
- Dzienna energia porównana dla 7/30 dni lub własnego zakresu do 90 dat.
- Oryginalne i skorygowane prognozy produkcji co 15 minut.
- Sześć języków z menu w prawym górnym rogu.

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

**Pulpit** pokazuje bieżącą moc i dzisiejszą produkcję, **Sprawność** porównuje rozliczoną energię i PR, a **Prognoza** zestawia prognozę oryginalną i skorygowaną. **Ustawienia** pozostają w prawym górnym rogu, a trzy widoki danych są dostępne. Kategorie obejmują połączenie HA, moduły PV, czujniki, prognozę i monitorowanie.

Sekcja **Monitorowanie** jest początkowo zwinięta. Wybierz jej nagłówek lub pozycję na liście kategorii, aby wyświetlić ustawienia. Przycisk **?** obok nagłówka wyświetla pomoc dotyczącą rozliczeń, uśredniania, odświeżania i limitów czasu dla czujników również przy zwiniętych ustawieniach.

**Zapisz konfigurację** pozostawia otwarte Ustawienia. **Odrzuć zmiany** ponownie pobiera zapisaną konfigurację z serwera i zastępuje zmiany; jeśli odczyt się nie powiedzie, szkic pozostaje do ponowienia próby. Przy opuszczaniu strony ze zmianami możesz kontynuować edycję lub je odrzucić. Powrót do Ustawień ponownie pobiera zapisaną konfigurację.

Menu **Tryb motywu** u góry po prawej oferuje Auto, Jasny i Ciemny. Auto śledzi tryb Home Assistant w jego interfejsie, a bez dostępnego kontekstu Home Assistant korzysta z ustawienia systemu. Jasny lub Ciemny zapisuje lokalne nadpisanie; Auto przywraca śledzenie. Zmiana języka lub motywu zachowuje szkic.

| Ustawienie | Co wpisać |
| --- | --- |
| Łączna moc maksymalna w STC | Suma mocy maksymalnych modułów w standardowych warunkach testowych (STC) w W, np. `5000`. |
| Współczynnik temperaturowy Pmax | Wartość z karty panelu w %/°C, np. `-0,35`. |
| Moc rzeczywista | Czujnik mocy wytwarzanej przez panele (W lub kW). |
| Temperatura modułów | Czujnik temperatury paneli (°C, °F lub K). |
| Natężenie promieniowania | Czujnik w tej samej płaszczyźnie co panele (W/m² lub kW/m²). |
| Interwał rozliczenia | Zapisuje energię i PR co 1, 5 lub 10 minut dla widoku **Sprawność**. Domyślnie co 5 minut. |
| Średnia z | Domyślnie oblicza wartości bieżące z ostatnich 60 sekund. Dłuższe okno wygładza krótkotrwałe wahania. |
| Odświeżaj co | Domyślnie przelicza i odświeża wartości bieżące co 5 sekund. |
| Limit czasu bez danych | Ustala czas oczekiwania na kolejny odczyt każdego czujnika. Okresy po przekroczeniu limitu są liczone jako brak danych i obniżają kompletność danych. |

Zapisz ustawienia i otwórz **Pulpit**. Pierwszy rozliczony wynik pojawi się w widoku **Sprawność** po zakończeniu bieżącego okresu.

Pulpit wczytuje ostatnie dziesięć minut przy otwarciu lub ponownym połączeniu. Dane produkcji pokazują dzisiejszą rozliczoną moc szacowaną/rzeczywistą, natężenie promieniowania i temperaturę modułów. Wykres energii domyślnie obejmuje 7 dni, także 30 dni lub własny zakres do 90 domowych dat kalendarzowych włącznie z obiema granicami, najwyżej do dzisiaj. Braki pozostają puste, zmierzone zero pozostaje zerem; zapisane rozliczenia i energia skumulowana nie zmieniają się.

Sprawność pokazuje PR okresu, zmianę wobec porównywalnego poprzedniego okresu w punktach procentowych oraz energię szacowaną minus rzeczywistą. Dzisiaj porównuje się z wczoraj do tej samej godziny lokalnej, 24 godziny z poprzednimi 24 godzinami, a 7/30 dni z takim samym zakresem przesuniętym o 7/30 domowych dat. Oba wykresy współdzielą podsumowanie dzienne lub skonfigurowany interwał rozliczenia.

Wygładzanie dotyczy tylko rysunku. Mysz, dotyk i klawiatura pokazują oryginalne rekordy, w tym interwały prognozy co 15 minut. Energia i PR używają niewygładzonych wartości. Daty i prognozy stosują czas domu; znaczniki monitorowania i pobierania stosują preferencję HA server/local użytkownika lub czas przeglądarki w samodzielnym Dockerze. Przesunięcia UTC rozróżniają w razie potrzeby powtarzające się godziny.

## Prognoza produkcji

Prognoza jest domyślnie wyłączona po instalacji. Włącz ją w **Ustawienia > Prognoza**. Lokalizacja i strefa czasowa pochodzą z zapisanego połączenia Home Assistant i są ustawiane w HA.

W **Ustawienia > Moduły fotowoltaiczne** wybierz osobno dla nachylenia i kierunku **Wartość stała** lub **Encja HA**. Nachylenie wynosi od 0° do 90° włącznie. Azymut kompasowy jest liczony zgodnie z ruchem wskazówek zegara od północy (0°) do wartości poniżej 360°. Stałe kierunki obejmują także wschód (90°), południe (180°) i zachód (270°). Encje kątów to `sensor.*`, `number.*` lub `input_number.*` z jednostką `°`. Wybierz **Odśwież encje** w ustawieniach połączenia, aby je znaleźć.

W sekcji **Moduły fotowoltaiczne** wprowadź NOCT z karty modułu (powyżej 20°C, maksymalnie 80°C, domyślnie 45°C). Łączna moc maksymalna w STC i współczynnik temperaturowy Pmax służą też do monitorowania. Dla identycznych modułów pomnóż moc znamionową jednego modułu przez liczbę modułów, na przykład 500 W × 10 = 5000 W.

Podczas każdego odświeżania wybrane kąty z HA są odczytywane raz. Ta sama para kątów służy do oszacowania wszystkich 15-minutowych okresów siedmiodniowej prognozy, w tym wcześniejszych okresów dzisiejszego dnia. Strona prognozy wyświetla użyte kąty i czas odczytu oddzielnie od czasu pobrania pogody. Jeśli encja jest niedostępna, strona wskazuje ją i pokazuje nadal dostępne okresy ostatniej prognozy. Gdy prognoza jest niedostępna, wartości energii mają oznaczenie **—** i można ponowić odświeżanie.

Monitorowanie wykorzystuje zmierzoną wartość **Temperatura modułów**. Prognoza oblicza **Szacowaną temperaturę ogniw** na podstawie **Temperatury powietrza** i **Nominalnej temperatury pracy ogniwa (NOCT)**. To różne wielkości fizyczne; monitorowanie nie przelicza temperatury modułów na temperaturę ogniw.

Open-Meteo dostarcza dane modelu co 15 minut na dzisiaj i sześć kolejnych domowych dni kalendarzowych. Niektóre regiony lub pola interpolują modele godzinowe; krok wyjściowy nie gwarantuje większej dokładności. Wybierz datę dla energii oryginalnej/skorygowanej, krzywych mocy i szczegółów. Dzisiejsza prognoza obejmuje cały dzień; **Pozostało dzisiaj** czas od teraz do domowej północy i maleje między pobraniami. Zwykły dzień ma 96 interwałów, a dzień zmiany czasu 92 lub 100.

Karty dat zachowują pogodę oraz godzinowe maksymalne/minimalne temperatury obok par słupków energii i kWh. Ciepły znacznik **Dzisiaj** zmienia się o domowej północy niezależnie od niebieskiego zaznaczenia. Podsumowania pogody nadal używają próbek godzinowych z tego samego zapytania, pamięci podręcznej i czasu pobrania. Pogoda i energia mogą być niedostępne niezależnie; zero jest poprawne.

Pogoda odświeża się zwykle co godzinę lub przyciskiem **Odśwież prognozę**. Pasująca pamięć podręczna przetrwa restart. Błąd zachowuje czas pobrania, jest widoczny i powoduje ponowienie po 15 minutach. Brak danych wejściowych oznacza niedostępne sumy (**—**). Widoczne pozostają wyłączenie, brak lokalizacji, ładowanie i brak danych.

**Oryginalna prognoza** zachowuje model pogody/NOCT. **Skorygowana prognoza** mnoży go przez ostatni PR ważony energią, z większą wagą nowszych zakończonych dat domowych. W **Ustawienia > Prognoza** domyślnie n=14 dni historii PR, liczba całkowita 3–90; okres półtrwania to n/2 dni. Potrzeba co najmniej 3 kwalifikujących się dat z dodatnią energią szacowaną. Energia rzeczywista i szacowana obejmują te same poprawne okresy od ostatniej porównywalnej konfiguracji monitorowania. Zerowa produkcja rzeczywista jest poprawna, PR ponad 100% nie jest ograniczany. Bez dostatecznej historii korekta pokazuje **—**, a wartości oryginalne pozostają dostępne. Zmiana n przelicza korektę bez ponownego pobrania pogody.

Korekta dotyczy tylko strony i API aplikacji. Identyfikatory i znaczenie wszystkich 13 wyjść HA pozostają bez zmian; cztery encje prognozy nadal podają oryginalną energię całkowaną z interwałów 15 minut.

To szacowana wartość odniesienia DC dla jednego pola paneli, z natężeniem promieniowania w płaszczyźnie modułów i uproszczonym modelem temperatury NOCT. Nie uwzględnia sprawności/ograniczeń falownika, cienia, śniegu, zabrudzeń ani strat systemowych i nie gwarantuje rzeczywistego uzysku AC. Cztery encje prognozy mają kWh i klasę urządzenia energy, bez `state_class`; mogą maleć i są oddzielone od liczników skumulowanych. Nie zapewniają natywnej integracji prognoz HA ani panelu Energia.

## Czujniki wynikowe

| Wskaźnik | Nazwa encji HA | Jednostka |
| --- | --- | --- |
| Rozliczona moc szacowana | `settled_estimated_power` | W |
| Rozliczona moc rzeczywista | `settled_actual_power` | W |
| Rozliczony PR | `settled_pr` | % |
| Energia szacowana dzisiaj | `estimated_energy_today` | kWh |
| Łączna energia szacowana | `estimated_energy_lifetime` | kWh |
| Moc szacowana na żywo | `live_estimated_power` | W |
| Moc rzeczywista na żywo | `live_actual_power` | W |
| PR na żywo | `live_pr` | % |
| Moc możliwa do optymalizacji na żywo | `live_optimizable_power` | W |
| Prognozowana energia dzisiaj | `forecast_energy_today` | kWh |
| Prognozowana pozostała energia dzisiaj | `forecast_energy_remaining_today` | kWh |
| Prognozowana energia jutro | `forecast_energy_tomorrow` | kWh |
| Prognozowana energia na 7 dni | `forecast_energy_7d` | kWh |

Nazwa encji HA jest jej nazwą wyświetlaną. Pełny identyfikator encji to `sensor.pvyieldlens_` i ta nazwa, na przykład `sensor.pvyieldlens_settled_estimated_power`.

## Wzór PR

Moc szacowana zależy od łącznej mocy maksymalnej w STC, temperatury modułów i natężenia promieniowania:

```text
P_estimated = P_stc × [1 + (K / 100) × (T − 25)] × G / 1000
PR = P_actual / P_estimated × 100%
```

`P_stc`: łączna moc maksymalna w STC (W); `K`: współczynnik temperaturowy Pmax (%/°C), procent z karty modułu, np. `-0,35`; `T`: temperatura modułów (°C); `G`: natężenie promieniowania w płaszczyźnie modułów (W/m²). Aplikacja dzieli K przez 100 tylko raz.

Współczynnik wydajności (PR) porównuje moc rzeczywistą z szacowaną. Moc możliwa do optymalizacji to moc szacowana minus rzeczywista i może być ujemna.

## Jak czytać wyniki

- PR może przekroczyć 100%. Gdy moc szacowana wynosi zero, PR nie jest wyświetlany.
- Ujemna moc możliwa do optymalizacji oznacza, że moc rzeczywista jest większa od szacowanej.
- Energia jest liczona tylko wtedy, gdy wszystkie trzy czujniki mają dane. Brakujące okresy są pomijane.
- Energia dzienna zeruje się o północy według strefy Home Assistant. Suma jest liczona od pierwszej konfiguracji.

Po przerwie dla niektórych okresów nadal może brakować danych. Zachowaj dane aplikacji podczas aktualizacji lub ponownej instalacji. Dla aplikacji używaj kopii zapasowych Home Assistant; przy samodzielnym Dockerze zatrzymaj kontener przed skopiowaniem katalogu `/data`.
