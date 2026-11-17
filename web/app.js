"use strict";

const $ = (id) => document.getElementById(id);
const WORKFLOW = { new: "Nový", shortlisted: "Zajímavý", contacted: "Kontaktováno", rejected: "Zamítnuto" };
const PORTALS = { bazos: "Bazoš", sauto: "Sauto" };

const app = {
  index: { profiles: [], listings: [] },
  user: {},
  profileId: null,
  selected: new Set(),
  details: new Map(),
  openUid: null,
};

// ---------- helpers ----------
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : "#");
const fmtPrice = (n) => (n == null ? "cena neuvedena" : n.toLocaleString("cs-CZ") + " Kč");
const fmtKm = (n) => (n == null ? "?" : n.toLocaleString("cs-CZ") + " km");
const fmtDate = (s) => (s ? new Date(s).toLocaleDateString("cs-CZ") : "?");
const profile = () => app.index.profiles.find((p) => p.id === app.profileId) || {};
const scoreOf = (l) => l.scores?.[app.profileId] ?? 0;
const userOf = (uid) => app.user[uid] || {};
const dataUrl = (uid, rel) => `/data/listings/${encodeURIComponent(uid)}/${rel.split("/").map(encodeURIComponent).join("/")}`;

function say(msg) {
  $("status").textContent = msg;
  clearTimeout(say.t);
  say.t = setTimeout(() => ($("status").textContent = ""), 6000);
}

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok && r.status !== 501 && r.status !== 409 && r.status !== 400 && r.status !== 202) throw new Error(`${path}: ${r.status}`);
  return r;
}

async function patchState(uid, patch) {
  app.user[uid] = { ...userOf(uid), ...patch };
  try {
    const r = await api("/api/state", { method: "POST", body: JSON.stringify({ uid, patch }) });
    app.user[uid] = await r.json();
  } catch (e) {
    say("Uložení se nepovedlo: " + e.message);
  }
}

// ---------- loading ----------
async function load() {
  try {
    const [idx, st] = await Promise.all([
      fetch("/data/index.json", { cache: "no-store" }).then((r) => (r.ok ? r.json() : { profiles: [], listings: [] })),
      fetch("/api/state").then((r) => r.json()).catch(() => ({})),
    ]);
    app.index = idx;
    app.user = st;
  } catch (e) {
    say("Načtení dat selhalo: " + e.message);
  }
  if (!app.index.profiles.some((p) => p.id === app.profileId)) app.profileId = app.index.profiles[0]?.id ?? null;
  $("profile").innerHTML = app.index.profiles.map((p) => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join("");
  $("profile").value = app.profileId;
  const models = [...new Set(app.index.listings.map((l) => `${l.make} ${l.model}`))].sort();
  const cur = $("f-model").value;
  $("f-model").innerHTML = `<option value="">vše</option>` + models.map((m) => `<option>${esc(m)}</option>`).join("");
  $("f-model").value = models.includes(cur) ? cur : "";
  $("purpose").textContent = profile().purpose || "";
  render();
}

// ---------- filtering + cards ----------
function filtered() {
  const q = $("f-text").value.trim().toLowerCase();
  const pmin = parseInt($("f-pmin").value, 10), pmax = parseInt($("f-pmax").value, 10), ymin = parseInt($("f-year").value, 10);
  const model = $("f-model").value;
  const onlyStk = $("f-stk").checked, hideRej = $("f-hidden").checked, showInactive = $("f-inactive").checked;

  const list = app.index.listings.filter((l) => {
    const u = userOf(l.uid);
    if (q && !(l.search_text || l.title.toLowerCase()).includes(q)) return false;
    if (!isNaN(pmin) && (l.price_czk == null || l.price_czk < pmin)) return false;
    if (!isNaN(pmax) && (l.price_czk == null || l.price_czk > pmax)) return false;
    if (!isNaN(ymin) && (l.year == null || l.year < ymin)) return false;
    if (model && `${l.make} ${l.model}` !== model) return false;
    if (onlyStk && !l.stk_detected) return false;
    if (hideRej && (u.hidden || u.workflow_status === "rejected" || l.excluded?.[app.profileId])) return false;
    if (!showInactive && l.status !== "active") return false;
    return true;
  });

  const discount = (l) => (l.price_prev_czk && l.price_czk != null ? l.price_prev_czk - l.price_czk : 0);
  const sorters = {
    score: (a, b) => scoreOf(b) - scoreOf(a),
    price: (a, b) => (a.price_czk ?? Infinity) - (b.price_czk ?? Infinity),
    newest: (a, b) => String(b.first_seen).localeCompare(String(a.first_seen)),
    discount: (a, b) => discount(b) - discount(a),
    ai: (a, b) => (userOf(b.uid).ai_compare?.score ?? -1) - (userOf(a.uid).ai_compare?.score ?? -1) || scoreOf(b) - scoreOf(a),
  };
  return list.sort(sorters[$("f-sort").value]);
}

function card(l) {
  const u = userOf(l.uid);
  const drop = l.price_prev_czk && l.price_czk != null && l.price_czk < l.price_prev_czk;
  const tagCls = (t) => ({ STK: "good", "Tažné": "good", Sleva: "good", "Neaktivní": "bad" }[t] || "");
  const wf = u.workflow_status && u.workflow_status !== "new" ? `<span class="tag">${esc(WORKFLOW[u.workflow_status])}</span>` : "";
  return `<article class="card ${l.status !== "active" ? "inactive" : ""} ${u.workflow_status === "shortlisted" ? "shortlisted" : ""}" data-uid="${esc(l.uid)}">
    <img class="thumb" data-act="open" loading="lazy" alt="" src="/data/${esc(l.thumb || "")}" onerror="this.removeAttribute('src')">
    <div class="card-body">
      <h2 class="card-title" data-act="open">${esc(l.title)}</h2>
      <div class="price">${fmtPrice(l.price_czk)}${drop ? `<span class="old">${fmtPrice(l.price_prev_czk)}</span><span class="drop">−${(l.price_prev_czk - l.price_czk).toLocaleString("cs-CZ")}</span>` : ""}</div>
      <div class="meta">${esc(l.location || "?")} · ${l.year ?? "?"} · ${fmtKm(l.mileage_km)} · ${esc(PORTALS[l.portal] || l.portal)}</div>
      <div class="row"><div class="tags">${wf}${(l.tags || []).map((t) => `<span class="tag ${tagCls(t)}">${esc(t)}</span>`).join("")}</div>
        <span>${u.ai_compare ? `<span class="tag good" title="${esc(u.ai_compare.reason || "AI skóre ze srovnání")}">AI ${esc(u.ai_compare.score)}</span> ` : ""}<span class="score" title="Základní skóre">${scoreOf(l)}</span></span></div>
      <div class="actions">
        <label class="inline"><input type="checkbox" data-act="select" ${app.selected.has(l.uid) ? "checked" : ""}> Porovnat</label>
        <button type="button" data-act="star" class="${u.workflow_status === "shortlisted" ? "on" : ""}">Zajímavý</button>
        <button type="button" data-act="hide">${u.hidden ? "Zobrazit" : "Skrýt"}</button>
        <a class="btn" href="${esc(safeUrl(l.url))}" target="_blank" rel="noopener noreferrer">Otevřít inzerát</a>
      </div>
    </div>
  </article>`;
}

function render() {
  const list = filtered();
  $("count").textContent = `${list.length} z ${app.index.listings.length}`;
  const emptyMsg = app.index.listings.length
    ? "Žádné nabídky neodpovídají filtru."
    : "Zatím tu nejsou žádná data. Klikněte na „Stáhnout nové nabídky“ (první běh trvá několik minut).";
  $("cards").innerHTML = list.length ? list.map(card).join("") : `<p class="empty">${emptyMsg}</p>`;
  const n = app.selected.size;
  $("compare-count").textContent = n;
  $("compare").disabled = n < 2;
}

// ---------- prompt bridge ----------
const PHOTO_CHECKLIST = [
  "koroze prahů, podběhů, lemů a spodních hran dveří",
  "spáry karoserie a známky havárie či lakování",
  "stav nákladového prostoru a podlahy",
  "opotřebení volantu, řadicí páky a sedačky vs. udávaný nájezd",
  "kontrolky na palubní desce (a údaj o nájezdu, je-li vidět)",
  "stav pneumatik a kol",
];

const JSON_SCHEMA_TEXT = `{
  "verdict": "jedna věta závěru",
  "score": 0-100,
  "pluses": ["..."],
  "red_flags": ["... (odkazuj na čísla fotek, např. [3])"],
  "call_checklist": ["otázky pro prodejce / co ověřit při telefonátu"],
  "seller": "soukromník | překupník | autobazar | nejasné – stručně podle čeho; reputace: zjištěno/nezjištěno"
}`;

const SELLER_CUES = [
  [/\bdph\b/, "zmínka o DPH"],
  [/leasing|splatk|financov|na splatky|uver/, "leasing / splátky / financování"],
  [/vykup|protiucet|vymena|inzerc/, "výkup / protiúčet / výměna"],
  [/zaruk|ze zaruky|zarucni/, "záruka"],
  [/autobazar|bazar|prodejn|showroom|u nas|na pobocce|provozovn/, "jazyk autobazaru / prodejny"],
  [/\bico\b|s\.r\.o|\bs\.r\.o\.|a\.s\./, "IČO / právnická osoba"],
  [/dalsi vozy|nasi nabidku|dalsi nabidka|skladem/, "odkaz na další vozy v nabídce"],
  [/soukrom|prvni majitel|od majitele|jeden majitel|bez realitky/, "tvrzení o soukromém prodeji / majiteli"],
  [/dovoz|po dovozu|z nemecka|z rakouska|ze svycar|ze zahranici/, "dovoz ze zahraničí"],
];

function sellerSignals(d) {
  const t = `${d.title} ${d.description}`.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const hits = SELLER_CUES.filter(([re]) => re.test(t)).map(([, label]) => label);
  return hits.length ? hits.join("; ") : "žádné zřetelné";
}

const SELLER_TASK = `Prodejce: z textu a fotek odhadni, zda jde o soukromníka, překupníka, nebo autobazar/dealera (a podle čeho). Reputaci konkrétního prodejce NEZNÁM a ty ji ze zadaných dat také nezjistíš – jméno ani telefon prodejce jsem záměrně nevložil. Pokud umíš otevřít odkaz na inzerát, můžeš zkusit uvést počet dalších inzerátů prodejce a veřejně dohledatelné recenze, ale jen pokud je opravdu najdeš; jinak výslovně napiš „nezjištěno“ a nic si nevymýšlej. Na závěr uveď stručný postup, jak si reputaci ověřit sám (např. u firmy: IČO v ARES / justice.cz, recenze na Google Maps a Firmy.cz, jiné inzeráty téhož prodejce, ověření VIN a nájezdu v historii vozu, ochota k prohlídce a k přepisu na místě).`;

function listingFacts(d) {
  const v = d.vehicle || {};
  const hist = (d.price_history || []).map((h) => `${h.date}: ${fmtPrice(h.price_czk)}`).join(" → ");
  return [
    `Titulek: ${d.title}`,
    `Odkaz: ${d.url}`,
    `Cena: ${fmtPrice(d.price_czk)}${hist ? ` (historie: ${hist})` : ""}`,
    `Lokalita: ${d.location || "?"}`,
    `Vůz: ${v.make} ${v.model}, rok ${v.year ?? "?"}, nájezd ${fmtKm(v.mileage_km)}, palivo ${v.fuel || "?"}`,
    `STK (z textu): ${v.stk_detected || "nezjištěno"}; tažné: ${v.tow_bar_detected ? "ano" : "nezjištěno"}`,
    `Signály o prodejci (automaticky z textu, orientační): ${sellerSignals(d)}`,
    `Text inzerátu:\n"""\n${d.description}\n"""`,
  ].join("\n");
}

function buildPrompt(d) {
  const p = profile();
  return `Jsi zkušený automechanik a poradce při koupi ojetých vozidel. Posuď inzerát na ojetý vůz podle účelu, textu a přiložené fotokoláže (fotky jsou očíslované [1], [2], …).

ÚČEL NÁKUPU:
${p.purpose || "(neuvedeno)"}

DATA INZERÁTU:
${listingFacts(d)}

ÚKOL:
1. Z fotek zkontroluj zejména:
${PHOTO_CHECKLIST.map((c) => `   - ${c}`).join("\n")}
2. Zhodnoť, zda cena a stav odpovídají účelu nákupu.
3. Uveď typické závady tohoto modelu a motorizace, na které se zeptat.
4. Připrav otázky na telefonát prodejci.
5. ${SELLER_TASK}
Na fotky odkazuj jejich čísly. Pokud něco z fotek nelze posoudit, napiš to – nehádej.

Na úplný konec odpovědi vlož JEDEN blok \`\`\`json v tomto tvaru:
${JSON_SCHEMA_TEXT}`;
}

function buildCompare(ds) {
  const p = profile();
  return `Jsi zkušený automechanik a poradce při koupi ojetých vozidel. Porovnej ${ds.length} kandidátů a urči pořadí, komu zavolat jako prvnímu.

ÚČEL NÁKUPU:
${p.purpose || "(neuvedeno)"}

KANDIDÁTI:
${ds.map((d, i) => `=== Vůz ${i + 1} (${d.uid}) ===\n${listingFacts(d)}`).join("\n\n")}

ÚKOL:
- Porovnej vozy vedle sebe (cena vs. stav vs. účel nákupu, rizika, STK).
- Seřaď je od nejlepšího a stručně zdůvodni pořadí.
- U každého uveď hlavní riziko a 2–3 otázky na prodejce.
- ${SELLER_TASK}
  U prodejce zahrň do hodnocení i to, zda jde o soukromníka nebo obchodníka, a nepřeceňuj tvrzení, která nelze ověřit.
(Fotokoláže jednotlivých vozů přiložím zvlášť, pokud je přidám; jinak posuzuj jen z textu.)

Na úplný konec vlož JEDEN blok \`\`\`json: {"ranking": [{"uid": "...", "score": 0-100, "reason": "..."}]}`;
}

async function getDetail(uid) {
  if (!app.details.has(uid)) {
    const r = await fetch(`/data/listings/${encodeURIComponent(uid)}/listing.json`, { cache: "no-store" });
    if (!r.ok) throw new Error("listing.json nenalezen");
    app.details.set(uid, await r.json());
  }
  return app.details.get(uid);
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

function showPromptDialog(text) {
  const dlg = $("prompt-dialog");
  dlg.innerHTML = `<div class="dlg-head"><h2>Prompt pro AI</h2><button type="button" data-act="close">Zavřít</button></div>
    <div class="dlg-body"><p class="muted">Automatické kopírování se nepovedlo – zkopírujte text ručně.</p>
    <textarea class="big" readonly></textarea></div>`;
  dlg.querySelector("textarea").value = text;
  dlg.showModal();
  dlg.querySelector("textarea").select();
}

function showCompareDialog(ds, text, copied) {
  const dlg = $("prompt-dialog");
  const cars = ds.map((d, i) => {
    const imgs = (d.collages || []).map((r) => {
      const src = dataUrl(d.uid, r);
      return `<div class="collage"><a href="${src}" target="_blank"><img alt="Fotokoláž" src="${src}"></a>
        <div class="row"><button type="button" data-act="copy-img" data-src="${src}">Zkopírovat obrázek</button>
        <a href="${src}" download>Stáhnout</a></div></div>`;
    }).join("");
    return `<h3>Vůz ${i + 1}: ${esc(d.title)}</h3>${imgs || `<p class="muted">Bez koláže (inzerát nemá fotky).</p>`}`;
  }).join("");
  dlg.innerHTML = `<div class="dlg-head"><h2>Porovnání v AI (${ds.length} vozů)</h2><button type="button" data-act="close">Zavřít</button></div>
    <div class="dlg-body">
    <p class="muted">${copied ? "Prompt je zkopírován ve schránce." : "Automatické kopírování se nepovedlo – zkopírujte text níže."}
    Postup: 1) vložte prompt do chatu s AI, 2) přidejte koláže níže (přetáhněte, nebo „Zkopírovat obrázek“ a vložte Ctrl+V) v pořadí Vůz 1, 2, …</p>
    <div class="row"><button type="button" class="primary" data-act="copy-text">Zkopírovat prompt znovu</button></div>
    ${cars}
    <h3>Vložit odpověď AI (pořadí)</h3>
    <textarea id="cmp-paste" placeholder="Sem vložte odpověď z AI, hlavně blok JSON s &quot;ranking&quot;…"></textarea>
    <div class="row" style="margin-top:.4rem"><button type="button" data-act="save-ranking">Uložit pořadí</button></div>
    <div id="cmp-result" class="muted"></div>
    <h3>Text promptu</h3><textarea id="cmp-prompt" class="big" readonly></textarea></div>`;
  dlg.querySelector("#cmp-prompt").value = text;
  dlg.dataset.uids = JSON.stringify(ds.map((d) => d.uid));
  dlg.showModal();
}

function parseRanking(text) {
  const o = extractJson(text);
  const arr = Array.isArray(o?.ranking) ? o.ranking : null;
  if (!arr) return null;
  return arr
    .map((r) => ({ uid: String(r?.uid ?? ""), score: Number(r?.score), reason: r?.reason ? String(r.reason) : "" }))
    .filter((r) => r.uid && Number.isFinite(r.score));
}

async function saveRanking(dlg) {
  const out = dlg.querySelector("#cmp-result");
  const ranking = parseRanking(dlg.querySelector("#cmp-paste").value);
  if (!ranking?.length) {
    out.textContent = "Blok JSON s „ranking“ (uid + score) nenalezen.";
    return;
  }
  const known = new Set(JSON.parse(dlg.dataset.uids || "[]"));
  const stamp = new Date().toISOString();
  let saved = 0;
  const unknown = [];
  for (const r of ranking) {
    if (!known.has(r.uid)) { unknown.push(r.uid); continue; }
    await patchState(r.uid, { ai_compare: { score: Math.max(0, Math.min(100, Math.round(r.score))), reason: r.reason, updated_at: stamp } });
    saved++;
  }
  render();
  out.textContent = `Uloženo ${saved} z ${known.size} vozů.` + (unknown.length ? ` Neznámé uid ignorováno: ${unknown.join(", ")}.` : "");
}

async function copyImage(src) {
  const img = new Image();
  img.src = src;
  await img.decode();
  const c = document.createElement("canvas");
  c.width = img.naturalWidth;
  c.height = img.naturalHeight;
  c.getContext("2d").drawImage(img, 0, 0);
  const blob = await new Promise((res) => c.toBlob(res, "image/png"));
  await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
}

async function copyOrShow(text, okMsg) {
  if (await copyText(text)) say(okMsg);
  else showPromptDialog(text);
}

// ---------- AI report import ----------
function extractJson(text) {
  const candidates = [];
  for (const m of text.matchAll(/```(?:json)?\s*([\s\S]*?)```/gi)) candidates.push(m[1]);
  const a = text.indexOf("{"), b = text.lastIndexOf("}");
  if (a >= 0 && b > a) candidates.push(text.slice(a, b + 1));
  for (const c of candidates.reverse()) {
    try {
      const o = JSON.parse(c.trim());
      if (o && typeof o === "object") return o;
    } catch { /* try next */ }
  }
  return null;
}

function parseReport(text) {
  const o = extractJson(text);
  if (!o) return null;
  const arr = (x) => (Array.isArray(x) ? x.map(String) : x ? [String(x)] : []);
  const score = Number(o.score);
  return {
    verdict: o.verdict ? String(o.verdict) : "",
    score: Number.isFinite(score) ? score : null,
    pluses: arr(o.pluses),
    red_flags: arr(o.red_flags),
    call_checklist: arr(o.call_checklist),
    seller: o.seller ? String(o.seller) : "",
  };
}

function reportHtml(rep) {
  if (!rep) return `<p class="muted">Zatím žádný AI posudek.</p>`;
  const p = rep.parsed;
  const list = (t, a) => (a?.length ? `<h3>${t}</h3><ul class="plain">${a.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "");
  if (!p) return `<div class="report"><p class="muted">JSON blok nenalezen – uložen celý text (${fmtDate(rep.updated_at)}).</p><div class="desc">${esc(rep.raw_text)}</div></div>`;
  return `<div class="report"><div class="verdict">${esc(p.verdict || "Bez verdiktu")}${p.score != null ? ` · ${p.score}/100` : ""}</div>
    <div class="muted">Uloženo ${fmtDate(rep.updated_at)}</div>${p.seller ? `<h3>Prodejce</h3><p>${esc(p.seller)}</p>` : ""}${list("Plusy", p.pluses)}${list("Red flags", p.red_flags)}${list("Checklist na telefonát", p.call_checklist)}</div>`;
}

// ---------- detail dialog ----------
async function openDetail(uid) {
  const dlg = $("detail");
  let d;
  try {
    d = await getDetail(uid);
  } catch (e) {
    say(e.message);
    return;
  }
  app.openUid = uid;
  const u = userOf(uid), v = d.vehicle || {}, sc = d.rule_scoring?.[app.profileId];
  const imgs = (d.images || []).map((r) => `<img loading="lazy" alt="Foto" src="${dataUrl(uid, r)}" data-act="zoom">`).join("");
  const collages = (d.collages || []).map((r) => `<a href="${dataUrl(uid, r)}" target="_blank"><img alt="Fotokoláž" src="${dataUrl(uid, r)}"></a>`).join("");
  const hist = (d.price_history || []).map((h) => `<li>${esc(h.date)}: ${fmtPrice(h.price_czk)}</li>`).join("");
  dlg.innerHTML = `
    <div class="dlg-head"><h2>${esc(d.title)}</h2><button type="button" data-act="close">Zavřít</button></div>
    <div class="dlg-body">
      <div class="gallery">${imgs || `<span class="muted">Bez fotek.</span>`}</div>
      <div class="grid2">
        <div><h3>Parametry</h3><dl class="kv">
          <dt>Cena</dt><dd>${fmtPrice(d.price_czk)}</dd>
          <dt>Vůz</dt><dd>${esc(v.make)} ${esc(v.model)}</dd>
          <dt>Rok / nájezd</dt><dd>${v.year ?? "?"} · ${fmtKm(v.mileage_km)}</dd>
          <dt>Palivo</dt><dd>${esc(v.fuel || "?")}</dd>
          <dt>STK</dt><dd>${esc(v.stk_detected || "nezjištěno")}</dd>
          <dt>Tažné</dt><dd>${v.tow_bar_detected ? "ano" : "nezjištěno"}</dd>
          <dt>Lokalita</dt><dd>${esc(d.location || "?")}</dd>
          <dt>Portál</dt><dd>${esc(PORTALS[d.portal] || d.portal)} · <a href="${esc(safeUrl(d.url))}" target="_blank" rel="noopener noreferrer">inzerát</a></dd>
          <dt>Stav inzerátu</dt><dd>${d.status === "active" ? "aktivní" : "neaktivní"} (viděno ${fmtDate(d.first_seen)} – ${fmtDate(d.last_seen)})</dd>
        </dl></div>
        <div><h3>Historie ceny</h3><ul class="plain">${hist}</ul>
          <h3>Klíčová slova</h3>
          <div class="tags">${(sc?.positive_hits || []).map((t) => `<span class="tag good">${esc(t)}</span>`).join("")}${(sc?.warning_hits || []).map((t) => `<span class="tag bad">${esc(t)}</span>`).join("")}${sc ? "" : `<span class="muted">žádná</span>`}</div>
          ${sc ? `<p class="muted">Základní skóre: ${sc.base_score}</p>` : ""}</div>
      </div>
      <div><h3>Text inzerátu</h3><div class="desc">${esc(d.description)}</div></div>
      ${collages ? `<div class="collage"><h3>Fotokoláž pro AI</h3>${collages}<p class="muted">Přetáhněte tento obrázek do chatu s AI spolu s promptem.</p></div>` : ""}
      <div><h3>Prompt-Bridge</h3>
        <div class="row"><button type="button" class="primary" data-act="copy-prompt">Zkopírovat prompt pro Gemini / ChatGPT</button></div>
        <p class="notice">Analýza fotek v AI slouží jen k odhalení zjevných varovných signálů před telefonátem – nenahrazuje fyzickou prohlídku vozu.</p>
        <h3>Vložit odpověď AI</h3>
        <textarea id="ai-paste" placeholder="Sem vložte odpověď z Gemini / ChatGPT…"></textarea>
        <div class="row" style="margin-top:.4rem"><button type="button" data-act="save-ai">Uložit analýzu</button></div>
        <div id="report" style="margin-top:.6rem">${reportHtml(u.imported_ai_report)}</div>
      </div>
      <div class="grid2">
        <div><h3>Stav</h3><select id="wf">${Object.entries(WORKFLOW).map(([k, t]) => `<option value="${k}" ${(u.workflow_status || "new") === k ? "selected" : ""}>${t}</option>`).join("")}</select></div>
        <div><h3>Poznámky</h3><textarea id="notes" placeholder="Poznámky z hovoru…"></textarea></div>
      </div>
    </div>`;
  $("notes").value = u.notes || "";
  dlg.showModal();
}

// ---------- events ----------
document.addEventListener("click", async (e) => {
  const el = e.target.closest("[data-act]");
  if (!el) return;
  const act = el.dataset.act;
  const uid = el.closest(".card")?.dataset.uid || app.openUid;

  if (act === "close") return el.closest("dialog").close();
  if (act === "zoom") return window.open(el.src, "_blank");
  if (act === "copy-img") {
    try { await copyImage(el.dataset.src); say("Obrázek zkopírován – vložte ho Ctrl+V do chatu."); }
    catch { say("Kopírování obrázku se nepovedlo – přetáhněte ho myší nebo použijte Stáhnout."); }
    return;
  }
  if (act === "save-ranking") return saveRanking(el.closest("dialog"));
  if (act === "copy-text") {
    const t = el.closest("dialog").querySelector("#cmp-prompt").value;
    say((await copyText(t)) ? "Prompt zkopírován." : "Kopírování se nepovedlo.");
    return;
  }
  if (act === "open") return openDetail(uid);
  if (act === "select") {
    el.checked ? app.selected.add(uid) : app.selected.delete(uid);
    return render();
  }
  if (act === "star") {
    const cur = userOf(uid).workflow_status;
    await patchState(uid, { workflow_status: cur === "shortlisted" ? "new" : "shortlisted" });
    return render();
  }
  if (act === "hide") {
    await patchState(uid, { hidden: !userOf(uid).hidden });
    return render();
  }
  if (act === "copy-prompt") {
    const d = await getDetail(app.openUid);
    return copyOrShow(buildPrompt(d), "Prompt zkopírován do schránky.");
  }
  if (act === "save-ai") {
    const raw = $("ai-paste").value.trim();
    if (!raw) return say("Vložte nejdřív text odpovědi.");
    const rep = { updated_at: new Date().toISOString(), raw_text: raw, parsed: parseReport(raw) };
    await patchState(app.openUid, { imported_ai_report: rep });
    $("report").innerHTML = reportHtml(userOf(app.openUid).imported_ai_report);
    $("ai-paste").value = "";
    say(rep.parsed ? "Analýza uložena." : "Uložen celý text (JSON blok nenalezen).");
  }
});

document.addEventListener("change", async (e) => {
  if (e.target.id === "wf") {
    await patchState(app.openUid, { workflow_status: e.target.value });
    render();
  } else if (e.target.id === "notes") {
    await patchState(app.openUid, { notes: e.target.value });
  }
});

for (const id of ["f-text", "f-pmin", "f-pmax", "f-year"]) $(id).addEventListener("input", render);
for (const id of ["f-model", "f-stk", "f-hidden", "f-inactive", "f-sort"]) $(id).addEventListener("change", render);

$("profile").addEventListener("change", () => {
  app.profileId = $("profile").value;
  $("purpose").textContent = profile().purpose || "";
  render();
});

$("compare").addEventListener("click", async () => {
  try {
    const ds = await Promise.all([...app.selected].map(getDetail));
    const text = buildCompare(ds);
    const ok = await copyText(text);
    showCompareDialog(ds, text, ok);
    if (ok) say(`Srovnávací prompt (${ds.length} vozů) zkopírován.`);
  } catch (e) {
    say(e.message);
  }
});

// Starts a crawler run (all categories, or one hand-picked ad) and waits for it to finish.
async function runCrawler(path, body, doneMsg) {
  const btns = [$("crawl"), $("add")];
  btns.forEach((b) => (b.disabled = true));
  try {
    const r = await api(path, { method: "POST", body: JSON.stringify(body) });
    if (r.status === 501) return say("Crawler zatím není implementován.");
    if (r.status === 409) return say("Stahování už běží.");
    if (r.status === 400) return say("Zadejte odkaz na inzerát z nastaveného portálu (Bazoš).");
    say("Stahování běží…");
    for (;;) {
      await new Promise((res) => setTimeout(res, 2000));
      const s = await (await fetch("/api/crawl/status")).json();
      if (!s.running) {
        const last = (s.log_tail || []).filter(Boolean).slice(-1)[0] || "";
        say(s.returncode === 0 ? doneMsg : `Stahování skončilo chybou (kód ${s.returncode}). ${last}`);
        break;
      }
    }
    app.details.clear();
    await load();
    return true;
  } catch (e) {
    say("Chyba: " + e.message);
  } finally {
    btns.forEach((b) => (b.disabled = false));
  }
}

$("crawl").addEventListener("click", () => runCrawler("/api/crawl", {}, "Stahování dokončeno."));

$("add-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const url = $("add-url").value.trim();
  if (url && (await runCrawler("/api/add", { url }, "Inzerát přidán."))) $("add-url").value = "";
});

load();
