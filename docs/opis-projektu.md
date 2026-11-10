# Opis projektu: przewidywanie wyniku apelacji na podstawie orzeczeń SAOS

## 1. Streszczenie

Budujemy klasyfikator, który na podstawie wyroku sądu pierwszej instancji
(uzasadnienia i metadanych) szacuje prawdopodobieństwo, że apelacja od tego wyroku
zostanie uwzględniona. Dane pochodzą z publicznego Systemu Analizy Orzeczeń Sądowych
(SAOS). Zbiór par „wyrok pierwszej instancji, orzeczenie apelacyjne” wraz z etykietą
zbudowaliśmy sami, bo SAOS takich par nie udostępnia.

## 2. Motywacja i problem

W polskich sądach powszechnych większość apelacji jest oddalana, a decyzja o jej
wniesieniu jest kosztowna. Model, który na podstawie samego wyroku pierwszej instancji
wskazuje, że dana sprawa odbiega od typowej, mógłby wspierać taką decyzję,
a z perspektywy badawczej pokazać, które cechy wyroku (sąd, przepisy, długość i treść
uzasadnienia) wiążą się z jego zmianą.

Pytanie badawcze: czy na podstawie wyroku sądu pierwszej instancji (tekstu
uzasadnienia i metadanych) da się przewidzieć, że apelacja od tego wyroku zostanie
uwzględniona, lepiej niż zgaduje to sama częstość bazowa?

## 3. Źródło danych: SAOS

SAOS (saos.org.pl) udostępnia przez REST API bez klucza orzeczenia sądów powszechnych,
Sądu Najwyższego, Trybunału Konstytucyjnego i Krajowej Izby Odwoławczej. Pełny zrzut
pobraliśmy 2026-11-03: 544 646 rekordów, około 27 GB JSON, z czego 474 894 to sądy
powszechne. Tylko z nich korzystamy.

Rekord zawiera pełny tekst orzeczenia, sygnaturę, sąd i wydział, skład sędziowski,
datę, hasła tematyczne, podstawy prawne oraz przywołane przepisy znormalizowane
do pozycji Dziennika Ustaw. Strony są zanonimizowane; sędziowie nie.

## 4. Jak powstał zbiór danych

Cały proces jest kodem w pakiecie `saos_appeals`, uruchamianym jako kolejne komendy.
Każdy etap zapisuje plik pośredni, a wynik końcowy jest zamrożony i nazwany hashem
swojej zawartości.

1. **Przygotowanie** (`saos-download`, `saos-extract`, `saos-judgments`): pobranie
   zrzutu, podział na typy sądów, parsowanie sygnatur i nagłówków, czyszczenie tekstu,
   scalenie wyroku z osobno opublikowanym uzasadnieniem w jedną sprawę.
2. **Parowanie** (`saos-pair`): orzeczenie apelacyjne nazywa w nagłówku zaskarżony wyrok
   („na skutek apelacji pozwanego od wyroku Sądu Rejonowego w Gliwicach z dnia … sygn. akt
   VI P 1651/07”). Odczytujemy stamtąd sygnaturę, sąd i datę, a następnie szukamy wyroku
   w sądach bezpośrednio podległych sądowi apelacyjnemu w słowniku SAOS. Para jest
   potwierdzona, gdy zgadza się data z nagłówka, a przy jej braku nazwa sądu.
3. **Etykieta** (`saos-label`): sentencja sądu drugiej instancji kończy się rozstrzygnięciem
   z małego, stałego słownika. „Oddala apelację” daje etykietę 0; „zmienia”, „zmienia w części”
   i „uchyla” dają 1. Odrzucenie (formalne) i umorzenie (cofnięcie) nie trafiają do zbioru,
   bo nie mówią nic o trafności wyroku.
4. **Zamrożenie** (`saos-dataset`): jeden plik na domenę. Z orzeczenia apelacyjnego
   zostaje tylko etykieta, data i klucze; cały tekst wejściowy pochodzi z pierwszej
   instancji. Pliki mają wstępne kolumny podziału na train/valid/test; schemat
   walidacji jest jeszcze do ustalenia (zob. `docs/plan.md`).

Linki między orzeczeniami, które SAOS sam wyznacza (`judgmentIds`), okazały się
bezużyteczne: 89 % z nich wskazuje sprawę o tej samej sygnaturze w niepowiązanym sądzie.
Dlatego parowanie opiera się wyłącznie na nagłówku i hierarchii sądów.

**Domena** sprawy wynika z kodu repertorium w sygnaturze apelacji: Pa i APa to prawo
pracy, Ua i AUa ubezpieczenia społeczne, Ca i ACa sprawy cywilne, analogicznie karne,
gospodarcze i rodzinne. Bierzemy wyłącznie apelacje od wyroków; zażalenia na
postanowienia (kody z literą z, np. Pz) są poza zbiorem.

### Od apelacji w SAOS do wiersza w zbiorze

Dane z `results/pairing-census.csv` i `datasets.json`. Apelację od wyroku sądu
rejonowego rozpoznaje sąd okręgowy, od wyroku sądu okręgowego sąd apelacyjny;
tabela sumuje oba poziomy.

| domena | apelacje w SAOS | dopasowane | potwierdzone | z uzasadnieniem I instancji | w zbiorze |
|---|---|---|---|---|---|
| prawo pracy | 7 667 | 504 | 456 | 413 | 406 |
| ubezpieczenia społeczne | 25 201 | 1 719 | 1 592 | 1 424 | 1 404 |
| cywilne | 86 462 | 8 168 | 6 870 | 5 994 | 5 919 |

Największa strata następuje przy dopasowaniu: dla 91 % apelacji z rozpoznaną sygnaturą
wyrok pierwszej instancji w ogóle nie jest opublikowany w SAOS. Skąd pochodzą pary,
zależy od domeny: w prawie pracy prawie wszystkie z sądów okręgowych (Pa, czyli
pierwsza instancja w sądzie rejonowym), w ubezpieczeniach społecznych i cywilnych
głównie z sądów apelacyjnych (AUa, ACa). Różnica między ostatnimi dwiema
kolumnami to filtr etykiety (odrzucenia, umorzenia, nierozpoznane rozstrzygnięcia)
i zasada jednej apelacji na wyrok.

### Zamrożone zbiory

Dane z `data/processed/datasets.json`. Udział uwzględnionych to odsetek etykiety 1.

| domena | wiersze | uwzględnione | oddalono | zmieniono w części | zmieniono | uchylono |
|---|---|---|---|---|---|---|
| prawo pracy | 406 | 18,7 % | 330 | 31 | 31 | 14 |
| ubezpieczenia społeczne | 1 404 | 25,6 % | 1 044 | 59 | 228 | 73 |
| cywilne | 5 919 | 35,1 % | 3 843 | 1 340 | 528 | 208 |
| karne | 2 514 | 50,2 % | 1 252 | 829 | 147 | 286 |
| gospodarcze | 343 | 37,6 % | 214 | 58 | 53 | 18 |
| rodzinne | 58 | 43,1 % | 33 | 20 | 4 | 1 |

Każdy wiersz to jedna apelacja. Wejście to wyrok pierwszej instancji: sąd, wydział,
poziom sądu, data, skład sędziowski, hasła tematyczne, podstawy prawne, przywołane
przepisy, sentencja i uzasadnienie. Wyjście to etykieta i czteroklasowe
rozstrzygnięcie. W wejściu celowo nie ma niczego z orzeczenia apelacyjnego; nie ma
też jeszcze informacji, kto wniósł apelację, choć da się ją odczytać z nagłówka.
Jeden wyrok występuje w zbiorze najwyżej raz. Do modelowania wybierzemy jedną
z trzech pierwszych domen; sprawy karne, gospodarcze i rodzinne są poza zakresem.

## 5. Co już wiemy z eksploracji

Notatniki `01`–`03` pokazują dla trzech domen rozkład etykiety, czas, sądy, składy,
długości tekstów i podstawy prawne. Notatnik `04` zbiera problemy jakości danych SAOS
do tabeli `results/saos-data-quality.csv`. Sekcja do uzupełnienia po analizie domen
i weryfikacji listy błędów przed prezentacją. Obserwacje na dziś:

- Częstość bazowa różni się między domenami: w prawie pracy uwzględnia się 19 % apelacji,
  w ubezpieczeniach społecznych 26 %, w sprawach cywilnych 35 %. Model „zawsze oddala”
  ma więc w prawie pracy trafność 81 %, co czyni trafność bezużyteczną jako metrykę.
- Rodzaj uwzględnienia też się różni: w prawie pracy zmiany pełne i częściowe są po
  równo, w ubezpieczeniach społecznych dominuje pełna zmiana, w cywilnych częściowa.
- Jakość danych SAOS: 6 % wyroków nie ma tekstu, 10 % rekordów nie ma żadnego sędziego,
  30 % nie ma haseł tematycznych, zdarzają się daty typu „3013-12-04” i sklejone nazwiska
  sędziów. Przypadki są policzone w tabeli jakości; lista jest w trakcie weryfikacji.
- Uzasadnienia pierwszej instancji są długie (mediana ok. 26 tys. znaków w prawie pracy,
  16 tys. w ZUS, 27 tys. w cywilnych) i rzadko mocno zanonimizowane (1,5 % wierszy ma
  ponad 5 wycięć na tysiąc znaków).

## 6. Podejście modelowe

Zaczynamy od punktu odniesienia „zawsze oddala” i prostego baseline'u na metadanych
wyroku (sąd, rok, przepisy, hasła tematyczne, długości tekstów). Baseline odpowiada
na pytanie, czy w danych jest jakikolwiek sygnał. Kolejne modele, w szczególności
wykorzystujące tekst uzasadnienia, dobierzemy po jego wynikach.

Sposób oceny (metryki, schemat walidacji) ustalimy przed pierwszym eksperymentem
i zapiszemy w `docs/plan.md`.

## 7. Ograniczenia i kwestie etyczne

- **Selekcja publikacji.** SAOS zawiera to, co sądy zdecydowały się opublikować, a para
  istnieje tylko wtedy, gdy opublikowały oba sądy. Rozkład etykiet w zbiorze nie musi
  odpowiadać rzeczywistej skuteczności apelacji.
- **Wyciek informacji.** Największe zagrożenie dla wiarygodności wyników. Zbiór nie zawiera
  żadnego tekstu z drugiej instancji; wszelkie cechy liczone z innych spraw muszą
  powstawać wyłącznie na danych treningowych.
- **Etykieta z wyrażeń regularnych.** Słownik rozstrzygnięć jest mały i stały, ale planujemy
  ręczną weryfikację losowej próbki etykiet i zapisanie jej wyniku.
- **Sędziowie nie są zanonimizowani.** Cechy związane ze składem wykorzystujemy tylko
  w postaci zagregowanej i nie publikujemy żadnych rankingów ani profili sędziów.
  Model nie jest narzędziem do oceny sędziów i nie powinien być tak używany.
- **Mała próba.** W prawie pracy pozytywnych przykładów jest 76; wyniki będą miały
  duży rozrzut, który raportujemy, zamiast go ukrywać.

## 8. Repozytorium i odtwarzalność

Kod, testy i konfiguracja są w repozytorium
https://github.com/MateuszSztefek/saos-appeal-classifier; dane nie, ze względu
na rozmiar. Stos: Python 3.12, uv, pandas i pyarrow, pytest dla kodu parsującego,
ruff i pre-commit, CI na GitHubie. Praca na gałęziach i pull requestach z jednym
przeglądem. Kod i commity po angielsku, dokumenty dla prowadzącego po polsku.

Zamrożone zbiory i pliki pośrednie udostępniamy przez Google Drive. `datasets.json`
obok zbiorów zawiera hashe SHA-256, liczby wierszy i granice podziałów, więc pobraną
kopię da się zweryfikować. Z plików pośrednich trzy komendy odbudowują zbiory
w kilka minut i powinny dać identyczne hashe; odtworzenie od zera z surowego zrzutu
trwa kilka godzin. Wyniki eksperymentów trafiają do `results/` z hashem zbioru,
na którym powstały.

## 9. Zespół i przebieg przedmiotu

Mateusz Sztefek, Julia Bartczak, Nikodem Buszko. Zadania rozdzielamy na bieżąco
na spotkaniach; kto co zrobił, widać w historii repozytorium.

Projekt ma dwa punkty kontrolne: prezentację założeń, danych i ich jakości
2026-11-17 oraz raport końcowy na koniec semestru.
