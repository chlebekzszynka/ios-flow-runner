# Changelog

Wszystkie istotne zmiany w projekcie. Format według
[Keep a Changelog](https://keepachangelog.com/pl/1.1.0/), numeracja wersji
według [Semantic Versioning](https://semver.org/lang/pl/).

## [Unreleased]

## [1.0] - 2026-10-21 — Pierwsza Kromka

Pierwsze wydanie. Kromka posmarowana, szynka położona, wegetarianie
proszeni o cierpliwość.

### Dodane

- Przepływ sterowany plikiem JSON: kroki nawigacji, odczyt pól i lista
  z przewijaniem (`python -m ios_flow.run`); kod nie zna żadnej aplikacji.
- Dwa tryby pracy w polu `tryb`: `symulator` (bez konta Apple Developer)
  i `urzadzenie` (podpisany WebDriverAgent na telefonie).
- Walidacja konfiguracji, która zgłasza wszystkie braki naraz i podaje,
  skąd wziąć każdą brakującą wartość; `--sprawdz` bez łączenia z Appium.
- Lokatory `id`, `etykieta`, `predykat`, `class_chain`, `xpath`; dopasowanie
  zawsze dokładne, z obsługą dopisku po przecinku i przedrostków stanu.
- Kroki opcjonalne — brak elementu pomija krok zamiast przerywać przebieg.
- Krok zmienny `{zmienna}` wypełniany z `--zmienna`.
- Zbieranie list z przewijaniem i scalaniem wyników bez duplikatów
  (`--lista`), z pomijaniem elementów dla czytnika ekranu.
- Wynik w JSON-ie ze znacznikiem czasu, surowymi tekstami i zrzutem ekranu;
  przy błędzie nawigacji zrzut i drzewo elementów z chwili błędu.
- Podgląd elementów ekranu z propozycjami lokatorów
  (`python -m ios_flow.inspect`), także z zapisanego pliku XML.
- Przykład dla Ustawień na symulatorze i szablon dla telefonu.
- 131 testów na ręcznie pisanych drzewach XML — bez urządzenia,
  symulatora i Appium; CI na Pythonie 3.11 i 3.13.
- Pliki Claude Code: `CLAUDE.md`, komenda `/chlebek`, skill
  `namierzanie-lokatorow`, podagent `recenzent`.
- `--version`, bo każdy szanujący się projekt musi umieć się przedstawić.

[Unreleased]: https://github.com/chlebekzszynka/ios-flow-runner/compare/v1.0...HEAD
[1.0]: https://github.com/chlebekzszynka/ios-flow-runner/releases/tag/v1.0
