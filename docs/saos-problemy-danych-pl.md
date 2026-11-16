# Problemy i wyzwania danych SAOS

## Cel dokumentu

Dokument jest podstawą do przygotowania slajdów o jakości danych pochodzących
z SAOS. Opisuje ograniczenia samego źródła: brakujące publikacje, niepełne
teksty, niespójne metadane i różne sposoby zapisu orzeczeń.

Nie opisuję tu problemów wynikających wyłącznie z naszego parsera, sposobu
parowania spraw ani implementacji pipeline'u. Liczności pochodzą z
`results/saos-data-quality.csv`; mianowniki są różne i zawsze podaję je przy
liczbie.

## Najważniejsze przesłanie

SAOS jest wartościowym, ale selektywnym i niejednorodnym źródłem. Największe
ryzyko nie polega na pojedynczych literówkach, lecz na tym, że:

- część orzeczeń ma metadane bez tekstu;
- uzasadnienia i sentencje bywają publikowane jako osobne rekordy;
- wiele apelacji wskazuje na orzeczenia pierwszej instancji, których nie ma
  w dostępnej kopii SAOS;
- kompletność metadanych różni się między rekordami;
- daty nie zawsze oznaczają to samo zdarzenie;
- tekst może mieć formę transkrypcji albo być niepełny.

W efekcie zbiór do modelowania nie jest prostą reprezentacją wszystkich
spraw, lecz wyselekcjonowanym podzbiorem opublikowanych i wystarczająco
kompletnych dokumentów.

## Ranking ważności problemów

Poniższa kolejność jest celowa: zaczyna się od problemów, które najbardziej
ograniczają reprezentatywność i poprawność zbioru modelowego, a kończy na
rzadkich anomaliach i problemach dotyczących opcjonalnych metadanych.

### 1. Selektywne pokrycie SAOS i brak orzeczeń pierwszej instancji

**132 188 z 145 773 (90,68%)** apelacji wskazujących orzeczenie pierwszej
instancji nie ma odpowiadającego dokumentu w dostępnej kopii SAOS. To
najpoważniejsze ograniczenie: model uczy się na sprawach, które zostały
opublikowane i zachowały wystarczający zestaw dokumentów, a nie na pełnej
populacji apelacji.

### 2. Brak zasadniczego tekstu orzeczenia

**21 256 z 357 527 (5,95%)** rekordów `SENTENCE` ma puste `textContent`.
Dodatkowo **16 369 z 175 076 (9,35%)** apelacyjnych rekordów `SENTENCE` nie
ma tekstu. Bez sentencji nie da się wiarygodnie odczytać treści orzeczenia
ani wyniku apelacji.

### 3. Niejednoznaczna struktura jednej sprawy

**1 753** spraw ma więcej niż jeden rekord `SENTENCE`, a **1 035** grup ma co
najmniej trzy rekordy tej samej sprawy. Sentencja i uzasadnienie mogą być
osobnymi publikacjami, a ich daty mogą się różnić. To utrudnia ustalenie,
który dokument jest właściwym przedstawicielem sprawy.

### 4. Niekompletne metadane

Brak sędziego dotyczy **48 421 z 474 894 (10,20%)** rekordów, brak keywords
**29,75%**, brak podstaw prawnych **28,92%**, a brak summary aż **90,56%**.
Metadane nie mogą być traktowane jako kompletne cechy wszystkich spraw.

### 5. Niejednorodna forma i kompletność tekstu

W danych występują transkrypcje, puste rozstrzygnięcia, niepełne rozpoznanie
wyniku i przypadki potencjalnie uciętych lub niepełnych dokumentów. Sama
anonimizacja nie jest tutaj traktowana jako problem jakości danych, a krótkie
uzasadnienie nie jest błędem, jeśli jest kompletne i merytorycznie wystarcza.

### 6. Niespójności dat

Występują zarówno pojedyncze ewidentne literówki w datach, jak i przypadki,
w których data publikacji poprzedza datę wyroku. Są ważne dla analiz
czasowych, ale liczebnie znacznie mniejsze niż problemy pokrycia i tekstu.

## 1. Niepełna dostępność tekstu orzeczeń

### Puste rekordy SENTENCE

**21 256 z 357 527 (5,95%)** rekordów typu `SENTENCE` ma puste
`textContent`. Rekord może zawierać identyfikator, sąd, sygnaturę, datę i
sędziów, ale nie zawiera sentencji, którą można przeczytać lub wykorzystać
do analizy.

To nie jest tylko problem techniczny formatu. Oznacza, że w SAOS istnieje
ślady orzeczenia, ale nie ma jego zasadniczej treści. Brakującego tekstu nie
można bezpiecznie odtworzyć z samej daty, sygnatury lub listy sędziów.

### Puste rekordy REASONS

**4 823 z 53 072 (9,09%)** rekordów `REASONS` ma puste `textContent`.
Może istnieć informacja, że uzasadnienie zostało zarejestrowane lub
opublikowane, ale samo uzasadnienie nie jest dostępne w tym rekordzie.

W SAOS sentencja i uzasadnienie mogą być osobnymi rekordami. Dlatego pusty
rekord `REASONS` nie oznacza zawsze braku uzasadnienia całej sprawy, ale
oznacza brak treści w konkretnej publikacji.

**Przykłady z raportu:** rekordy `418676`, `391901` i `424568` mają typ
`REASONS`, metadane sprawy i datę, lecz puste `textContent`.

### Puste lub niepełne teksty apelacyjne

- **16 369 z 175 076 (9,35%)** apelacyjnych rekordów `SENTENCE` nie ma tekstu;
- **1 239 z 148 512 (0,83%)** rekordów daje w ekstrakcji pusty tekst
  rozstrzygnięcia po rozpoznanym nagłówku apelacji i sygnaturze;
- **11 079 z 158 707 (6,98%)** tekstów nie zawiera rozpoznawalnego opisu
  zaskarżonego orzeczenia;
- **1 855 z 147 628 (1,26%)** nagłówków nie zawiera sygnatury orzeczenia
  pierwszej instancji.

Te przypadki ograniczają możliwość ustalenia, czego dotyczyła apelacja i jaki
był jej wynik. Są szczególnie istotne przy budowie zbioru uczącego, bo tekst
apelacji pełni rolę źródła etykiety lub identyfikacji sprawy.

Ta ostatnia kontrola jest obecnie przede wszystkim **problemem po naszej
stronie: ekstrakcji i heurystyki**, a nie potwierdzonym problemem SAOS.
Sprawdzone rekordy podobnego typu (`43`, `91`, `31`, `72`) zawierały pełne
rozstrzygnięcia po nagłówku, więc sam nagłówek nie jest problemem. W lokalnym
zbiorze nie ma surowego `textContent` dla 1 239 wskazanych rekordów, dlatego
nie możemy potwierdzić, że ich dokumenty źródłowe są fizycznie ucięte.
Regułę trzeba poprawić lub zweryfikować na surowych rekordach; dopiero
potwierdzone braki powinny być wykluczane z etykietowania.

## 2. Selektywne pokrycie i brak ciągłości spraw

### Brak orzeczeń pierwszej instancji

W **132 188 z 145 773 (90,68%)** przypadków, w których apelacja zawiera
odniesienie do orzeczenia pierwszej instancji, odpowiadającego orzeczenia nie
znaleziono w dostępnej kopii SAOS.

To najważniejsze ograniczenie reprezentatywności. Brak nie musi oznaczać, że
orzeczenie nigdy nie istniało — może oznaczać brak publikacji, brak w
pobranym zakresie albo niepełność archiwum. W każdym przypadku obserwujemy
tylko sprawy, dla których SAOS udostępnił wystarczający zestaw dokumentów.

**Przykłady:** `89|II AKa 31/98`, `89|II AKa 43/99`,
`89|II AKa 72/99`.

Konsekwencją jest ryzyko biasu selekcyjnego według sądu, okresu, rodzaju
sprawy i praktyki publikacyjnej.

### `judgmentIds` jako odsyłacze do przywołanych orzeczeń

Dokumentacja SAOS definiuje `referencedCourtCases[i].judgmentIds` jako
identyfikatory przywołanych orzeczeń w systemie SAOS. Dlatego fakt, że
odsyłacz prowadzi do innego sądu albo do sprawy, która nie jest zaskarżonym
wyrokiem pierwszej instancji, **nie jest błędem danych**. Jest to prawidłowa
informacja o orzeczeniu przywołanym w rekordzie.

Przykładowo apelacja `362278` (`VI Ka 511/18`) zawiera odsyłacze do
`IX K 1012/17`, ale może również zawierać przywołania do innych spraw. Te
relacje należy zachować jako referencje źródłowe. Nie należy używać ich
samodzielnie do automatycznego parowania apelacji z wyrokiem pierwszej
instancji; do tego celu służą sygnatura i informacja z nagłówka apelacji.

## 3. Wielorejestrowość i różne publikacje tej samej sprawy

### Więcej niż jedna sentencja

**1 753 z 418 164 (0,42%)** spraw ma więcej niż jeden rekord `SENTENCE`.
Może to oznaczać ponowne rozpoznanie, wyrok częściowy, duplikat albo kolejną
wersję publikacji.

### Wiele rekordów o tej samej sygnaturze

**1 035 z 55 368 (1,87%)** grup rekordów ma co najmniej trzy rekordy
powiązane z tą samą sprawą. Sama sygnatura nie mówi, czy rekordy są
uzupełniającymi się częściami, kolejnymi orzeczeniami, czy duplikatami.

### Osobne daty sentencji i uzasadnienia

Wśród spraw z osobnymi rekordami `SENTENCE` i `REASONS`:

- **152 z 39 654 (0,38%)** ma datę `REASONS` wcześniejszą niż datę sentencji;
- **121 (0,31%)** ma datę `REASONS` późniejszą o ponad rok.

Najbardziej prawdopodobne wyjaśnienie jest takie, że daty opisują różne
zdarzenia publikacyjne lub redakcyjne, a nie zawsze tę samą datę wydania
orzeczenia. Nie należy automatycznie interpretować ich jako dowodu błędnej
chronologii.

## 4. Niekompletne metadane

### Sędziowie

- **48 421 z 474 894 (10,20%)** rekordów nie zawiera żadnego sędziego;
- w finalnych danych modelowych **398 z 10 644 (3,74%)** rekordów nie ma
  jawnie wskazanej roli przewodniczącego; w **54** przypadkach jest dokładnie
  jeden sędzia, więc przewodniczącego można ustalić jednoznacznie, **340**
  rekordów nie zawiera żadnego sędziego, a tylko **4** mają wielu sędziów bez
  wskazanej roli;
- **89 z 734 415** wartości pola sędziego zawiera więcej niż jedno nazwisko
  lub dodatkowy tekst.

Brak sędziego może być neutralny dla modelu opartego wyłącznie na tekście,
ale ogranicza analizy instytucjonalne i modele wykorzystujące metadane.
W przypadkach z jednym sędzią można po naszej stronie deterministycznie
uzupełnić rolę przewodniczącego. Nie należy natomiast rekonstruować jej
na podstawie kolejności nazw, gdy w składzie jest więcej osób.

### Keywords, podstawy prawne i summary

- **141 270 z 474 894 (29,75%)** rekordów nie ma `keywords`;
- **137 334 (28,92%)** nie ma `legal_bases`;
- **430 080 (90,56%)** nie ma `summary`.

Te pola są nierównej jakości i nie mogą być traktowane jako kompletne
cechy wszystkich orzeczeń. Brak `summary` jest szczególnie częsty, więc
nie powinien być interpretowany jako wyjątek dotyczący pojedynczych spraw.

## 5. Jakość i forma tekstu

### Transkrypcje zamiast orzeczeń

**251 z 148 512 (0,17%)** tekstów apelacyjnych ma cechy transkrypcji:
znaczniki czasu, ślady OCR/ASR lub zapis przebiegu rozprawy. Taki tekst może
nie zawierać stabilnej, formalnej sentencji i utrudniać odczytanie wyniku
apelacji.

### Tekst sugeruje wynik, ale metadane go nie rozpoznają

**35 z 148 512 (0,02%)** tekstów zawiera sformułowanie wskazujące na
oddalenie apelacji, ale wynik nie został rozpoznany. Przykładowy fragment:

> „Uzasadnienie wyroku z dnia 18 kwietnia 2014 r. ... Apelacja podlega
> oddaleniu.”

To pokazuje, że tekst może być semantycznie użyteczny, ale formalna
reprezentacja wyniku w danych nie musi być kompletna ani jednoznaczna.

### Bardzo krótkie uzasadnienia

**4 z 10 644 (0,04%)** finalnych tekstów ma mniej niż 2 000 znaków.
Sprawdzono indywidualnie wszystkie cztery teksty. Każdy ma logiczny początek
i zakończenie; żaden nie wygląda na ucięty. Są to krótkie, kompletne dokumenty
o różnym charakterze: postanowienie uzupełniające wyrok, krótkie uzasadnienie
wyroku konsensualnego oraz postanowienie i zarządzenie w sprawach karnych.
Sama długość nie jest więc problemem jakościowym i nie uzasadnia wykluczenia.

## 6. Niespójności dat

### Daty wyroku poza zakresem lub nieparsowalne

Wykryto **3 z 474 894** rekordów:

- `358516`: `0208-03-14`, tekst zawiera „Sygn. akt II K 336/17”;
- `227221`: `2101-04-14`, tekst zawiera „Dnia 14 kwietnia 21016 r.”;
- `31345`: `3013-12-04`, tekst zawiera „Dnia 4 grudnia 3013 roku”.

To przykłady błędów w źródłowej wartości daty, a nie tylko różnic między
datą publikacji i datą orzeczenia.

### Publikacja przed datą wyroku

**44 z 474 894 (0,01%)** rekordów ma `publication_date` wcześniejszą niż
`judgment_date`.

Przykłady potwierdzone w API SAOS:

- rekord `199625`: `judgmentDate = 2016-02-13`,
  `publicationDate = 2016-02-10`, tekst: „Dnia 13 stycznia 2016 roku”;
- rekord `175911`: `judgmentDate = 2016-05-26`,
  `publicationDate = 2015-09-09`, tekst: „Dnia 26 maja 2016 roku”.

Nie musi to oznaczać niemożliwej publikacji. Może wskazywać na niespójność
metadanych albo różne znaczenie pól daty.

## Wnioski do slajdów

1. **SAOS nie jest kompletnym rejestrem tekstów**, lecz selektywnym zbiorem
   publikacji.
2. **Największe ryzyko to selekcja**, a nie pojedyncze literówki: brak
   pierwszej instancji dotyczy ponad 90% przypadków z takim odwołaniem.
3. **Jedna sprawa może mieć wiele rekordów**, a sentencja i uzasadnienie mogą
   być publikowane osobno.
4. **Metadane są nierówne**: szczególnie często brakuje summary, keywords,
   podstaw prawnych i sędziów.
5. **Daty wymagają interpretacji**, bo mogą opisywać różne zdarzenia i
   zawierać błędy źródłowe.
6. **Tekst nie zawsze jest kompletnym formalnym orzeczeniem**: może być pusty,
   ucięty albo mieć formę transkrypcji. Sama anonimizacja i mała długość nie
   są wystarczającym powodem do odrzucenia.

## Zakres wyłączony z tego dokumentu

Nie uwzględniono problemów wynikających wyłącznie z naszego parsera
sygnatur, reguł parowania, filtrów zbioru modelowego ani implementacji
pipeline'u. Te kwestie powinny być opisane osobno jako ograniczenia
techniczne przetwarzania danych.
