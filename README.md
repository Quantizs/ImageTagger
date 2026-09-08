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
| Kategória kézi beállítása | Objektum kijelölése, majd a kategórialista használata |
| Automatikus javaslat kézi megerősítése | **Rögzítés kéziként** |
| Kézi kategória feloldása | **Vissza automatikusra** |
| Régi annotációk kategorizálása | **Mappa automatikus kategorizálása** |

A téglalapból konvex, tetszőlegesen ferde négyszög készíthető. A sarkok nem keresztezhetik
egymást, és nem hagyhatják el a képet. A minimális objektumterület 1 eredeti képpixel²;
az új téglalap mindkét oldalát legalább 3 képernyőpixelnyire kell húzni.
Átfedésnél az objektumlista segít a takarásban lévő négyszög kijelölésében.
A részletes billentyűsúgó a jobb oldali **Súgó** fülön érhető el.

## Reklámfelületek kategóriái

Az újonnan rajzolt objektum automatikusan kategóriát kap az eredeti képpixelben mért
oldalaránya alapján. A felső/alsó élek átlaghosszát osztja a bal/jobb élek átlaghosszával,
és a logaritmikus távolság szerint legközelebbi típust választja. Ugyanezt a szabályt
használja az annotátor, az utólagos kategorizáló és a még kategória nélküli objektumok exportja.

| Mentett kategória | Névleges méret / exportarány (szélesség : magasság) |
| --- | --- |
| `BKV_álló` | 70 × 100 cm → 0,7000:1 |
| `Citylight` | 118,5 × 175 cm → 0,6771:1 |
| `Óriásplakát` | 504 × 238 cm → 2,1176:1 |
| `Kandeláber` | 100 × 140 cm → 0,7143:1 |
| `Reklámháló` | Változó méret; kiinduló exportarány 2:1 |
| `Tetőreklám` | Változó méret; kiinduló exportarány 3:1 |
| `Korlátreklám` | 133 × 63 cm → 2,1111:1 |

A névleges méretek a megadott kategóriákhoz tartozó referenciaértékek, nem a fotóból mért fizikai méretek.
A három álló típus, illetve az óriásplakát és a korlátreklám aránya nagyon közeli:
**pusztán az oldalarányból nem lehet megbízhatóan megkülönböztetni őket**. Az automatikus
kategória ezért javaslat; perspektíva vagy pontatlan sarokpozíció is megváltoztathatja.

- Kijelölés után a jobb oldali listából válassz kategóriát. A választás rögtön mentődik,
  és **kézi** értékké válik. Az automatikus javaslatot változtatás nélkül a
  **Rögzítés kéziként** gombbal lehet megerősíteni.
- Automatikus módban a geometria módosítása frissíti a javaslatot. A **kézi** kategóriát
  sarokhúzás, mozgatás és a teljes mappás újrakategorizálás sem írja felül.
- A **Vissza automatikusra** gomb tudatosan feloldja a kézi értéket, és új javaslatot számol.
- A kategóriaváltás és az automatikus módra visszatérés is visszavonható/újraalkalmazható.
  Törléskor és átrendezéskor a kategória a saját poligonjával együtt mozog.

### Régebbi annotációk utólagos kategorizálása

Az annotátor **Mappa automatikus kategorizálása** gombja a megnyitott mappában frissíti
a kategória nélküli és az automatikus objektumokat; a kézi értékeket megőrzi.
Ugyanez külön, ablak nélküli scriptből is futtatható:

```powershell
python categorize_annotations.py "C:\Projects\ImageTagger\budapest_kozut"
```

Fájlmódosítás nélküli előzetes összesítés:

```powershell
python categorize_annotations.py "C:\Projects\ImageTagger\budapest_kozut" --dry-run
```

A script jelzi a módosított objektumok és képek, a megőrzött kézi kategóriák és a hibák számát.
Újrafuttatható: a változatlan címkéket nem írja újra. Hibás annotációt megőriz és kihagy.
Mentéskor frissíti a statisztikát is. Az első kategóriás felülírás előtt az eredeti TXT
bájtpontos másolata az `annotations/backups/<képfájlnév>.txt.before_categories.bak` fájlba
kerül; egy meglévő biztonsági másolatot nem cserél le.
A külön scriptet akkor futtasd, amikor az adott mappa nincs megnyitva az annotátorban;
nyitott alkalmazásból a beépített gombot használd.

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
Egy objektum egy sor. Az első **8 szám** a sarokkoordinátáké; kategorizált objektumnál
ezeket a kategórianév és az eredet (`auto` vagy `manual`) követi. A fájl UTF-8 kódolású,
fejléc és numerikus osztályazonosító nélkül:

```text
tl_x tl_y tr_x tr_y br_x br_y bl_x bl_y kategória eredet
```

Példa:

```text
0.1 0.2 0.6 0.15 0.65 0.7 0.12 0.75 Óriásplakát manual
```

A régi, csak 8 koordinátából álló sorok továbbra is olvashatók, akár az új sorokkal
egy fájlban is. Az érintetlen régi sorok megmaradnak; kategorizáláskor kapják meg a két
új mezőt. A geometria és a kategória egyetlen atomi fájlmentéssel kerül lemezre.
Más feldolgozó scriptben az első 8 mező a geometria, az opcionális 9–10. mező a kategória.

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
  kategóriánkénti darabszám (`objects_per_category`), kategória nélküli és kézzel kategorizált
  objektumok száma, hibás képek/annotációk listája és időbélyeg.
- `statistics_per_image.csv`: képenként a méret, darabszám, átlagos és összes objektumterület,
  valamint az esetleges hiba. Táblázatkezelőben is megnyitható.

A területet a négyszög tényleges sarkaiból a shoelace-képlettel számolja, eredeti
pixelméretre átszámítva. Az átfedő objektumokat külön számolja, területeik összeadódnak.
A hibás annotációjú képek is beleszámítanak az összes képbe, de objektumaik ismeretlenek és
kimaradnak az objektumszámból; olvashatatlan kép esetén a betölthető objektumokat számolja,
területüket kihagyja. A hibaszámláló és az `objects_with_measurable_area` mező ezt jelzi.
Objektumok hiányában az átlagok nullák. Váratlan leállás után az annotációk az utolsó
automatikus mentésig megmaradnak; a statisztika a következő mentéskor frissül.

## Háromszínű keretek és normalizált táblák exportálása

A külön exportáló script csak a legalább egy poligonnal rendelkező képekről készít
rajzolt másolatot. A kép mellett számozott oldalsávban mutatja a reklámtáblák
perspektívakorrekcióval szembeforgatott, egységes méretű nézeteit.
Az eredeti képeket és az annotációkat nem módosítja.

Az export alapértelmezés szerint **Ultralytics YOLO11l** ember- és járműfelismerést is futtat.
Ehhez a külön exportfüggőségek szükségesek. Windows alatt egy helyi környezetben telepíthetők:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-export.txt
.\export_images.cmd budapest_kozut
```

Az `export_images.cmd` automatikusan a projekt `.venv` környezetét használja, ha az létezik.
Aktivált környezetben vagy az exportfüggőségekkel rendelkező Pythonból közvetlenül is indítható:

```powershell
python export_polygons.py "C:\Projects\ImageTagger\budapest_kozut"
```

Alapértelmezett kimenet: a képmappa `output` almappája. Másik mappa, eltérő
vonalvastagság és a kivágások magassága is megadható:

```powershell
python export_polygons.py "C:\Projects\ImageTagger\budapest_kozut" --output "C:\Projects\ImageTagger\rajzolt_kepek"
python export_polygons.py "C:\Projects\ImageTagger\budapest_kozut" --line-ratio 0.002
python export_polygons.py "C:\Projects\ImageTagger\budapest_kozut" --crop-height 480
```

- Minden poligonon egyszerre **belül kék, középen piros, kívül zöld** keret látszik.
  A három sáv az annotáció határától kifelé épül fel, az objektum belsejét nem tölti ki.
- **Egy színsáv** vastagsága a rövidebb képoldal **0,3%-a**, egész pixelre kerekítve,
  minimum 1 pixel. Például 1920×1080 esetén színenként 3 pixel, összesen 9 pixel.
  A `--line-ratio 0.002` színenként vékonyabb, 0,2%-os vonalat jelent.
- A képen és az oldalsávon egyező számok kapcsolják össze az objektumokat.
  A számozás a TXT-fájl sorainak sorrendjét követi, képenként 1-től indul.
  A script a tábla felett, alatt és mellett több helyet vizsgál, figyelembe véve az összes
  többi poligont és a már elhelyezett számokat. A legkisebb takarású, közeli helyet
  választja, és összekötő vonalat húz a táblához. Nagyon zsúfolt képen nem garantálható
  teljesen takarásmentes számozás; a kép körüli margó is helyet biztosít a jelöléseknek.
- Az oldalsáv a **mentett kategóriát** és annak fent megadott oldalarányát használja,
  akkor is, ha a fotón látható geometria más típust sugallna. A kártyán megjelenik a
  kategórianév, a névleges méret vagy kiinduló arány, valamint a kézi/automatikus eredet.
  Régi, kategória nélküli annotációnál az export idejére automatikus javaslat készül;
  az export a TXT-be nem írja vissza ezt a javaslatot.
- A négy sarokból projektív transzformáció készül: TL/TR/BR/BL a kivágás megfelelő
  sarkaiba kerül. A kivágás az eredeti, feliratok és keretek nélküli képből származik.
- A kivágások alapértelmezés szerint **320 pixel magasak**: Kandelábernél 229 × 320,
  Óriásplakátnál 678 × 320, Tetőreklámnál 960 × 320 pixel körüli méret adódik. A `--crop-height` 120–1600 pixel
  között állítható. A kisebb részleteket felnagyítja; az interpoláció nem állítja vissza
  a forrásképen hiányzó részleteket. A már nagyobb táblákat az egységes méretre kicsinyíti.
- A kártyák közös rácson, azonos kivágásmagassággal jelennek meg. Minden kategória a
  saját oldalarányához szükséges számú oszlopot foglalja el, a széles tetőreklám is elfér.
  Az oszlopszám a táblák számához és a kép méretéhez igazodik,
  sok tábla esetén több oszlop/sor készül, egyik kivágást sem hagyja el.
- A bal oldali fotó az eredeti felbontásában, az annotátor pixelirányában marad;
  az oldalsáv és a margók miatt a **teljes exportkép nagyobb lesz**.
  Minden másolat veszteségmentes PNG: például `foto.jpg` → `output/foto.jpg.png`.
  Az eredeti teljes fájlnév használata kizárja a különböző kiterjesztések névütközését.
- Az üres vagy hiányzó annotációjú képeket kihagyja. Hibás fájl esetén jelzi a hibát,
  a többi képet feldolgozza, és nem nulla kilépési kódot ad.
- Az output mappa legyen üres vagy egy korábbi, ugyanebből a képmappából készült export mappája.
  Újrafuttatáskor frissíti a másolatokat, és eltávolítja azokat a korábbi exportképeket,
  amelyekhez már nincs poligon. A saját fájljait a `.polygon_export.json` tartja nyilván;
  ezt hagyd a mappában. Idegen fájlokat tartalmazó output mappát nem módosít.
- Ugyanazokat a támogatott képformátumokat és az `annotations/<teljes képfájlnév>.txt`
  fájlokat használja, mint az annotátor. Almappákat nem jár be, többképes fájlból az első képet exportálja.

A korábbi piros keretes exportok ugyanazzal a paranccsal újragenerálhatók az új megjelenéssel.
Detektálás nélkül, a korábbi működéshez csak a Pillow szükséges:

```powershell
python export_polygons.py budapest_kozut --no-detection
```

### Emberek és járművek felismerése

- Az alapmodell a hivatalos **`yolo11l.pt`** detektor, amely az első futtatáskor a
  `models` mappába töltődik le. Utána helyből tölti be, futtatásonként egyszer;
  a képeket egyenként dolgozza fel. A felismerés helyben történik.
  Modellleírás: [Ultralytics YOLO11](https://docs.ultralytics.com/models/yolo11/).
- **Piros kör + fehér sorszám** jelöli a `person` találatokat.
  **Kék kör + fehér sorszám** jelöli a járműveket: `bicycle`, `car`, `motorcycle`,
  `bus`, `train`, `truck` (kerékpár, autó, motor, busz, vonat, teherautó).
  Ezek a [COCO osztálynevek](https://github.com/ultralytics/ultralytics/blob/main/ultralytics/cfg/datasets/coco.yaml)
  szerinti csoportok; repülőgép és hajó nem tartozik a járműszámlálóba.
- A kör a detektált bounding box **középpontjára** kerül. A sugár a rövidebb képoldal
  1,4%-a, minimum 12, maximum 40 pixel; például 1920×1080 képnél 15 pixel.
  A kör mérete nem követi a bounding box méretét. A kontrasztos fehér perem és a
  körhöz méretezett félkövér szám az olvashatóságot segíti. Sűrű találatok körei átfedhetnek.
- A számozás **képenként és csoportonként 1-től indul**, fentről lefelé, balról jobbra.
  A reklámtáblák külön, a megszokott sötét négyszögben számozódnak.
- Az oldalsáv tetején nagy **PEOPLE** és **VEHICLE** számláló mutatja az adott képen
  detektált darabszámot. Nulla találat esetén is megjelenik a 0.
- A felismerés a mappa **minden beolvasható képén** lefut, üres vagy hiányzó annotáció
  esetén is. A korábbi exportszűrés megmarad: **csak a reklámpoligonnal rendelkező képekből
  készül outputkép**. A futás végi terminálösszesítés az összes feldolgozott képre vonatkozik;
  ez több képen ugyanazt a személyt/járművet többször is tartalmazhatja, nem követés.
- A reklámkivágások a tiszta képből készülnek; az új körök és sorszámok nem kerülnek rájuk.
  Az annotációs TXT-k és az annotátor statisztikái nem változnak a detektálás miatt.
- Modellbetöltési vagy felismerési hiba esetén a futás hibával leáll; nem tüntet fel
  félrevezető nulla darabszámot. A korábbi exportokat ilyen hiba miatt nem törli.
- A számok modellbecslések: távoli, takart objektumok kimaradhatnak, téves találatok is
  előfordulhatnak, például plakáton szereplő alakoknál. Képenként legfeljebb 1000 találatot kér a modelltől.

Beállítások példákkal:

```powershell
.\export_images.cmd budapest_kozut --confidence 0.35 --imgsz 1280
.\export_images.cmd budapest_kozut --device cpu
.\export_images.cmd budapest_kozut --device 0
.\export_images.cmd budapest_kozut --weights "C:\modellek\yolo11l.pt"
```

A `--confidence` alapértéke 0,25; emelése kevesebb, megbízhatóbbnak ítélt találatot hagy meg.
A `--imgsz` alapértéke 1280; a kisebb, például 640-es érték gyorsabb lehet, de az apró
objektumok felismerése romolhat. A `--device cpu` processzort, a `--device 0` az első,
PyTorch által támogatott CUDA GPU-t választja; utóbbihoz megfelelő CUDA-s PyTorch-telepítés kell.
Alapból az Ultralytics választ az elérhető eszközökből. A csomag beállításai alapértelmezés
szerint a projekt `.ultralytics` mappájába kerülnek, a meglévő `YOLO_CONFIG_DIR` beállítást tiszteletben tartja.
Paraméterek: [Ultralytics Predict dokumentáció](https://docs.ultralytics.com/modes/predict/).

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
