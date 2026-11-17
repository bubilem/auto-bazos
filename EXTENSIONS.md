# AutoHledač (Add-Check) – Rozšíření a budoucí fáze (Fáze 2 a 3)

Tento dokument shromažďuje plánovaná rozšíření nad rámec základního MVP popsaného v [README.md](README.md). Cílem první fáze je mít co nejrychleji funkční, přenositelný nástroj s *Prompt-Bridge* napojením na webová LLM; níže uvedené funkce rozšiřují automatizaci, počet zdrojů a lokální AI zpracování.

---

## Obsah

1. [Další inzertní servery (Fáze 2–3)](#1-další-inzertní-servery-fáze-23)
2. [Automatická AI Pipeline (LM Studio / Ollama / Cloud API)](#2-automatická-ai-pipeline-lm-studio--ollama--cloud-api)
3. [Doporučené lokální modely pro LM Studio](#3-doporučené-lokální-modely-pro-lm-studio)
4. [Pokročilá deduplikace a sledování trhu](#4-pokročilá-deduplikace-a-sledování-trhu)
5. [Automatizace na pozadí a notifikace](#5-automatizace-na-pozadí-a-notifikace)

---

## 1. Další inzertní servery (Fáze 2–3)

> **Stav po ověření nad živými weby (listopad 2026):** aktivní je jen **Bazoš.cz**. **Sauto.cz** a **Sbazar.cz** v `robots.txt` zakazují všechny boty mimo vyhledávačů, takže je nelze automaticky stahovat. **TipCars.com** vrací našemu klientu výzvu Cloudflare (HTTP 403); ochranu neobcházíme a adaptér byl odstraněn. Priority v tabulce níže jsou proto jen původní odhady; sloupec *Stav* říká, jak to dopadlo.

Další izolované adaptéry se přidávají do `crawler/scrapers/` a registrují v `crawler/portals.py`:

| Server | Přínos | Technická náročnost & poznámky | Priorita |
| :--- | :--- | :--- | :--- |
| **Sbazar.cz** | Ekosystém Seznamu – mnoho soukromníků tam inzeruje paralelně s Bazošem (někdy s jinou cenou nebo dalšími fotkami). | **Nelze:** `robots.txt` zakazuje všechny boty mimo vyhledávačů. | **Vyřazeno** |
| **TipCars.com** | Silný český portál autobazarů a dealerů, často detailnější technické údaje a servisní historie. Dražší: u Peugeotu Expert byla nejlevnější nabídka 130 000 Kč. | Živý web odmítá náš klient (Cloudflare, HTTP 403). Neobcházíme; adaptér odstraněn. | **Zrušeno** |
| **Bazoš.sk / Autobazar.eu** | Rozšíření nabídky pro příhraniční nákupy na Slovensku u stejných koncernových vozů. | Nízká u Bazoš.sk (`robots.txt` stejný jako u `.cz`, téměř totožný layout), nutné přepočty měn EUR → CZK. Autobazar.eu zatím neprozkoumáno. | **Střední** (zatím nenapsáno) |
| **Cars.cz / Auto.cz** | Doplňkový český zdroj pro méně časté užitkové konfigurace. | Střední. | **Nízká–Střední** |
| **Mobile.de / AutoScout24** | Cenový benchmark západního trhu a zdroj pro dražší/novější auta na dovoz (u levných pracovních aut do 90 tis. Kč se dovoz z DE zpravidla nevyplatí). | Vysoká (silná anti-bot ochrana, vyžaduje `Playwright` nebo `curl_cffi` + překlad z DE). | **Volitelná** |
| **Facebook Marketplace** | Velké množství levných aut přímo od soukromníků. | **Velmi vysoká** (vyžaduje přihlášený účet, agresivní detekce botů, riziko blokace účtu). | **Specifická** *(viz níže)* |

> **Řešení pro Facebook Marketplace (a Sauto, Sbazar):** Místo automatického scrapingu přidat do webového UI jednoduchý **ruční import odkazu / bookmarklet** – uživatel najde auto v prohlížeči, zkopíruje text + fotky (nebo uloží stránku), a aplikace pro něj připraví stejný *Prompt-Bridge* a zařadí vůz do porovnání. Je to jediná poctivá cesta k portálům, které automatický přístup zakazují. *(Zatím nenapsáno.)*

---

## 2. Automatická AI Pipeline (LM Studio / Ollama / Cloud API)

Pokud v budoucnu nebudete chtít kopírovat prompty ručně do ChatGPT/Gemini, lze doplnit modul `crawler/ai.py`, který komunikuje přes jednotné **OpenAI-kompatibilní REST API** (`POST /v1/chat/completions`) pomocí čistých HTTP požadavků (`httpx` / `urllib`).

Tím pádem stačí v `config.json` přepínat pouze cílovou URL a název modelu:
- **LM Studio (lokálně):** `http://localhost:1234/v1/chat/completions`
- **Ollama (lokálně):** `http://localhost:11434/v1/chat/completions`
- **Cloud API (Gemini / OpenAI):** volitelně pouze pro finální Vision analýzu, pokud PC nemá dostatečnou GPU.

### Dvoufázová optimalizace výkonu a nákladů
1. **Fáze A (Rychlá textová filtrace):** Lehký textový model (1–2 s na inzerát) vytáhne z volného textu Bazoše datum STK, skryté vady, tažné zařízení a odliší soukromníka od překupníka.
2. **Fáze B (Hloubkový Vision posudek):** Spustí se pouze na **horních 10–20 % kandidátů**, kteří prošli Fází A. Místo 15 fotek najednou se pošle buď vygenerovaná koláž, nebo max. 4–5 klíčových snímků zmenšených na max. `1024 px` s nízkou teplotou (`temperature: 0.1`) a vynuceným JSON schématem (`Structured Outputs`).

### Co automatický LLM Use-Case Parser přidá navíc
- Uživatel napíše volným textem nový scénář (např. *„rodinné kombi na dlouhé trasy po dálnici, tiché, spolehlivý automat, bez panoramy“*) a LLM samo vygeneruje pravidla do `config.json` (preferované motorizace, vyloučené motory, váhy bodování).

---

## 3. Doporučené lokální modely pro LM Studio

Pro české inzeráty je klíčová kombinace: **dobrá čeština + podpora Vision (VLM) + spolehlivý JSON výstup**.

### Univerzální multimodální modely (Text + Fotky)
- **Qwen2.5-VL (7B)** / novější řada **Qwen3-VL (4B / 8B)** *(GGUF)*
  - *Silné stránky:* špičkové čtení textu z fotek (SPZ, nálepka STK, kilometry na budících), detailní popis karoserie, spolehlivý JSON.
  - *Nároky (Q4):* `7B/8B` vyžaduje cca **6–8 GB VRAM** (RTX 3060 12GB, RTX 4060/4070 nebo Mac s 16 GB+ RAM); `3B/4B` běží i na **4–5 GB VRAM**.
- **Gemma 3 (4B / 12B / 27B)** *(multimodální od Googlu)*
  - *Silné stránky:* nadprůměrná znalost češtiny a českého kontextu.
  - *Nároky (Q4):* `4B` (**4–5 GB VRAM**) výborná na texty; `12B` (**8–10 GB VRAM**) vyvážená volba pro text i fotky; `27B` (**18–20 GB VRAM**) pro detailní analýzu vad na snímcích.
- **MiniCPM-V (řada 2.6 / 4.x, ~8B)**
  - Specializovaný lehký model zaměřený na analýzu detailů na fotografiích (~**8 GB VRAM**).

### Rozdělená strategie (rychlost + kvalita)
- **Na text:** `Gemma 3 4B` nebo `Qwen3 8B` (rychlé procházení všech nových inzerátů).
- **Na fotky TOP kandidátů:** největší Vision model, který se vejde do paměti GPU/RAM, spouštěný dávkově (např. přes noc nebo na vyžádání).

---

## 4. Pokročilá deduplikace a sledování trhu

- **Percepční hashování obrázků (`pHash` přes `Pillow` + `imagehash`):**
  - Detekuje stejný vůz napříč portály (např. Bazoš vs. Sbazar vs. Sauto) i v případě, že portál fotku zmenší, přeuloží s jinou kompresí nebo přidá vodoznak.
  - Duplikáty se sloučí do jedné karty vozu se zobrazením rozdílů v ceně mezi portály.
- **Čtení SPZ / VIN z fotek:**
  - Pomocí OCR nebo Vision modelu lze z fotek vytáhnout čitelnou SPZ/VIN pro 100% přesnou deduplikaci a rychlé ověření historie (např. přes veřejný portál *Kontrola tachometru* MDČR).
- **Sledování životního cyklu a cenových trendů:**
  - Automatický výpočet **mediánové ceny trhu** v lokálně nasbírané databázi podle modelu, ročníku a nájezdu (označení mimořádně výhodných nabídek např. `-20 % pod mediánem`).
  - Detekce „ležáků“ (inzerát visí beze změny > 45 dní) vs. čerstvých slev.

---

## 5. Automatizace na pozadí a notifikace

- **Plánované spouštění:**
  - Windows *Plánovač úloh (Task Scheduler)* nebo Linux `cron` spouštějící `crawler/run.py --quiet` např. 2–3× denně.
- **Okamžité notifikace na „jednorožce“:**
  - Pokud nový inzerát dosáhne skóre např. `>= 85 %` (nízká cena + čerstvá STK + bez červených vlajek), crawler pošle zprávu s fotkou a odkazem přes jednoduchý webhook:
    - **Telegram Bot API** (zdarma, 10 řádků kódu přes HTTP POST),
    - **Discord Webhook**,
    - nebo **E-mail** přes SMTP.
- **Archivní úklid (Retence):**
  - Automatické promazání starých neaktivních inzerátů (např. zmizely před více než 30 dny a nejsou označené jako `Zajímavý`/`Kontaktováno`), aby složka `data/` nerostla donekonečna.
