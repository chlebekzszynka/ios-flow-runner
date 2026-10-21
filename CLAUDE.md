# iOS Flow Runner

Framework sterujący aplikacjami iOS przez Appium. Ścieżka nawigacji i lokatory
siedzą w pliku JSON w `configs/`; kod w `ios_flow/` nie wie nic o żadnej
konkretnej aplikacji. Przykład działa na symulatorze z Ustawieniami
(`com.apple.Preferences`).

## Komendy

```bash
source .venv/bin/activate                 # środowisko (python -m venv .venv przy pierwszym razie)
pip install -r requirements.txt
pytest -v                                 # testy — bez urządzenia, symulatora i Appium
ruff check . && ruff format --check .     # lint i formatowanie

python -m ios_flow.run configs/przyklad-symulator.json --sprawdz   # walidacja + capabilities, bez Appium
python -m ios_flow.run configs/przyklad-symulator.json             # przebieg (appium musi działać)
python -m ios_flow.run configs/przyklad-symulator.json --lista     # lista pozycji z przewijaniem
python -m ios_flow.inspect configs/przyklad-symulator.json         # elementy bieżącego ekranu
python -m ios_flow.inspect --z-pliku tests/fixtures/ogolne.xml     # to samo z zapisanego drzewa
```

Przebieg na żywo wymaga: `appium` w osobnym terminalu, uruchomionego
symulatora (`open -a Simulator`) zgodnego z `symulator` w konfiguracji.

Kontrola przed wydaniem: `/chlebek`. Przegląd zmian: podagent `recenzent`.
Nowy ekran do zmapowania: skill `namierzanie-lokatorow`.

## Zasady projektu

1. **Lokatory tylko w konfiguracji.** Żaden identyfikator, etykieta ani
   predykat konkretnej aplikacji nie trafia do `ios_flow/`. Kod dostaje je
   z JSON-a. Wyjątek: testy i fikstury.
2. **Dopasowanie zawsze dokładne.** `==` i `BEGINSWITH '<tekst>, '` (pełny
   człon przed separatorem), nigdy `CONTAINS` ani `LIKE`. Predykaty buduje
   `ios_flow/locators.py`; każda wartość wstawiana do apostrofów idzie przez
   `escape_literal`.
3. **Każda nowa logika parsowania ma test na fiksturze** w `tests/fixtures/`
   (ręcznie pisany XML w formacie `page_source`, opisany w
   `tests/fixtures/README.md`). Test, który potrzebuje urządzenia, jest źle
   napisany — używaj atrapy `FakeDevice` z `tests/conftest.py`.
4. **Komunikat błędu mówi, co zrobić**: co się stało, przy jakim lokatorze
   albo polu, jaka komenda pomoże. Walidacja konfiguracji zbiera wszystkie
   problemy naraz i podaje, skąd wziąć brakującą wartość (`HINTS` w `config.py`).
5. Kod: adnotacje typów wszędzie, nazwy po angielsku, komentarze i komunikaty
   po polsku. Klucze konfiguracji po polsku, bez znaków diakrytycznych.
6. Humor tylko w README, CHANGELOG i `--version`. Logi i błędy są rzeczowe.
7. **Zero danych z poprzednich projektów.** Przed commitem:
   `git grep --untracked -niEf .audyt-wzorce` musi nic nie zwrócić. Plik
   `.audyt-wzorce` jest lokalny i ignorowany przez git — nigdy go nie dodawaj
   ani nie przepisuj jego treści do repozytorium.

## Układ

```
ios_flow/config.py     ładowanie i walidacja JSON → dataclassy Config, Step, FieldSpec
ios_flow/locators.py   lokator z konfiguracji → (strategia Appium, selektor); escape
ios_flow/navigate.py   wykonywanie kroków, kroki opcjonalne, podział wokół {zmienna}
ios_flow/extract.py    parsowanie page_source: wartości, stan, listy, scalanie przewinięć
ios_flow/driver.py     capabilities obu trybów (czysta funkcja) + sesja Appium
ios_flow/inspect.py    podgląd elementów ekranu, propozycje lokatorów
ios_flow/run.py        CLI przebiegu; zapis JSON + zrzut ekranu do artifacts/
configs/               przyklad-symulator.json (działa), szablon-urzadzenie.json
tests/fixtures/        zapisane drzewa XML Ustawień + syntetyczna lista wariantów
```

`navigate.py` i `extract.py` nie importują Appium. Appium/Selenium są
importowane leniwie w `driver.py` i `run.py` — dzięki temu testy jednostkowe
nie dotykają sieci.

## Pułapki techniczne

- **`waitForQuiescence: false`** — XCUITest przed każdą akcją czeka, aż
  aplikacja przestanie animować. Aplikacje z animacjami, mapą albo
  odtwarzaczem nigdy tego stanu nie osiągają i sesja wisi na starcie albo
  przy pierwszym kliknięciu. Wyłączamy czekanie i w zamian używamy jawnego
  `czekaj_s` (WebDriverWait na konkretny element) oraz `pauza_s` po kliknięciu.
- **Drzewo elementów (`page_source`) pobieramy dopiero po znalezieniu
  elementu docelowego.** Część elementów ładuje się wolniej niż reszta ekranu;
  zrzut zrobiony zaraz po przejściu na ekran by ich nie zawierał. Dlatego
  `run_flow` najpierw czeka na pola z `odczyt`, a potem robi zrzut do
  `teksty_na_ekranie`.
- **Dokładne dopasowanie zamiast `CONTAINS`** — `label CONTAINS '20%'` trafia
  też w `20%HM` i `20%VM`, a Appium bierze pierwszy pasujący element, więc
  przebieg klika nie to, co trzeba, i nie zgłasza błędu. Testy w
  `test_locators.py::TestExactMatch` pilnują tego na fiksturze.
- **Komórka i przycisk z tym samym `name`.** W Ustawieniach `Cell` i `Button`
  w wierszu mają ten sam identyfikator, ale etykieta komórki potrafi rozbić
  wartość (`Capacity, 494, 38 GB` zamiast `494,38 GB`). Podawaj `"element"`
  w lokatorze.
- **Identyfikatory zamiast etykiet, gdy to możliwe.** `com.apple.settings.general`
  nie zależy od języka systemu, `General`/`Ogólne` — tak.
- **`snapshotMaxDepth`** — za mała wartość daje drzewo z samych kontenerów
  bez przycisków. 50 wystarcza dla Ustawień.
- **`inspect` nie restartuje aplikacji** (`forceAppLaunch: false`), żeby
  pokazać ekran, który jest w tej chwili widoczny.
- Wzorce w `odczyt` szukają grupy `(?P<wartosc>...)`; w `lista` także
  `(?P<nazwa>...)`. W JSON-ie backslash podwójnie: `\\s`.
- Przedrostek stanu (`Selected, X`) zdejmowany jest przed wzorcem listy.
