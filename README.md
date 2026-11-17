# AutoHledač (Add-Check)

Lokální nástroj pro hledání levných ojetých dodávek (a podobných aut) na **Bazoš.cz**. Stáhne nabídky do složky na vašem disku, ohodnotí je jednoduchými pravidly (cena, STK, tažné, varovná slova) a ke každému autu vám připraví **prompt a očíslovanou fotokoláž**, které vložíte do webového ChatGPT / Gemini k předběžnému posudku. Běží jen u vás, bez databáze, bez cloudu a bez placených API.

> Nástroj slouží k **předvýběru** před telefonátem. Posudek z fotek od AI odhalí zjevná varování, ale **nenahrazuje prohlídku vozu**.

---

## Obsah

1. [Co to umí a co ne](#1-co-to-umí-a-co-ne)
2. [Instalace](#2-instalace)
3. [První spuštění](#3-první-spuštění)
4. [Jak aplikaci používat](#4-jak-aplikaci-používat)
5. [Příkazový řádek crawleru](#5-příkazový-řádek-crawleru)
6. [Nastavení (`config.json`, `profiles.json`, `taxonomy.json`)](#6-nastavení)
7. [Jak se počítá skóre](#7-jak-se-počítá-skóre)
8. [Kde jsou data](#8-kde-jsou-data)
9. [Zdroje dat a slušné chování](#9-zdroje-dat-a-slušné-chování)
10. [Známá omezení](#10-známá-omezení)
11. [Řešení problémů](#11-řešení-problémů)
12. [Vývoj a testy](#12-vývoj-a-testy)
13. [Struktura projektu](#13-struktura-projektu)

---

## 1. Co to umí a co ne

**Umí**
- Projít kategorie Bazoše (`/dodavka/`, `/peugeot/`, `/citroen/`, …), vybrat inzeráty s modely z `taxonomy.json` (Expert, Jumpy, Scudo, ProAce, Vivaro, Trafic, Primastar, Transporter, Transit Custom, Vito) a stáhnout jejich detail a fotky.
- Z volného textu vytáhnout **STK** (`STK do 08/2027`, `nová STK`, `bez STK`, `propadlá`…), **tažné**, výbavu (`L2H1`, výdřeva…), **varování** (`klepe`, `nouzový režim`, `k.o.`…), rok, nájezd a palivo.
- Spočítat **skóre 0–100** podle vašeho profilu (účel, cílová cena, klíčová slova).
- Zobrazit vše v přehledu s filtry a řazením, hlídat **změny cen** a **zmizelé inzeráty** (data i fotky zůstanou).
- Vytvořit **fotokoláž** (mřížka s čísly `[1]`…`[6]`) a **prompt** pro jedno auto nebo pro porovnání více aut, a uložit zpět odpověď AI.
- Pamatovat si vaše stavy (`Nový` / `Zajímavý` / `Kontaktováno` / `Zamítnuto`) a poznámky.

**Neumí (zatím)**
- Jiné portály než Bazoš.cz – viz [kapitola 9](#9-zdroje-dat-a-slušné-chování).
- Filtrovat podle roku, nájezdu, paliva nebo vzdálenosti. Nájezd a rok se zobrazí, ale **neovlivňují skóre**.
- Hledat podle volného textu účelu – účel je jen text, který se vkládá do promptu.
- Automatickou analýzu AI (vždy vkládáte ručně do webového chatu).

---

## 2. Instalace

### Požadavky
- **Python 3.11 nebo novější** (vyvíjeno a testováno na 3.13). Na Windows ho stáhnete z python.org a při instalaci zaškrtněte *Add python.exe to PATH*.
- **Připojení k internetu** (při instalaci závislostí a při stahování nabídek).
- Běžný prohlížeč. Nic dalšího (žádný Node.js, žádná databáze).

### Windows
1. Zkopírujte celou složku projektu kamkoli (i na USB disk).
2. Dvakrát klikněte na **`start.bat`**.

Při prvním spuštění skript sám vytvoří složku `.venv`, nainstaluje tři knihovny z `requirements.txt` (`httpx`, `beautifulsoup4`, `pillow`), spustí server a otevře prohlížeč na <http://127.0.0.1:8080/>. Další spuštění jsou okamžitá.

### Linux / macOS
```bash
sh start.sh
```
*(Skript je napsaný stejně jako `start.bat`, ale na Linuxu ani macOS jsem ho nezkoušel.)*

### Ruční instalace (kdyby skript selhal)
```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt     # Linux/macOS: .venv/bin/python
.venv/Scripts/python server.py --open
```

Ukončení: v okně serveru **Ctrl+C**. Server při tom ukončí i rozběhnuté stahování (zkoušeno jen v kódu, ne za běhu). Kdyby stahování po zavření okna běželo dál, ukončete proces `python` ve Správci úloh.

---

## 3. První spuštění

Po instalaci je aplikace **prázdná** – žádné nabídky ještě nejsou stažené.

1. Otevřete <http://127.0.0.1:8080/> (otevře se samo).
2. Klikněte na **Stáhnout nové nabídky**. Stahování běží na pozadí, stav vidíte nahoře.
   Konkrétní inzerát přidáte vložením jeho adresy (`auto.bazos.cz/inzerat/…`) do pole **URL inzerátu** a tlačítkem **Přidat inzerát**. Filtr modelu ani cenový strop se na něj neuplatní, v seznamu se objeví vedle automaticky stažených (v souboru je značka `manual`).
3. Po dokončení se přehled sám obnoví.

**Jak dlouho to trvá?** Crawler záměrně čeká 2–5 s mezi stránkami a 0,4–1 s mezi fotkami, aby Bazoš nezatěžoval. Orientačně:
- výpisy kategorií: asi 40 stránek × 3,5 s ≈ 2–3 minuty,
- každý **nový** vhodný inzerát (detail + až 12 fotek + koláže) ≈ 10–15 s.

První běh s desítkami inzerátů tak trvá **řádově 5–15 minut**. Další běhy jsou rychlé, protože už viděné inzeráty se znovu nestahují. Jeden inzerát zabere asi **3 MB** (fotky v plné velikosti).

Chcete-li první běh omezit, spusťte ho z příkazového řádku s `--limit` (viz [kapitola 5](#5-příkazový-řádek-crawleru)); zbylé kandidáty crawler doplní při příštím běhu.

---

## 4. Jak aplikaci používat

### Přehled
- **Profil** (vlevo nahoře) určuje účel, cílovou cenu a podle něj se počítá skóre. Pod lištou rozkliknete **Účel užití**.
- **Filtry:** fulltext (titulek + popis), cena od–do, minimální rok, model, portál, *Jen s STK*, *Skrýt zamítnuté*, *Zobrazit neaktivní*.
- **Řazení:** základní skóre, cena, nejnovější, největší sleva.
- **Karta auta:** fotka, titulek, cena (při poklesu přeškrtnutá původní), lokalita, rok, nájezd, štítky (`STK`, `Tažné`, `Sleva`, `Neaktivní`) a skóre vpravo. Tlačítka: **Zajímavý**, **Skrýt**, **Otevřít inzerát** (původní inzerát na Bazoši) a zaškrtávátko **Porovnat**.
- Rok a nájezd mají u některých inzerátů otazník – Bazoš je nemá jako samostatné pole a v textu je prodejce nemusí uvést.

> Inzeráty, které obsahují některé z **vyloučených slov** profilu (`havarované`, `nepojízdné`, `na náhradní díly`, `bez TP`, `k.o.`), se standardně skrývají pod volbou *Skrýt zamítnuté*. Nic se nemaže – po vypnutí volby je uvidíte.

### Detail auta (klik na kartu)
Fotogalerie, parametry, historie ceny, nalezená klíčová slova, celý text inzerátu a **fotokoláže**. Dole je **Prompt-Bridge**, stav a poznámky.

### Posudek z fotek přes webovou AI (Prompt-Bridge)
1. V detailu auta klikněte na **Zkopírovat prompt pro Gemini / ChatGPT**. Do schránky se uloží zadání: účel nákupu, parametry, historie ceny, text inzerátu, kontrolní seznam pro fotky (koroze prahů a lemů, spáry, podlaha nákladového prostoru, opotřebení interiéru vs. nájezd, kontrolky, pneumatiky) a žádost o otázky na prodejce a o závěrečný JSON blok.
2. Otevřete chat (ChatGPT, Gemini, Google AI Mode) a prompt vložte.
3. Přiložte **fotokoláž**. Je to soubor `data/listings/<id>/collage_1.jpg` (případně `collage_2.jpg`) a zobrazuje se i v detailu. Číslo `[3]` na koláži odpovídá souboru `images/03.jpg`, takže AI se může odvolat na „fotka [3]“ a vy ji najdete.
4. Odpověď AI zkopírujte, vložte do pole **Vložit odpověď AI** v detailu a klikněte na **Uložit analýzu**. Aplikace z ní vytáhne JSON blok (verdikt, skóre, plusy, red flags, checklist na telefonát) a zobrazí ho u auta. Když JSON blok chybí, uloží se aspoň celý text.

**Porovnání více aut:** zaškrtněte u karet **Porovnat** (alespoň 2) a nahoře klikněte na **Porovnat zaškrtnuté v AI**. Zkopíruje se souhrnný prompt pro určení pořadí. Fotokoláže jednotlivých aut přikládáte do chatu ručně.

Když prohlížeč nepovolí kopírování do schránky, zobrazí se prompt v okně ke zkopírování ručně.

### Stav a poznámky
V detailu vyberete stav (`Nový`, `Zajímavý`, `Kontaktováno`, `Zamítnuto`) a napíšete poznámky (třeba „volat v úterý po 16:00“). Ukládá se to hned do `data/user_state.json` a stahování to **nikdy nepřepíše**.

---

## 5. Příkazový řádek crawleru

Tlačítko v UI spouští stejný příkaz bez parametrů. Z příkazového řádku (ve složce projektu, s Pythonem z `.venv`):

```bash
.venv/Scripts/python -m crawler.run [volby]          # Linux/macOS: .venv/bin/python
```

| Volba | Význam |
| :--- | :--- |
| `--dry-run` | Projde výpisy a vypíše kandidáty. Nestahuje detaily ani fotky a nic nezapisuje. |
| `--limit N` | Stáhne detail nejvýše N **nových** inzerátů; zbytek počká do příštího běhu. |
| `--max-pages N` | Přepíše počet stránek na kategorii z `config.json`. |
| `--add-url URL` | Přidá jeden inzerát podle adresy (bez procházení kategorií a bez filtru modelu a ceny). |
| `--slug S` | Jen jedna kategorie, např. `--slug dodavka`. |
| `--portal bazos` | Jen vybraný portál (dnes jediný aktivní). |
| `--stale-limit N` | Nejvýše N neviděných inzerátů znovu ověřit (výchozí 10). |
| `--data-dir CESTA` | Použít jinou složku než `data/` (např. na zkoušku). |
| `--reset-state` | Zapomenout seznam už viděných ID; vše se znovu posoudí. Stažené inzeráty zůstanou. |

Návratový kód **0** = vše v pořádku, **2** = potíže (portál odmítl přístup, změnil se vzhled stránek nebo spadla síť v některé kategorii). Podrobnosti jsou ve výpisu.

Příklady:
```bash
.venv/Scripts/python -m crawler.run --dry-run --slug dodavka --max-pages 2
.venv/Scripts/python -m crawler.run --limit 10
```

### Jak crawler pracuje
- Prochází kategorie od nejnovějších. Jakmile narazí na stránku bez novinek, další stránky té kategorie přeskočí.
- Model určuje **jen z titulku** a cenu kontroluje už ve výpisu, takže detail se stahuje jen u vhodných nabídek.
- Při opakovaném běhu aktualizuje cenu a `last_seen`. Inzeráty, které nevidí, občas znovu ověří; smazaný inzerát označí `inactive` (data i fotky zůstanou).
- Po každém běhu přepočítá skóre všech uložených inzerátů a přepíše `data/index.json`.

---

## 6. Nastavení

### `config.json`

| Klíč | Význam |
| :--- | :--- |
| `server.host`, `server.port` | Adresa serveru (výchozí `127.0.0.1:8080`). Při obsazeném portu změňte `port`. Server přijímá jen požadavky na tuto adresu a na `localhost`. |
| `scraping.user_agent` | Identifikace crawleru. |
| `scraping.delay_seconds` | Pauza mezi stránkami `[min, max]` v sekundách (výchozí `[2, 5]`). **Nezkracujte.** |
| `scraping.image_delay_seconds` | Pauza mezi fotkami (výchozí `[0.4, 1.0]`). |
| `scraping.request_timeout_seconds` | Časový limit jednoho požadavku. |
| `scraping.max_images_per_listing` | Kolik fotek stáhnout k jednomu inzerátu (výchozí 12). |
| `scraping.collage_images` | Kolik fotek je v jedné koláži (výchozí 6; koláží je nejvýše 2). |
| `portals.bazos.enabled` | Zapnutí portálu. |
| `portals.bazos.categories` | Seznam `{ "slug": "...", "max_pages": N }`. Slug je část adresy `auto.bazos.cz/<slug>/`. Jedna stránka má 40 inzerátů. |

**Kategorie Bazoše:** `dodavka` (dodávky) a značkové kategorie. Stejný model může být v kategorii značky i v `dodavka`, proto se procházejí obě. Značkové kategorie jsou obrovské (tisíce inzerátů), a při `max_pages: 3` se projdou jen **nejnovější 120**. Starší shody v nich uniknou; hloubku zvyšte u kategorií, které vás zajímají (za cenu delšího běhu).

### Profil hledání (`profiles.json`)

Každý profil má:

| Klíč | Význam |
| :--- | :--- |
| `id`, `name` | Identifikátor a název v nabídce profilů. |
| `purpose` | **Lidský popis účelu.** Vkládá se do promptu pro AI. Čím konkrétnější, tím lepší posudek. |
| `equivalence_group` | Skupina modelů z `taxonomy.json`, které se hledají. |
| `reference_model` | Jen informativní (zatím se nepoužívá). |
| `params.price_target_czk` | Cílová cena. Do ní dostane nabídka plný počet bodů za cenu. |
| `params.price_max_czk` | Strop. Dražší inzeráty se **vůbec nestahují** (a mezi cílem a stropem bodů ubývá). |
| `exclude_keywords` | Slova, která inzerát vyřadí (označí `excluded`). |
| `positive_keywords` | Slova, za která jsou body. Slovo `stk` se započítá jen u platné STK. |
| `warning_keywords` | Slova, která odečítají body (spolu s vestavěnými varováními). |
| `score_weights` | Váhy složek skóre (`price`, `stk`, `keywords`, `presentation`). |

Slova se hledají bez ohledu na velikost písmen a diakritiku, tolerují české koncovky (`tažné` najde i `tažného`) a **nesmí být popřená** (`bez koroze` nebo `neklepe` se nepočítá jako varování).

**Skupiny modelů a kategorie:** tlačítko **Modely a kategorie** otevře editor skupin (`taxonomy.json`, jeden model na řádek ve tvaru `Značka | Model | alternativní zápisy | poznámka`) a seznamu kategorií Bazoše (`config.json`, slug a počet stránek). Skupinu, kterou používá nějaký profil, nejde smazat. Změny se projeví při dalším stahování a při běžícím stahování se ukládání odmítne.

**Nový profil:** tlačítko **Upravit profily** v horní liště otevře editor (název, účel, skupina modelů, ceny, klíčová slova, váhy skóre). Uložení zapíše `profiles.json` a na pozadí přepočítá skóre všech uložených inzerátů, nic se nestahuje znovu. Při běžícím stahování editor ukládání odmítne. Poslední profil nejde smazat. Které inzeráty se stahují, určuje skupina modelů a nejvyšší strop ceny napříč profily.

Parametry **rok, nájezd, palivo a vzdálenost** konfigurace zatím nezná (v dřívějších verzích byly v souboru jen naoko, odstranil jsem je).

### `taxonomy.json`
Skupiny zaměnitelných modelů: `{ "make", "model", "notes" }`. Model se hledá v titulku jako celé slovo. Pro jiný zápis přidejte `"match": ["proace", "pro ace"]`. `notes` jsou jen poznámky pro vás. Nový model přidáte jedním řádkem; značka musí mít odpovídající kategorii v `portals.bazos.categories`, jinak ho najdete jen v `dodavka`.

---

## 7. Jak se počítá skóre

Skóre 0–100 slouží jen k **předřazení**, ne jako verdikt.

| Složka | Váha | Pravidlo |
| :--- | :--- | :--- |
| **Cena** | 30 | Do cílové ceny plný počet bodů; mezi cílem a stropem klesá na 30 %; nad stropem 0. Bez ceny („dohodou“) 50 %. |
| **STK** | 30 | Platná ≥ 12 měsíců 100 %, 6–11 měs. 80 %, kratší 50 %; „platná STK“ bez data 65 %; nová/čerstvá STK 100 %; **neznámá 40 %** (nevíme ≠ špatná); bez STK / propadlá 0. |
| **Klíčová slova** | 25 | Podíl nalezených slov z `positive_keywords` (maximálně 4 stačí na plný počet). |
| **Prezentace** | 15 | ≥ 5 fotek (8 b.), 3–4 fotky (4 b.); popis ≥ 200 znaků (4 b.); uvedená lokalita (3 b.). |
| **Penalizace** | − | −8 bodů za každé varovné slovo. Výsledek se ořízne na 0–100. |

Vstupy jsou z **volného textu**, takže si nejsou jisté: rok a nájezd mají v datech značku důvěryhodnosti (`high` = vedle slova „r.v.“ / „najeto“, `low` = jen odhad).

---

## 8. Kde jsou data

Vše je ve složce `data/` (soubory, žádná databáze). Složka je mimo verzování (`.gitignore`).

```text
data/
├── index.json            přehled pro UI (přepisuje se po každém běhu)
├── user_state.json       VAŠE stavy, poznámky a uložené posudky AI
├── crawl_state.json      už viděná ID inzerátů (pro přírůstkové běhy)
└── listings/<portal>_<id>/
      ├── listing.json    detail, historie cen, skóre
      ├── collage_1.jpg   fotokoláž pro AI (collage_2.jpg při více než 6 fotkách)
      └── images/01.jpg … stažené fotky
```

- **Zálohujte `user_state.json`.** Je to jediný soubor, který nejde znovu stáhnout. Ostatní data crawler obnoví (kromě inzerátů, které mezitím z Bazoše zmizely).
- Inzerát, který zmizel z Bazoše, zůstane na disku jako `inactive`. Automatické mazání starých inzerátů zatím neexistuje. Chcete-li nějaký odstranit, smažte jeho složku `data/listings/<id>`; jeho ID zůstane v `crawl_state.json`, takže se příště nestáhne znovu.
- Fotky mohou obsahovat **registrační značky**. Zůstávají jen lokálně, nikam se neposílají (kromě toho, co sami vložíte do webového chatu).
- Telefonní čísla ani jména prodejců se **neukládají**.

### Formát souborů (pro vlastní skripty)

`index.json` – pole `listings` s položkami:
```json
{ "uid": "bazos_226472643", "portal": "bazos", "title": "…", "url": "https://auto.bazos.cz/inzerat/…",
  "status": "active", "price_czk": 85000, "price_prev_czk": null, "location": "Olomouc",
  "make": "Citroën", "model": "Jumpy", "year": 2011, "mileage_km": 190000, "fuel": "diesel",
  "stk_detected": null, "tow_bar": false, "first_seen": "2026-11-16T12:00:00Z", "last_seen": "…",
  "scores": { "dodavka_na_sut": 50 }, "excluded": {}, "tags": [], "thumb": "listings/…/images/01.jpg" }
```
`listing.json` obsahuje navíc `description`, `price_history` (`[{date, price_czk}]`), `images`, `collages`, `vehicle` (včetně `year_confidence`, `mileage_confidence`, `stk_status`) a `rule_scoring` (pro každý profil: `base_score`, `breakdown`, `positive_hits`, `warning_hits`, `excluded`).

`user_state.json` – klíčováno podle `uid`:
```json
{ "bazos_226472643": { "workflow_status": "shortlisted", "notes": "Volat v úterý", "hidden": false,
    "imported_ai_report": { "updated_at": "…", "raw_text": "…",
      "parsed": { "verdict": "…", "score": 87, "pluses": [], "red_flags": [], "call_checklist": [] } } } }
```

---

## 9. Zdroje dat a slušné chování

**Aktivní je jen Bazoš.cz.** Ostatní zkoušené portály jsem ověřil nad živými weby a nelze je (nebo nemá smysl) automaticky stahovat:

| Portál | Stav | Důvod |
| :--- | :--- | :--- |
| **Bazoš.cz** | **Funguje** | Procházení kategorií je v `robots.txt` povolené. |
| **Sauto.cz**, **Sbazar.cz** | Nelze | `robots.txt` zakazuje všechny boty mimo jmenovaných vyhledávačů (`User-agent: *` → `Disallow: /`). |
| **TipCars.com** | Zrušeno | Živý web našemu klientu vrací výzvu Cloudflare (HTTP 403), kterou neobcházíme. Adaptér byl odstraněn. |
| **Bazoš.sk** | Nenapsáno | `robots.txt` stejný jako u `.cz`; chybí adaptér a přepočet EUR → CZK. |

Pro Sauto a podobné weby zbývá jen **ruční postup**: najděte auto v prohlížeči sami a hodnoťte ho v AI ručně. Ruční import do aplikace zatím není.

### Co crawler dodržuje
- **`robots.txt`**: Bazoš zakazuje hledání přes parametry (`hledat=`, `cenaod=`, `cenado=`, `hlokalita=`, `humkreis`, `order=`) a stránky `ad-phone.php`. Crawler proto používá jen kategorie a zakázanou adresu nikdy nestáhne (kontrola je v kódu a v testech). Kvůli tomu se cena i model filtrují až u vás.
- **Prodlevy** 2–5 s mezi stránkami, 0,4–1 s mezi fotkami, přírůstkové běhy, žádné paralelní požadavky.
- **Odmítnutí přístupu** (HTTP 401/403/429): crawler to ohlásí (`BLOCKED`), na daný portál už nic neposílá a skončí s kódem 2. Ochranu nijak neobchází.
- **Osobní údaje:** telefon ani jméno prodejce se neparsují ani neukládají.
- **Osobní použití:** data a fotky slouží výhradně pro vaši potřebu při výběru vozu.

---

## 10. Známá omezení

- **Pokrytí:** značkové kategorie se procházejí jen do nastavené hloubky (výchozí 3 stránky, tedy nejnovějších 120 inzerátů). Starší nabídky v nich nenajdete. Zvyšujte `max_pages`, kde to potřebujete.
- **Párování podle titulku:** inzerát, který model v titulku neuvádí („Prodám dodávku“), se nechytí. Naopak občas projde nesouvisející inzerát (pneumatiky, díly) se jménem modelu v titulku; ceny a vyloučená slova většinu odfiltrují, zbytek uvidíte v přehledu.
- **Zkratky v textu:** „na ND“ (= na náhradní díly) pravidla nerozpoznají.
- **Cena:** některé inzeráty mají ceny v jiné měně nebo leasing, a pak nedává smysl.
- **Skóre** nezohledňuje nájezd ani stáří vozu (u vozu s 450 000 km může vyjít vysoko).
- **Bazoš může změnit vzhled stránek.** Crawler pak nenajde žádné inzeráty, napíše `WARNING … layout changed or blocked?` a skončí s kódem 2. Parsery jsou v `crawler/scrapers/bazos.py`; otestované jsou na uložených stránkách v `tests/fixtures/`.
- **Přenosnost:** složka se dá zkopírovat na jiný počítač, ale `.venv` je vázané na konkrétní instalaci Pythonu. Na novém stroji `.venv` smažte a spusťte `start.bat` znovu.
- **Linux/macOS:** `start.sh` jsem nevyzkoušel.
- **UI** jsem testoval v prohlížeči zabudovaném v nástroji (úzké okno) a na ukázkových i reálných datech. Vložení do skutečného ChatGPT/Gemini jsem neověřoval.
- Stahování z UI nelze zrušit tlačítkem; ukončíte ho zavřením serveru (**Ctrl+C**).

---

## 11. Řešení problémů

| Příznak | Co zkusit |
| :--- | :--- |
| `start.bat` hlásí chybu při přípravě prostředí | Je nainstalovaný Python 3.11+ a je v `PATH`? (`python --version` v příkazovém řádku.) Máte internet (stahují se knihovny)? Smažte složku `.venv` a zkuste znovu. |
| Port 8080 je obsazený | V `config.json` změňte `server.port` (např. na 8090) a otevřete novou adresu. |
| Přehled je prázdný | Zatím nejsou data: klikněte na **Stáhnout nové nabídky**. Pokud už data jsou, zkontrolujte filtry a volbu *Skrýt zamítnuté*. |
| Stahování skončí chybou (kód 2) | Přečtěte si poslední řádky výpisu v okně serveru nebo spusťte `python -m crawler.run --dry-run`. `BLOCKED` = Bazoš odmítl přístup (počkejte, zkuste později, **nezkracujte prodlevy**). `layout changed` = změnil se vzhled stránek, je potřeba upravit parser. |
| Chci vše stáhnout znovu | Smažte `data/crawl_state.json` (nebo spusťte s `--reset-state`). Už uložené inzeráty se nepřepíšou, jen se znovu posoudí. |
| Hlášení „Uložení se nepovedlo“ v UI | Běží server? Není složka `data/` jen pro čtení? |
| Stránka se načte, ale tlačítka nereagují | Zkuste Ctrl+F5. Server vás pustí jen na `127.0.0.1` nebo `localhost` a stejný port, ne přes jiný název počítače nebo IP adresu v síti. |

---

## 12. Vývoj a testy

```bash
.venv/Scripts/python -m unittest discover -s tests          # 91 testů, bez internetu, pár sekund
.venv/Scripts/python tools/make_fixtures.py                 # vygeneruje ukázková data pro vývoj UI (přepíše data/index.json!)
```

Testy pokrývají pravidla (čeština, negace, STK), koláž, parser Bazoše na uložených stránkách, robots.txt, celý tok crawleru proti falešnému serveru (přírůstkový běh, pokles ceny, zmizelý inzerát, výpadek sítě, blokace) a lokální server (path traversal, cizí `Origin` a `Host`). Testy se spouštějí z `.venv` (potřebují `httpx` a `beautifulsoup4`).

Fixtures v `tests/fixtures/` jsou skutečné stránky zbavené jmen a telefonů prodejců.
---

## 13. Struktura projektu

```text
add-check/
├── start.bat / start.sh        # spouštěč (vytvoří .venv, nainstaluje závislosti, spustí server)
├── requirements.txt            # httpx, beautifulsoup4, pillow
├── config.json                 # server, prodlevy, kategorie
├── profiles.json               # profily hledání (upravuje se v GUI)
├── taxonomy.json               # skupiny zaměnitelných modelů
├── server.py                   # lokální HTTP server (jen stdlib) + API pro stav a spuštění crawleru
├── crawler/                    # spouští se jako: python -m crawler.run
│   ├── run.py                  # stažení → pravidla → koláže → index.json
│   ├── rules.py                # extrakce STK/vad/roku/nájezdu + skóre
│   ├── collage.py              # očíslovaná mřížka fotek
│   ├── fetcher.py              # HTTP klient: robots.txt, prodlevy, opakování
│   ├── robots.py               # parser robots.txt se zástupnými znaky
│   ├── taxonomy.py             # párování modelů
│   ├── portals.py              # jednotné rozhraní portálů pro run.py
│   └── scrapers/
│       └── bazos.py            # Bazoš.cz
├── web/                        # čisté HTML + CSS + JS (index.html, style.css, app.js)
├── tests/                      # unittest + fixtures
├── tools/make_fixtures.py      # ukázková data pro vývoj UI
└── data/                       # stažená data a vaše stavy (vzniká sám)
```

Další možná rozšíření (lokální AI, deduplikace, notifikace…) jsou v [EXTENSIONS.md](EXTENSIONS.md); část z nich se po průzkumu portálů ukázala jako neproveditelná.
