[English](README.md) | [中文](README.zh-CN.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | **Polski** | [Italiano](README.it.md)

# PVYieldLens

## Przegląd

PVYieldLens porównuje zmierzoną produkcję energii słonecznej z produkcją, jaką instalacja fotowoltaiczna mogłaby osiągnąć w zaobserwowanych warunkach. Śledź współczynnik wydajności (PR) w Home Assistant i sprawdzaj prognozę produkcji na siedem dni.

## Instalacja

### Home Assistant OS

Aplikacja wymaga Home Assistant 2025.9.0 lub nowszego.

[![Dodaj repozytorium aplikacji PVYieldLens](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fenecess%2Fha-pvyieldlens%23dev_v0)

1. Użyj przycisku powyżej i potwierdź wybór przyciskiem **Dodaj** w Home Assistant. Aby dodać repozytorium ręcznie, otwórz **Ustawienia > Aplikacje > Zainstaluj aplikację > ⋮ > Repozytoria** i wpisz `https://github.com/enecess/ha-pvyieldlens#dev_v0`.
2. Znajdź **PVYieldLens** na stronie **Sklep z aplikacjami** i wybierz **Zainstaluj**.
3. Wybierz **Uruchom**, a następnie **Otwórz interfejs użytkownika**.

Przed wersją Home Assistant 2026.2 otwórz **Ustawienia > Dodatki > Sklep z dodatkami**, a następnie dodaj repozytorium z menu ⋮.

### Docker

1. Pobierz repozytorium i otwórz jego folder. Skopiuj `.env.example` do `.env` i ustaw hasło w `PVYL_WEB_PASSWORD`.
2. Uruchom `docker compose up -d --build`.
3. Na hoście Dockera otwórz [localhost:8099](http://localhost:8099). Zaloguj się jako `admin` przy użyciu ustawionego hasła.

Aby uzyskać dostęp z innego urządzenia, zmień mapowanie portów w `compose.yaml` z `127.0.0.1:8099:8099` na `8099:8099`.

## Konfiguracja

Otwórz **Ustawienia** w PVYieldLens. Menu **Język** w prawym górnym rogu pozwala zmienić język interfejsu.

### Połączenie z Home Assistant

Aplikacja Home Assistant łączy się automatycznie. W Dockerze podaj **Adres Home Assistant** oraz **Długoterminowy token dostępu** administratora Home Assistant, a następnie wybierz **Odśwież encje**. Publikowanie czujników wynikowych wymaga uprawnień administratora.

Podaj token przy pierwszej konfiguracji lub przy zmianie adresu. Przy tym samym adresie pozostaw pole puste, aby użyć zapisanego tokena.

### Moduły fotowoltaiczne

| Ustawienie | Wartość do wpisania |
| --- | --- |
| **Łączna moc maksymalna w STC** | Zsumuj moce znamionowe modułów w W. Dziesięć modułów po 500 W daje 5 000 W. |
| **Współczynnik temperaturowy Pmax** | Wartość z karty katalogowej w %/°C, np. −0,35. |
| **Nachylenie modułów** | Od 0° do 90°. |
| **Kierunek modułów** | Azymut liczony zgodnie z ruchem wskazówek zegara od północy (0°), poniżej 360°. Wybierz kierunek świata lub **Własny**. |
| **Nominalna temperatura pracy ogniwa (NOCT)** | Wartość z karty katalogowej, powyżej 20 °C i do 80 °C. Domyślnie 45 °C. |

Osobno dla nachylenia i kierunku wybierz **Wartość stała** lub **Encja HA**. Wybierz encję `sensor.*`, `number.*` lub `input_number.*`, która podaje kąt w stopniach (°). Przy każdym odświeżeniu cała prognoza dla instalacji nadążnej używa kątów odczytanych w tym momencie.

*Instalacja Berlin Demo o mocy 5 000 W ma nachylenie 35° i kierunek **Południe · 180°**.*

<!-- screenshot: settings-pv-modules.png -->

### Czujniki

| Ustawienie | Czujnik i obsługiwane jednostki |
| --- | --- |
| **Moc rzeczywista** | Moc produkcji PV w W lub kW. |
| **Natężenie promieniowania** | Natężenie promieniowania w płaszczyźnie modułów w W/m² lub kW/m². |
| **Temperatura modułu (opcjonalnie)** | Temperatura modułu w °C, °F lub K. Gdy pole jest puste, temperatura jest szacowana z temperatury powietrza z Open-Meteo, zmierzonego natężenia promieniowania i NOCT. |

*Berlin Demo korzysta z symulowanych czujników mocy, natężenia promieniowania i temperatury modułu.*

<!-- screenshot: settings-sensors.png -->

### Prognoza

W sekcji **Prognoza** w **Ustawieniach** sprawdź lokalizację i strefę czasową. Zmień je w Home Assistant. Pole **Liczba dni historii PR** wyznacza okres uwzględniany przy korekcie prognozy. Domyślnie wynosi 14 dni.

### Monitorowanie

Domyślnie PVYieldLens rozlicza energię i PR co 5 minut. Wartości bieżące są uśredniane z ostatnich 60 sekund i odświeżane co 5 sekund. Gdy czujnik przekroczy **Limit czasu bez danych**, odpowiedni okres jest traktowany jako brak danych.

Wybierz **Zapisz konfigurację**.

## Wyniki

### Pulpit

Porównaj bieżącą moc rzeczywistą i szacowaną, **PR** oraz wskaźnik **Moc możliwa do optymalizacji**. Wykres **Dane bieżące** pokazuje moc z ostatnich dziesięciu minut.

*Bieżąca moc i PR w Berlin Demo.*

<!-- screenshot: dashboard.png -->

Sekcja **Dane produkcji** pokazuje moc, natężenie promieniowania i temperaturę modułu w zakończonych okresach rozliczeniowych dzisiejszego dnia.

*Rozliczona produkcja dzisiaj i odczyty czujników w Berlin Demo.*

<!-- screenshot: dashboard-generation.png -->

Sekcja **Historia produkcji** porównuje dzienną energię rzeczywistą i szacowaną. Wybierz **7 dni**, **30 dni** lub **Własny** zakres do 90 dni kalendarzowych. Aby zobaczyć ostatnie siedem pełnych dni jak w Berlin Demo, wybierz zakres **Własny**, ustaw wczoraj jako datę końcową i rozpocznij zakres sześć dni wcześniej.

*Dzienna produkcja energii w Berlin Demo przez siedem pełnych dni.*

<!-- screenshot: dashboard-history.png -->

Bieżący PR to stosunek mocy rzeczywistej do szacowanej wyrażony w procentach. Może przekroczyć 100%. **Moc możliwa do optymalizacji** (moc szacowana minus rzeczywista) może być ujemna. Brak odczytu pozostawia lukę. Zmierzona wartość zero pozostaje zerem. Przy szacowanej mocy równej zero PR ma wartość **—**.

### Sprawność

Wybierz **Dzisiaj**, **24 godziny**, **7 dni** lub **30 dni**. Opcja **Dzisiaj** porównuje wyniki z wczorajszymi do tej samej godziny lokalnej. Zakres **7 dni** obejmuje dzisiaj.

Sprawdź PR w okresie, jego zmianę w punktach procentowych i różnicę między energią szacowaną a rzeczywistą. Zmiany pokazują **Trend PR** i **Porównanie produkcji**. W zakresach kalendarzowych przełączaj między widokiem **Podsumowanie dzienne** a widokiem według interwału rozliczenia. PR w okresie to energia rzeczywista podzielona przez szacowaną z tych samych ważnych okresów rozliczeniowych.

*Sprawność dzisiaj w Berlin Demo w porównaniu z wczorajszą do tej samej godziny.*

<!-- screenshot: efficiency.png -->

### Prognoza

Porównaj wartości z pól **Oryginalna prognoza** i **Skorygowana prognoza** dla dzisiejszego dnia i kolejnych sześciu dni. Oryginalny model korzysta z danych pogodowych Open-Meteo i ustawień instalacji. Korekta uwzględnia PR z ostatnich dni, ważony energią, i wymaga co najmniej trzech pełnych dni, które spełniają warunki korekty i mają dodatnią energię szacowaną. Do tego czasu wartości skorygowane pokazują **—**.

Karty pokazują prognozę na cały dzisiejszy dzień, **Pozostało dzisiaj** oraz **Prognoza na jutro**. Sekcja **Dzienna prognoza energii** porównuje wszystkie siedem dni i pokazuje łączną energię w pozycji **Suma z 7 dni**. Wybierz **Odśwież prognozę**, aby pobrać aktualne dane pogodowe.

*Oryginalna i skorygowana prognoza energii w Berlin Demo, wybór daty i przycisk **Eksportuj CSV**.*

<!-- screenshot: forecast.png -->

Wybierz datę, aby porównać krzywe mocy. Otwórz **Szczegóły co 15 minut**, aby zobaczyć moc, energię, natężenie promieniowania i temperatury w każdym przedziale.

*Krzywe mocy i szczegóły co 15 minut dla wybranej daty w Berlin Demo.*

<!-- screenshot: forecast-details.png -->

W konfiguracji EMHASS z jednym falownikiem PV wybierz **Eksportuj CSV**, a następnie serię oryginalną lub skorygowaną. Dopasuj początek, interwał i liczbę kroków do przebiegu optymalizacji. Zapisz `data_weather_forecast.csv` w katalogu EMHASS wskazanym przez `data_path` i ustaw `set_use_pv=true` oraz `weather_forecast_method=csv`. [Konfiguracja EMHASS](pvyieldlens/DOCS.md#export-a-pv-power-forecast-to-emhass)

### Czujniki wynikowe Home Assistant

| Miara | Nazwa encji HA | Jednostka |
| --- | --- | --- |
| Rozliczona moc szacowana | `settled_estimated_power` | W |
| Rozliczona moc rzeczywista | `settled_actual_power` | W |
| Rozliczony PR | `settled_pr` | % |
| Szacowana energia dzisiaj | `estimated_energy_today` | kWh |
| Łączna szacowana energia | `estimated_energy_lifetime` | kWh |
| Bieżąca moc szacowana | `live_estimated_power` | W |
| Bieżąca moc rzeczywista | `live_actual_power` | W |
| Bieżący PR | `live_pr` | % |
| Bieżąca moc możliwa do optymalizacji | `live_optimizable_power` | W |
| Prognozowana energia dzisiaj | `forecast_energy_today` | kWh |
| Prognozowana energia na resztę dnia | `forecast_energy_remaining_today` | kWh |
| Prognozowana energia jutro | `forecast_energy_tomorrow` | kWh |
| Prognozowana energia przez 7 dni | `forecast_energy_7d` | kWh |

Tabela podaje nazwy widoczne w Home Assistant. W automatyzacjach używaj pełnego identyfikatora, np. `sensor.pvyieldlens_settled_estimated_power`. Cztery czujniki prognozy podają energię z widoku **Oryginalna prognoza**. Dzienna szacowana energia zeruje się o północy w domowej strefie czasowej, a suma narasta od pierwszej konfiguracji.
