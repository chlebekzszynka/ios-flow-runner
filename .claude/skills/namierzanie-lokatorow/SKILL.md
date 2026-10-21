---
name: namierzanie-lokatorow
description: Procedura ustalania lokatorów dla nowego ekranu aplikacji iOS i dopisywania kroków do pliku konfiguracyjnego iOS Flow Runner. Użyj, gdy trzeba zmapować nowy ekran, dodać krok nawigacji albo pole do odczytu, naprawić krok, który przestał znajdować element, albo przygotować konfigurację dla innej aplikacji.
---

# Namierzanie lokatorów

Cel: dla każdego ekranu na ścieżce znaleźć element, w który trzeba dotknąć
(albo z którego czytamy wartość), i opisać go lokatorem w konfiguracji JSON.
Kod w `ios_flow/` zostaje bez zmian.

## Warunki

- Działa `appium` (osobny terminal) i symulator albo telefon z konfiguracji.
- Konfiguracja przechodzi `python -m ios_flow.run <plik> --sprawdz`.
- Aplikacja jest **ręcznie** ustawiona na ekranie, który mapujesz.
  `inspect` nie restartuje aplikacji — pokazuje to, co widać teraz.

## 1. Uruchom podgląd

```bash
python -m ios_flow.inspect configs/<plik>.json                  # przyciski, komórki, pola
python -m ios_flow.inspect configs/<plik>.json --szukaj version  # filtr po tekście
python -m ios_flow.inspect configs/<plik>.json --wszystkie       # też teksty i kontenery
python -m ios_flow.inspect configs/<plik>.json --zapisz-xml ekran.xml
```

Pusta tabela przy widocznym ekranie: ekran jeszcze się nie narysował
(odczekaj i powtórz) albo drzewo jest za płytkie — podnieś
`sesja.snapshot_max_depth`.

## 2. Odczytaj atrybuty

Przykład z Ustawienia → Ogólne → To urządzenie:

```
#   TYP          NAME (identyfikator)     LABEL (etykieta)        VALUE
1   Cell         SW_VERSION_SPECIFIER     iOS Version, 27.0
2   Button       SW_VERSION_SPECIFIER     iOS Version, 27.0
```

- `name` — identyfikator dostępności. Jeśli różni się od etykiety, zwykle
  nadał go programista: stabilny i niezależny od języka.
- `label` — tekst czytany przez VoiceOver; zależy od języka i bywa sklejony
  z kilku członów przecinkiem (`Nazwa, wartość`).
- `value` — wartość pól, przełączników, tekstów.
- Ten sam `name` na `Cell` i `Button` to norma w Ustawieniach. Etykieta
  komórki potrafi rozbić wartość (`494, 38 GB`) — czytaj z `Button`.

## 3. Wybierz typ lokatora

Kolejność preferencji:

| Sytuacja | Lokator |
|---|---|
| `name` różny od etykiety | `{"typ": "id", "wartosc": "<name>", "element": "Button"}` |
| tylko etykieta, pełny tekst | `{"typ": "etykieta", "wartosc": "General", "element": "Button"}` |
| etykieta z dopiskiem po przecinku | dodaj `"z_dopiskiem": true` (`Name` trafi w `Name, iPhone`, nie w `NameX`) |
| etykieta z przedrostkiem stanu | dodaj `"przedrostki_stanu": ["Selected"]` |
| warunek złożony | `{"typ": "predykat", "wartosc": "name == 'A' AND visible == 1"}` |
| ostateczność | `class_chain`, `xpath` (wolne, kruche) |

Nigdy `CONTAINS` / `LIKE` w predykacie — trafia w warianty (`20%` w `20%HM`).
Jeśli potrzebujesz dopasowania częściowego, to znak, że brakuje lepszego
atrybutu: wróć do kroku 2 z `--wszystkie`.

## 4. Dopisz krok albo pole

Krok nawigacji (dotknięcie):

```json
{
  "opis": "To urządzenie",
  "lokator": { "typ": "id", "wartosc": "com.apple.settings.general.about", "element": "Button" },
  "czekaj_s": 10,
  "pauza_s": 1.0
}
```

- `czekaj_s` — ile czekać na pojawienie się elementu. Element ładujący się
  wolniej niż reszta ekranu: podnieś tę wartość, nie `pauza_s` poprzedniego kroku.
- `"opcjonalny": true` — element bywa nieobecny z założenia (okienko,
  baner, wariant ekranu). Brak elementu pomija krok zamiast przerywać
  przebieg. Daj krótkie `czekaj_s` (2–4 s), bo tyle trwa każde pominięcie.
- `{zmienna}` w `wartosc` — wartość z `--zmienna "tekst"`; tylko w jednym kroku.

Pole do odczytu (sekcja `odczyt`):

```json
"wersja_systemu": {
  "lokator": { "typ": "id", "wartosc": "SW_VERSION_SPECIFIER", "element": "Button" },
  "atrybut": "label",
  "wzorzec": "^[^,]+,\\s*(?P<wartosc>.+)$"
}
```

## 5. Zweryfikuj

1. `python -m ios_flow.run configs/<plik>.json --sprawdz` — konfiguracja i capabilities.
2. `python -m ios_flow.run configs/<plik>.json` — przebieg od startu aplikacji.
   Przy błędzie w `artifacts/` zostają `*_blad.png` i `*_blad.xml` z chwili błędu.
3. Jeśli dodałeś wzorzec albo nową regułę listy: zapisz drzewo
   (`--zapisz-xml`), usuń z niego dane osobiste, dodaj do `tests/fixtures/`
   (wpis w `tests/fixtures/README.md`) i dopisz test na tej fiksturze.
4. `pytest -v` i `ruff check .`.
