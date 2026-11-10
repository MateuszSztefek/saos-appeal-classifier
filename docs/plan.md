# Plan projektu

## 1. Cel i pytanie badawcze

Czy na podstawie wyroku sądu pierwszej instancji (tekstu uzasadnienia i metadanych)
da się przewidzieć, że apelacja od tego wyroku zostanie uwzględniona, lepiej niż
zgaduje to sama częstość bazowa?

## 2. Zakres

**Decyzja otwarta: domena.** Zamrożone zbiory istnieją dla sześciu domen,
ale sensowne do modelowania są trzy. Opcje:

| opcja | wiersze | udział uwzględnionych | za |
|---|---|---|---|
| A. prawo pracy | 406 | 19 % | jednorodna domena, czytelna interpretacja |
| B. ubezpieczenia społeczne | 1 404 | 26 % | ten sam wydział sądu co prawo pracy, 3,5 raza więcej danych |
| C. sprawy cywilne | 5 919 | 35 % | największy zbiór, najstabilniejsza ewaluacja |

Wybieramy jedną domenę; łączenia zbiorów nie rozważamy. Każda opcja ma swój
notatnik EDA: `03` prawo pracy, `02` ubezpieczenia społeczne, `01` cywilne.
Decyzja przed prezentacją 2026-11-17.

Jak powstał zbiór, co jest wejściem i jak wygląda etykieta, opisuje
`docs/opis-projektu.md`; układ plików opisuje `data/README.md`.

## 3. Ewaluacja (do ustalenia)

Sposób oceny modeli ustalamy przed pierwszym eksperymentem i zapisujemy tutaj,
żeby nie dopasowywać metryk do wyników. Wymaga krótkiego researchu, jak ocenia się
klasyfikatory w podobnych pracach o przewidywaniu orzeczeń.

Co już wiemy:

- Model „zawsze oddala” ma trafność ok. 81 % w prawie pracy, 74 % w ZUS i 65 %
  w cywilnych. Trafność sama w sobie nic nie mówi, potrzebujemy metryki wrażliwej
  na klasę mniejszościową.
- Zamrożone zbiory mają dwie kolumny: `split` (podział czasowy 70/15/15 po dacie
  apelacji) i `fold` (losowy, stratyfikowany po etykiecie podział na 5 części).
  Podział czasowy po dacie apelacji jest sensowny, bo etykieta powstaje w tej dacie.
  Z foldami w obecnej postaci są trzy problemy:
  1. **Foldy obejmują też wiersze z `test`.** Każdy split zawiera wszystkie pięć foldów.
     Dobór modelu walidacją krzyżową na całym zbiorze i raport na `test` oznacza, że
     zbiór testowy brał udział w rozwoju.
  2. **Losowe foldy ignorują czas.** Model uczony na sprawach z 2024 ocenia sprawy
     z 2014. Dane pokazują dryf: w cywilnych udział uwzględnionych rośnie z 33 %
     w `train` do 42 % w `test`. Walidacja krzyżowa ten dryf ukrywa.
  3. **Sprawy seryjne.** W cywilnych 4 427 z 5 919 wierszy dzieli sąd, przewodniczącego
     i rok z innym wierszem, największa grupa ma 27 spraw. Losowe foldy rozdzielają
     serię między train i test; model może zapamiętać szablon uzasadnienia i tendencję
     sądu. Stratyfikacja po etykiecie nic na to nie daje.

  Wnioski: kolumna `fold` nie nadaje się do użycia na wierszach testowych i przy
  najbliższym odświeżeniu zbiorów trzeba ją przebudować albo usunąć. Opcje do
  rozważenia: tylko podział czasowy (w prawie pracy `test` to 61 wierszy, ok. 11
  pozytywnych); foldy wyłącznie wewnątrz `train` + `valid`; walidacja czasowa
  krocząca (uczenie do roku t, ocena na t+1); foldy grupowe po sądzie, sędzim
  i roku lub po klastrach podobnych tekstów. Opcje można łączyć.

Do ustalenia:

- [ ] metryki główne i pomocnicze,
- [ ] schemat walidacji w trakcie rozwoju i w raporcie końcowym, z uwzględnieniem
      trzech problemów powyżej; w ślad za tym przebudowa lub usunięcie kolumny `fold`,
- [ ] format tabeli wyników w `results/` (co najmniej hash zbioru, model, metryki),
- [ ] czy i jak robimy ręczną analizę błędów.

## 4. Eksperymenty

Pierwszy krok jest pewny: **baseline** na metadanych wyroku (sąd, rok, przepisy,
hasła tematyczne, długości tekstów) z prostym modelem, np. regresją logistyczną.

Cecha do rozważenia przed baselinem: **kto wnosi apelację** (powód / pozwany / obie
strony). Jest w nagłówku orzeczenia apelacyjnego („na skutek apelacji pozwanego”),
znana przed wyrokiem, więc nie jest wyciekiem. Trzeba ją wyciągnąć w `saos-pair`
i dodać do zbioru, co zmieni hash plików.

## 5. Harmonogram

Dwa terminy z przedmiotu:

| termin | co | stan |
|---|---|---|
| 2026-11-17 | prezentacja: założenia projektu, dane, jakość danych, plan | w przygotowaniu |
| koniec semestru `[dokładna data]` | raport końcowy; wymagania co do zawartości jeszcze nieustalone | |

### Zrobione

- [x] Repo, środowisko, CI, zasady współpracy (2026-11-03)
- [x] Pobranie zrzutu SAOS i podział na typy sądów (2026-11-03)
- [x] Parowanie apelacji z pierwszą instancją, etykieta, zamrożone zbiory (2026-11-06)
- [x] Notatniki EDA dla trzech domen i raport jakości danych SAOS (2026-11-07)
- [x] Udostępnienie zbiorów zespołowi przez Google Drive

### Do prezentacji 2026-11-17

- [ ] Weryfikacja listy błędów SAOS z `results/saos-data-quality.csv`: czy każdy wiersz
      jest prawdziwy na przykładach, czy coś pominęliśmy, które problemy są istotne dla modelu
- [ ] Analiza trzech domen (prawo pracy, ZUS, cywilne) w notatnikach `01`–`03`
      i decyzja o domenie, z uzasadnieniem w dzienniku decyzji
- [ ] Prezentacja: cel, SAOS, jak powstał zbiór, jakość danych, decyzja o domenie,
      plan eksperymentów, ryzyka

### Po prezentacji

- [ ] Ustalenie ewaluacji (sekcja 3)
- [ ] Baseline na metadanych i tabela wyników
- [ ] Cecha „kto apeluje”, odświeżenie zbiorów
- [ ] Decyzja o kolejnych eksperymentach na podstawie baseline'u
- [ ] Kolejne eksperymenty
- [ ] Raport końcowy, gdy znane będą wymagania

## 6. Ryzyka

| ryzyko | skutek | jak ograniczamy |
|---|---|---|
| wyciek informacji z drugiej instancji | zawyżone wyniki, bezwartościowy model | w zbiorze nie ma tekstu apelacyjnego; każda cecha liczona z innych spraw musi powstawać wyłącznie na danych treningowych |
| niezbalansowanie klas | trafność myli | metryka wrażliwa na klasę mniejszościową, do ustalenia w sekcji 3 |
| błędy etykiety z regexu | szum w celu | ręczna weryfikacja losowej próbki etykiet, wynik zapisany w `results/` |
| dryf w czasie | model uczy się „sędzia X w 2019” | kolumna `split` z podziałem czasowym jest w danych; jej użycie do ustalenia w sekcji 3 |
| kosztowne metody (duże modele językowe, grafy) | utopiony czas bez zysku nad baselinem | najpierw baseline, dalsze kroki dopiero na podstawie jego wyników |

## 7. Decyzje

| data | decyzja | powód |
|---|---|---|
| 2026-11-03 | uv, Python 3.12, pandas + pyarrow, kod i commity po angielsku | standardowy, lekki stos; dokumenty dla prowadzącego po polsku |
| 2026-11-03 | dane poza gitem, udostępniane przez Google Drive, pliki nazwane hashem | repo ma być lekkie, a wersja zbioru jednoznaczna |
| 2026-11-06 | nie ufamy linkom `judgmentIds` z SAOS, parujemy po nagłówku i hierarchii sądów | 89 % linków wskazuje niepowiązany sąd |
| 2026-11-06 | etykieta binarna: cokolwiek zmieniono → 1; odrzucenie i umorzenie poza zbiorem | te wyniki nie mówią nic o trafności wyroku |
| 2026-11-07 | model tekstowy tylko na wierszach z uzasadnieniem pierwszej instancji | bez uzasadnienia tekst to sam nagłówek |
| `[data]` | domena: `[A / B / C]` | |
| `[data]` | schemat walidacji: `[do ustalenia, sekcja 3]`; kolumny `split` i `fold` w zbiorach są wstępne, nie decyzją | w obecnych foldach są trzy problemy opisane w sekcji 3 |
