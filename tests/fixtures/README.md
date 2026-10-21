# Fikstury: zapisane drzewa elementów

Pliki XML w formacie, który zwraca `driver.page_source` dla aplikacji iOS
(korzeń `AppiumAUT`, elementy `XCUIElementType*` z atrybutami `name`,
`label`, `value`, `visible`). Pisane ręcznie, skrócone do elementów
potrzebnych w testach.

| Plik | Co odwzorowuje |
|---|---|
| `ustawienia_glowny.xml` | Ekran główny Ustawień (`com.apple.Preferences`) |
| `ogolne.xml` | Ustawienia → Ogólne |
| `to_urzadzenie_1.xml` | Ustawienia → Ogólne → To urządzenie, góra listy |
| `to_urzadzenie_2.xml` | Ten sam ekran po przewinięciu: górne wiersze niewidoczne, dwa nowe na dole |
| `lista_wariantow.xml` | **Syntetyczny** ekran listy do przypadków brzegowych: etykiety-warianty (`20%`, `20%HM`, `20%VM`), przedrostek stanu `Selected`, apostrof w etykiecie, element dla czytnika ekranu, element niewidoczny i element z głębszą nazwą (`VariantRow/Info`) |

Identyfikatory i układ ekranów Ustawień (`com.apple.settings.general`,
`SW_VERSION_SPECIFIER`, `NAME_CELL_ID`, etykiety w postaci „Nazwa, wartość”,
rozbity przecinek dziesiętny w etykiecie komórki) odpowiadają temu, co
pokazuje symulator iPhone z iOS 27. Numer seryjny i adresy MAC są zmyślone.

Nowa fikstura: zapisz drzewo z urządzenia
(`python -m ios_flow.inspect <konfiguracja> --zapisz-xml plik.xml`),
usuń z niego dane osobiste i zbędne gałęzie, dodaj wiersz do tabeli wyżej.
