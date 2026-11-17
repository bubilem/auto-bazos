"use strict";
// Profile editor (profiles.json via /api/profiles). Uses helpers from app.js: $, esc, say, load, app.

const WEIGHTS = [["price", "Cena"], ["stk", "STK"], ["keywords", "Klíčová slova"], ["presentation", "Prezentace"]];
const KEYWORDS = [
  ["positive_keywords", "Pozitivní slova (přidávají body)"],
  ["warning_keywords", "Varovná slova (ubírají body)"],
  ["exclude_keywords", "Vylučující slova (inzerát se skryje)"],
];
const pf = { profiles: [], groups: [], current: null }; // current = id being edited, null = new profile

const lines = (s) => s.split("\n").map((x) => x.trim()).filter(Boolean);

async function openProfiles(selectId) {
  const r = await fetch("/api/profiles");
  if (!r.ok) return say("Profily se nepodařilo načíst.");
  Object.assign(pf, await r.json());
  pf.current = selectId ?? (pf.profiles.some((p) => p.id === app.profileId) ? app.profileId : pf.profiles[0]?.id ?? null);
  renderProfiles();
  const dlg = $("profiles-dialog");
  if (!dlg.open) dlg.showModal();
}

function renderProfiles(msg = "") {
  const p = pf.profiles.find((x) => x.id === pf.current);
  const base = p || pf.profiles.find((x) => x.id === app.profileId) || pf.profiles[0] || { params: {}, score_weights: {} };
  const w = { price: 30, stk: 30, keywords: 25, presentation: 15, ...base.score_weights };
  $("profiles-dialog").innerHTML = `
    <div class="dlg-head"><h2>Profily hledání</h2><button type="button" data-act="close">Zavřít</button></div>
    <form id="pf-form" class="dlg-body">
      <div class="row">
        <select id="pf-pick">${pf.profiles.map((x) => `<option value="${esc(x.id)}">${esc(x.name)}</option>`).join("")}
          <option value="">+ Nový profil</option></select>
        <span class="muted">${p ? "Úprava profilu" : "Nový profil (předvyplněno podle aktuálního)"}</span>
      </div>
      <label>Název <input id="pf-name" required maxlength="80" value="${p ? esc(p.name) : ""}"></label>
      <label>Účel užití <textarea id="pf-purpose" maxlength="2000">${esc(base.purpose || "")}</textarea></label>
      <div class="row">
        <label>Referenční model <input id="pf-ref" maxlength="80" value="${esc(base.reference_model || "")}"></label>
        <label>Skupina modelů <select id="pf-group">${pf.groups.map((g) =>
          `<option value="${esc(g.id)}"${g.id === base.equivalence_group ? " selected" : ""}>${esc(g.name)}</option>`).join("")}</select></label>
      </div>
      <p class="muted">Skupina určuje, která auta se z Bazoše vůbec stahují (modely ze <code>taxonomy.json</code>).</p>
      <div class="row">
        <label>Cílová cena (Kč) <input id="pf-target" type="number" min="0" step="1000" value="${base.params.price_target_czk ?? 0}"></label>
        <label>Maximální cena (Kč) <input id="pf-max" type="number" min="0" step="1000" value="${base.params.price_max_czk ?? 0}"></label>
      </div>
      <p class="muted">Do cílové ceny dostane inzerát plný počet bodů za cenu, nad maximem nulu. Dražší inzeráty než nejvyšší maximum ze všech profilů se nestahují.</p>
      ${KEYWORDS.map(([k, label]) => `<label>${label} (jedno na řádek)
        <textarea id="pf-${k}" rows="4">${esc((base[k] || []).join("\n"))}</textarea></label>`).join("")}
      <div class="row">${WEIGHTS.map(([k, label]) =>
        `<label>${label} <input id="pf-w-${k}" type="number" min="0" max="100" value="${w[k]}"></label>`).join("")}</div>
      <div class="row">
        <button type="submit" class="primary">Uložit</button>
        ${p ? `<button type="button" id="pf-del"${pf.profiles.length < 2 ? " disabled" : ""}>Smazat profil</button>` : ""}
        <span id="pf-msg" class="muted" role="status">${esc(msg)}</span>
      </div>
    </form>`;
  $("pf-pick").value = pf.current ?? "";
}

function readProfileForm() {
  const num = (id) => parseInt($(id).value, 10);
  return {
    ...(pf.current ? { id: pf.current } : {}),
    name: $("pf-name").value, purpose: $("pf-purpose").value, reference_model: $("pf-ref").value,
    equivalence_group: $("pf-group").value,
    params: { price_target_czk: num("pf-target"), price_max_czk: num("pf-max") },
    ...Object.fromEntries(KEYWORDS.map(([k]) => [k, lines($(`pf-${k}`).value)])),
    score_weights: Object.fromEntries(WEIGHTS.map(([k]) => [k, num(`pf-w-${k}`)])),
  };
}

// The server re-scores in a background crawler process; wait for it, then reload the index.
async function afterProfileChange(selectId) {
  say("Přepočítávám skóre…");
  for (;;) {
    await new Promise((res) => setTimeout(res, 700));
    const s = await (await fetch("/api/crawl/status")).json();
    if (!s.running) break;
  }
  app.details.clear();
  app.profileId = selectId ?? app.profileId;
  await load();
  say("Profily uloženy, skóre přepočítáno.");
}

async function sendProfile(path, body) {
  const r = await fetch(path, { method: "POST", body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (r.status === 409) throw new Error("Právě běží stahování, zkuste to po jeho dokončení.");
  if (!r.ok) throw new Error(data.error || `chyba ${r.status}`);
  return data;
}

document.addEventListener("submit", async (e) => {
  if (e.target.id !== "pf-form") return;
  e.preventDefault();
  try {
    const profile = readProfileForm();
    const data = await sendProfile("/api/profiles", { profile });
    const saved = profile.id || data.profiles[data.profiles.length - 1].id;
    await openProfiles(saved);
    await afterProfileChange(saved);
  } catch (err) {
    $("pf-msg") && ($("pf-msg").textContent = err.message);
  }
});

document.addEventListener("change", (e) => {
  if (e.target.id !== "pf-pick") return;
  pf.current = e.target.value || null;
  renderProfiles();
});

document.addEventListener("click", async (e) => {
  if (e.target.id !== "pf-del") return;
  const p = pf.profiles.find((x) => x.id === pf.current);
  if (!p || !confirm(`Smazat profil „${p.name}“? Hodnocení inzerátů pro něj zmizí (uložené inzeráty zůstanou).`)) return;
  try {
    const data = await sendProfile("/api/profiles/delete", { id: p.id });
    pf.profiles = data.profiles;
    pf.current = pf.profiles[0]?.id ?? null;
    renderProfiles();
    await afterProfileChange(pf.current);
  } catch (err) {
    $("pf-msg").textContent = err.message;
  }
});

$("profiles-open").addEventListener("click", () => openProfiles());
