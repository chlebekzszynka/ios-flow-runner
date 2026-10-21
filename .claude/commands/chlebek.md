---
description: Kontrola przed wydaniem — testy, ruff, audyt danych wrażliwych, wpis w CHANGELOG
allowed-tools: Bash(.venv/bin/pytest:*), Bash(pytest:*), Bash(.venv/bin/ruff:*), Bash(ruff:*), Bash(git grep:*), Bash(git status:*), Bash(git ls-files:*), Bash(test:*), Bash(grep:*), Read
---

Wykonaj kontrolę przed wydaniem. Każdy punkt uruchom niezależnie — błąd w
jednym nie przerywa pozostałych. Niczego nie poprawiaj; tylko raportuj.

Jeśli istnieje `.venv/bin/`, używaj stamtąd `pytest` i `ruff`.

1. **Testy:** `pytest -q`. Zanotuj liczbę zaliczonych i niezaliczonych;
   przy błędach nazwy testów.
2. **Lint:** `ruff check .` oraz `ruff format --check .`. Zanotuj liczbę
   problemów i pliki.
3. **Audyt danych wrażliwych:**
   - Sprawdź, czy istnieje `.audyt-wzorce` (`test -f .audyt-wzorce`). Brak
     pliku = audyt NIE WYKONANY (to nie jest sukces). Plik jest lokalny
     i ignorowany przez git.
   - `git grep --untracked -niEf .audyt-wzorce` — każde trafienie to błąd.
     W raporcie podaj plik i numer wiersza, ale **nie przepisuj treści
     trafienia ani zawartości `.audyt-wzorce`**.
   - Sprawdź, że `.audyt-wzorce` nie jest śledzony: `git ls-files --error-unmatch .audyt-wzorce`
     powinno zakończyć się błędem.
4. **CHANGELOG:**
   - Odczytaj wersję z `ios_flow/__init__.py` (`__version__`).
   - Sprawdź, czy `CHANGELOG.md` ma nagłówek tej wersji
     (`## [<wersja>]`) z datą i co najmniej jednym wpisem pod spodem.
   - Sekcja `## [Unreleased]` z treścią to ostrzeżenie: coś czeka na wydanie.
5. **Stan repozytorium:** `git status --short` — niezacommitowane zmiany to
   ostrzeżenie.

Na koniec wypisz raport dokładnie w tym układzie:

```
Kontrola przed wydaniem — iOS Flow Runner <wersja>

  [OK|BŁĄD|UWAGA]  Testy        <np. 130 zaliczonych>
  [OK|BŁĄD|UWAGA]  Ruff         <np. czysto / 3 problemy w 2 plikach>
  [OK|BŁĄD|UWAGA]  Audyt        <np. brak trafień / 2 trafienia: plik:wiersz / brak .audyt-wzorce>
  [OK|BŁĄD|UWAGA]  CHANGELOG    <np. wpis 1.0 z 2026-10-21 / brak wpisu dla 1.0>
  [OK|UWAGA]       Repozytorium <np. czysto / 4 pliki zmienione>

Werdykt: GOTOWE DO WYDANIA | NIE WYDAWAĆ
```

Werdykt „GOTOWE DO WYDANIA” tylko wtedy, gdy nie ma żadnego BŁĄD. Pod
werdyktem, przy NIE WYDAWAĆ, wypisz listę rzeczy do naprawy — po jednym
zdaniu, co zrobić.
