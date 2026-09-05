# Image Tagger

Egyszerű Python-alkalmazás képenként több, kézzel szerkeszthető négyszög rögzítéséhez.
Magyar kezelőfelület, automatikus mentés, folytatható munkamenet és területstatisztikák.

## Indítás

Python 3.10 vagy újabb, Tkinter és Pillow szükséges. A Windows hivatalos Python-telepítőjében
a **tcl/tk and IDLE** komponens legyen telepítve.

```powershell
python -m pip install -r requirements.txt
python image_tagger.py "C:\Projects\ImageTagger\budapest_kozut"
```

A `start_image_tagger.cmd` dupla kattintással indítja az alkalmazást; ezután a
**Mappa megnyitása…** gombbal választható ki a képmappa. A program argumentum nélkül is fut:

```powershell
python image_tagger.py
```

A kiválasztott mappa közvetlen képfájljait kezeli, almappákat nem jár be.
Támogatott: JPG/JPEG, PNG, BMP, TIF/TIFF, WEBP, GIF. Többképes fájl esetén az első képkockát használja.

## Használat

| Művelet | Kezelés |
| --- | --- |
| Új téglalap | Bal egérgombbal húzás a kép üres részén, bármelyik irányba |
| Átfedő objektum felvétele | **N**, majd húzás; sikeres rajzolás után visszavált kijelölésre |
| Kijelölés | Kattintás a négyszög belsejébe vagy a jobb oldali objektumlistában |
| Sarok igazítása | Kijelölés után a sárga sarokfogantyú húzása |
| Teljes négyszög mozgatása | Kijelölt négyszög belsejének húzása |
| Törlés | **Delete** vagy **Backspace** |
| Visszavonás / újra | **Ctrl+Z** / **Ctrl+Y**, képenként az utolsó 100 lépés |
| Aktuális húzás elvetése | **Esc**; húzás nélkül megszünteti a kijelölést |
| Kijelölési mód | **V** |
| Előző / következő kép | **Bal / jobb nyíl**, illetve a felső gombok |
| Nagyítás | Egérgörgő, a kurzor pozíciója körül |
| Nagyított kép mozgatása | Középső egérgomb húzása |
| Teljes kép az ablakba | **F** |
| Mentés azonnal | **Ctrl+S** |
| Statisztika megtekintése és mentése | **Statisztika** gomb |

A téglalapból konvex, tetszőlegesen ferde négyszög készíthető. A sarkok nem keresztezhetik
egymást, és nem hagyhatják el a képet. A minimális objektumterület 1 eredeti képpixel²;
az új téglalap mindkét oldalát legalább 3 képernyőpixelnyire kell húzni.
Átfedésnél az objektumlista segít a takarásban lévő négyszög kijelölésében.

## Mentési formátum és folytatás

Az eredeti képeket nem módosítja. A kiválasztott képmappán belül létrehozza az
`annotations` almappát. Minden szerkesztett képhez a **teljes képfájlnév + `.txt`** nevet használja:

```text
budapest_kozut/
  foto.jpg
  foto.png
  annotations/
    foto.jpg.txt
    foto.png.txt
    session.json
    statistics.json
    statistics_per_image.csv
```

Így az azonos nevű, különböző kiterjesztésű képek annotációi sem ütköznek.
Egy objektum egy sor, szóközzel elválasztott **8 szám**, osztályazonosító és fejléc nélkül:

```text
tl_x tl_y tr_x tr_y br_x br_y bl_x bl_y
```

Példa:

```text
0.1 0.2 0.6 0.15 0.65 0.7 0.12 0.75
```

Az origó a kép bal felső sarka, x jobbra, y lefelé nő. Minden x a kép eredeti szélességével,
minden y a magasságával osztott koordináta, a **[0, 1]** tartományban.
A saroksorrend az eredetileg rajzolt téglalap **bal felső, jobb felső, jobb alsó, bal alsó**
sarkának megfelelő TL, TR, BR, BL; a sarok mozgatásakor annak azonosítója megmarad.
A mentés teljes pontosságú, ezért egyes számok hosszabb tizedes alakban szerepelhetnek.

A képek a fájlban tárolt pixelirányban jelennek meg, EXIF szerinti automatikus forgatás nélkül.
Az annotációk ugyanebben a koordinátarendszerben értendők; a nagyítás és az ablakméret nem
befolyásolja a mentett értékeket.

- Minden befejezett szerkesztés azonnal mentődik. Hosszú sarokhúzás vagy mozgatás közben
  250 ms-onként is menti az aktuális érvényes állapotot. Az új téglalap előnézete az egér
  felengedésekor válik annotációvá.
- A mentés átmeneti fájlon és atomi fájlcserén keresztül történik.
- Képváltás, mappaváltás és bezárás előtt ment. Mentési hiba esetén jelzést ad;
  sikertelen mentéssel nem vált képet/mappát és nem zárja be az alkalmazást.
- Az utolsó objektum törlése után üres `.txt` marad. Az érintetlen képhez nem készül címkefájl.
- Ugyanazt a képmappát újra megnyitva betölti az annotációkat és visszatér a legutóbbi képhez.
  A visszavonási előzmények csak az aktuális munkamenetben élnek.
- Az **annotált képek** számláló legalább egy objektumot tartalmazó képeket számol;
  nem jelenti azt, hogy a kép feldolgozása végleg befejeződött.
- Hibás annotációs fájlt nem ír felül: az érintett kép csak olvasható lesz, és a hiba megjelenik
  az állapotsorban és a statisztikában. Külső javítás után nyisd meg újra a mappát.
- Egy képmappát egyszerre egy alkalmazáspéldányban szerkessz; a program a mappa megnyitásakor
  olvassa be a külső fájlokat.

## Statisztika

A **Statisztika** gomb, a mappaváltás és a szabályos bezárás két fájlt ment:

- `statistics.json`: összes/annotált kép, összes objektum, átlagos/minimális/maximális
  objektumterület pixel²-ben, objektumok átlaga az összes és külön az annotált képekre,
  hibás képek/annotációk listája és időbélyeg.
- `statistics_per_image.csv`: képenként a méret, darabszám, átlagos és összes objektumterület,
  valamint az esetleges hiba. Táblázatkezelőben is megnyitható.

A területet a négyszög tényleges sarkaiból a shoelace-képlettel számolja, eredeti
pixelméretre átszámítva. Az átfedő objektumokat külön számolja, területeik összeadódnak.
A hibás annotációjú képek is beleszámítanak az összes képbe, de objektumaik ismeretlenek és
kimaradnak az objektumszámból; olvashatatlan kép esetén a betölthető objektumokat számolja,
területüket kihagyja. A hibaszámláló és az `objects_with_measurable_area` mező ezt jelzi.
Objektumok hiányában az átlagok nullák. Váratlan leállás után az annotációk az utolsó
automatikus mentésig megmaradnak; a statisztika a következő mentéskor frissül.

## Ellenőrzés

Tárolás, formátum, területszámítás és mentési hibák tesztjei:

```powershell
python -m unittest discover -s tests -v
```

Az ablakos szerkesztési tesztek külön bekapcsolhatók (rövid időre tesztablakokat nyitnak):

```powershell
$env:IMAGE_TAGGER_GUI_TESTS = "1"
python -m unittest discover -s tests -v
```
