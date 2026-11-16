# Opis projektu: przewidywanie wyniku apelacji na podstawie orzeczeń SAOS

## 1. Temat

Budujemy klasyfikator, który na podstawie wyroku sądu pierwszej instancji
(uzasadnienia i metadanych) ma za zadanie przewidzieć, czy apelacja od tego wyroku
zostanie uwzględniona. Dane pochodzą z publicznego Systemu Analizy Orzeczeń Sądowych
(SAOS). Zbiór par „wyrok pierwszej instancji - orzeczenie apelacyjne” wraz z etykietą
zbudowaliśmy sami, bo SAOS takich par nie udostępnia.

## 2. Motywacja i pytanie badawcze

W polskich sądach powszechnych większość apelacji jest oddalana, a decyzja o jej
wniesieniu jest kosztowna. Model, który na podstawie samego wyroku pierwszej instancji
wskazuje, że dana sprawa ma duże szanse na zmianę wyroku po apelacji, mógłby nieść cenną informację i pomóc w podejmowaniu decyzji o tym, czy warto się odwoływać od wyroku sądu pierwszej instancji. Z perspektywy badawczej taki model mógłby pokazać, które cechy wyroku (sąd, przepisy, długość i treść uzasadnienia) wiążą się z jego zmianą.

Pytanie badawcze: czy na podstawie wyroku sądu pierwszej instancji (tekstu uzasadnienia i metadanych) da się przewidzieć, że apelacja od tego wyroku zostanie uwzględniona, lepiej niż zgaduje to sama częstość bazowa?

## 3. Źródło danych

Pełny zrzut danych z SAOS pobraliśmy 2026-11-03: 544 646 rekordów, około 27 GB JSON, z czego 474 894 to sądy powszechne.

Rekord zawiera pełny tekst orzeczenia, sygnaturę, sąd i wydział, skład sędziowski, datę, hasła tematyczne, podstawy prawne oraz przywołane przepisy znormalizowane do pozycji Dziennika Ustaw. Strony są zanonimizowane; sędziowie nie.

## 4. Etapy projektu i przygotowanie danych

Przygotowanie zbioru obejmuje kilka głównych kroków:

1. **Pobranie danych.** Z orzeczeń SAOS wybieramy sprawy apelacyjne i porządkujemy
   informacje potrzebne do dalszej analizy.
2. **Połączenie orzeczeń obu instancji.** Dla każdej apelacji szukamy wyroku
   pierwszej instancji, którego dotyczy. Porównujemy informacje o sprawie
   zawarte w orzeczeniach, takie jak sygnatura, sąd i data. Nie każdą apelację
   można połączyć z wyrokiem — część orzeczeń pierwszej instancji nie jest
   opublikowana w SAOS.
3. **Ustalenie wyniku apelacji.** Z treści orzeczenia apelacyjnego odczytujemy,
   czy sąd oddalił apelację, zmienił wyrok lub go uchylił. Odrzucenie apelacji
   i umorzenie postępowania pomijamy, ponieważ nie rozstrzygają o tym, czy
   zaskarżony wyrok był prawidłowy.
4. **Dobór spraw do zbioru końcowego.** Uwzględniamy sprawy z uzasadnieniem
   wyroku pierwszej instancji i rozpoznanym merytorycznie wynikiem apelacji.
   Jeśli od tego samego wyroku wniesiono więcej niż jedną apelację, w zbiorze
   pozostawiamy tylko jedną (najwcześniejszą).

Zbiór obejmuje apelacje z kilku dziedzin prawa. Najwięcej spraw udało się powiązać w sprawach cywilnych; znacznie mniej w sprawach z zakresu prawa pracy i ubezpieczeń społecznych.

| dziedzina | apelacje w SAOS | dopasowane pary | sprawy z uzasadnieniem I instancji | sprawy w zbiorze |
|---|---:|---:|---:|---:|
| prawo pracy | 7 667 | 504 | 413 | 406 |
| ubezpieczenia społeczne | 25 201 | 1 719 | 1 424 | 1 404 |
| cywilne | 86 462 | 8 168 | 5 994 | 5 919 |

Wśród wszystkich zgromadzonych spraw znajdują się również sprawy karne,
gospodarcze i rodzinne. Do dalszego modelowania rozważamy jedną z trzech
najliczniejszych dziedzin: prawo pracy, ubezpieczenia społeczne albo sprawy
cywilne.

Odsetek uwzględnionych apelacji w przygotowanych zbiorach różni się między
dziedzinami:

| dziedzina | liczba spraw | uwzględnione apelacje |
|---|---:|---:|
| prawo pracy | 406 | 18,7 % |
| ubezpieczenia społeczne | 1 404 | 25,6 % |
| cywilne | 5 919 | 35,1 % |

## 5. Wstępne obserwacje

Dotychczasowa analiza danych wskazuje na różnice między dziedzinami prawa oraz
na problemy z kompletnością i jakością publikowanych orzeczeń:

- Częstość uwzględniania apelacji różni się między dziedzinami: wynosi około
  19 % w sprawach z zakresu prawa pracy, 26 % w ubezpieczeniach społecznych
  i 35 % w sprawach cywilnych. Oznacza to, że samo przewidywanie oddalenia
  każdej apelacji może dawać pozornie dobry wynik.
- Część orzeczeń nie zawiera pełnego tekstu lub informacji o składzie sędziowskim,
  a w opublikowanych danych zdarzają się błędne daty i inne nieścisłości.
- Uzasadnienia wyroków pierwszej instancji są zwykle obszerne, co daje materiał do
  analizy, ale wymaga uwzględnienia różnic w długości i kompletności tekstów.

Analiza tych kwestii oraz wybór dziedziny badania są kolejnymi etapami projektu.

## 6. Plan badania

Najpierw wybierzemy dziedzinę prawa i ustalimy sposób rzetelnej oceny wyników. Punktem odniesienia będzie prosta prognoza, która zawsze zakłada oddalenie apelacji. Następnie sprawdzimy, czy informacje ogólne o sprawie pozwalają przewidywać wynik lepiej niż ten punkt odniesienia.

W kolejnych etapach zbadamy, czy treść uzasadnienia pierwszej instancji wnosi dodatkową wiedzę. Porównanie kolejnych podejść pozwoli ocenić, czy i w jakim stopniu dostępne informacje wiążą się z wynikiem apelacji. Sposób oceny ustalimy przed rozpoczęciem eksperymentów, zwracając szczególną uwagę na nierówny udział obu możliwych wyników.

W kolejnym etapie chcemy wprowadzić reprezentację grafową, która połączy wyroki na podstawie przepisów prawa do których się odnoszą. Możliwe są dalsze rozwinięcia grafu, korzystając z informacji o składzie sędziowskim lub cytowanych wyrokach. Sprawdzimy czy taka reprezentacja grafowa zwiększa moc predykcyjną modelu.

## 7. Ograniczenia i trudności

- **Niepełne dopasowanie spraw.** Do analizy trafiają tylko przypadki, w których
  opublikowano zarówno orzeczenie apelacyjne, jak i wyrok pierwszej instancji.
  Mogą one różnić się od spraw, których nie opublikowano.
- **Poprawność określenia wyniku.** Wynik ustalamy na podstawie treści orzeczenia
  apelacyjnego, dlatego część przypadków może wymagać dodatkowej weryfikacji.
- **Wykorzystanie informacji o sądach i sędziach.** Orzeczenia są zanonimizowane
  w różnym stopniu, a nazwiska sędziów są publiczne. Projekt ma charakter
  badawczy: jego wyniki nie powinny służyć do oceniania pojedynczych sędziów.


## 8. Zespół

Projekt realizują Mateusz Sztefek, Julia Bartczak i Nikodem Buszko.
