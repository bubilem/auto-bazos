"use strict";
// Editor of model groups (taxonomy.json) and Bazoš categories (config.json). Helpers from app.js: $, esc, say.

const src = { groups: {}, used: [], categories: [], current: null }; // current = group id, null = new group

// One model per line:  Značka | Model | alternativní zápisy (čárkou) | poznámka
const modelToLine = (m) => [m.make, m.model, (m.match || []).join(", "), m.notes || ""].join(" | ").replace(/( \| )+$/, "");

function lineToModel(line) {
  const [make = "", model = "", match = "", ...notes] = line.split("|").map((x) => x.trim());
  const m = { make, model };
  const alts = match.split(",").map((x) => x.trim()).filter(Boolean);
  if (alts.length) m.match = alts;
  if (notes.join(" | ").trim()) m.notes = notes.join(" | ").trim();
  return m;
}

async function openSources(selectId) {
  const [g, c] = await Promise.all([fetch("/api/groups"), fetch("/api/categories")]);
  if (!g.ok || !c.ok) return say("Skupiny a kategorie se nepodařilo načíst.");
  Object.assign(src, await g.json(), await c.json());
  const ids = Object.keys(src.groups);
  src.current = selectId !== undefined ? selectId : ids.includes(src.current) ? src.current : ids[0] ?? null;
  renderSources();
  if (!$("sources-dialog").open) $("sources-dialog").showModal();
}

function renderSources(msg = "") {
  const g = src.current ? src.groups[src.current] : null;
  const used = g && src.used.includes(src.current);
  $("sources-dialog").innerHTML = `
    <div class="dlg-head"><h2>Modely a kategorie</h2><button type="button" data-act="close">Zavřít</button></div>
    <div class="dlg-body">
      <form id="sg-form" class="dlg-body" style="padding:0">
        <h3>Skupiny modelů</h3>
        <p class="muted">Skupina říká, které modely se z Bazoše stahují a jsou považované za zaměnitelné. Profil si skupinu vybírá v editoru profilů.</p>
        <div class="row">
          <select id="sg-pick">${Object.entries(src.groups).map(([id, x]) => `<option value="${esc(id)}">${esc(x.name)}</option>`).join("")}
            <option value="">+ Nová skupina</option></select>
          <span class="muted">${g ? "Úprava skupiny" : "Nová skupina"}</span>
        </div>
        <label>Název skupiny <input id="sg-name" required maxlength="80" value="${g ? esc(g.name) : ""}"></label>
        <label>Modely (jeden na řádek: <code>Značka | Model | alternativní zápisy čárkou | poznámka</code>)
          <textarea id="sg-models" class="big" rows="10" spellcheck="false">${esc((g?.models || []).map(modelToLine).join("\n"))}</textarea></label>
        <p class="muted">Model se v titulku inzerátu hledá podle názvu modelu, nebo podle alternativních zápisů, pokud jsou uvedené (např. <code>Toyota | ProAce | proace, pro ace</code>).</p>
        <div class="row">
          <button type="submit" class="primary">Uložit skupinu</button>
          ${g ? `<button type="button" id="sg-del"${used ? " disabled title=\"Skupinu používá některý profil\"" : ""}>Smazat skupinu</button>` : ""}
          <span id="sg-msg" class="muted" role="status">${esc(msg)}</span>
        </div>
      </form>
      <form id="sc-form" class="dlg-body" style="padding:0">
        <h3>Kategorie Bazoše</h3>
        <p class="muted">Slug je část adresy <code>auto.bazos.cz/&lt;slug&gt;/</code> (např. <code>dodavka</code>, <code>peugeot</code>). Jedna stránka má 40 inzerátů, stahují se od nejnovějších.</p>
        <div id="sc-rows">${src.categories.map(catRow).join("")}</div>
        <div class="row">
          <button type="button" id="sc-add">+ Přidat kategorii</button>
          <button type="submit" class="primary">Uložit kategorie</button>
          <span id="sc-msg" class="muted" role="status"></span>
        </div>
        <p class="muted">Změny se projeví při dalším stahování. Neexistující slug crawler ohlásí varováním, že na první stránce nenašel inzeráty.</p>
      </form>
    </div>`;
  $("sg-pick").value = src.current ?? "";
}

const catRow = (c = { slug: "", max_pages: 3 }) => `<div class="row sc-row">
  <input class="sc-slug" placeholder="slug" maxlength="40" value="${esc(c.slug)}" aria-label="Slug kategorie">
  <input class="sc-pages" type="number" min="1" max="50" value="${c.max_pages}" aria-label="Počet stránek"> stránek
  <button type="button" class="sc-del" aria-label="Odebrat kategorii">✕</button></div>`;

async function postJson(path, body) {
  const r = await fetch(path, { method: "POST", body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (r.status === 409) throw new Error("Právě běží stahování, zkuste to po jeho dokončení.");
  if (!r.ok) throw new Error(data.error || `chyba ${r.status}`);
  return data;
}

document.addEventListener("submit", async (e) => {
  if (e.target.id === "sg-form") {
    e.preventDefault();
    try {
      const models = $("sg-models").value.split("\n").map((l) => l.trim()).filter(Boolean).map(lineToModel);
      const data = await postJson("/api/groups", { ...(src.current ? { id: src.current } : {}), group: { name: $("sg-name").value, models } });
      await openSources(data.id);
      $("sg-msg").textContent = "Skupina uložena.";
    } catch (err) {
      $("sg-msg").textContent = err.message;
    }
  } else if (e.target.id === "sc-form") {
    e.preventDefault();
    try {
      const categories = [...document.querySelectorAll(".sc-row")].map((r) => ({
        slug: r.querySelector(".sc-slug").value, max_pages: parseInt(r.querySelector(".sc-pages").value, 10) }));
      const data = await postJson("/api/categories", { categories });
      src.categories = data.categories;
      renderSources();
      $("sc-msg").textContent = "Kategorie uloženy.";
    } catch (err) {
      $("sc-msg").textContent = err.message;
    }
  }
});

document.addEventListener("change", (e) => {
  if (e.target.id !== "sg-pick") return;
  src.current = e.target.value || null;
  renderSources();
});

document.addEventListener("click", async (e) => {
  if (e.target.id === "sc-add") {
    $("sc-rows").insertAdjacentHTML("beforeend", catRow());
  } else if (e.target.classList.contains("sc-del")) {
    e.target.closest(".sc-row").remove();
  } else if (e.target.id === "sg-del") {
    const g = src.groups[src.current];
    if (!confirm(`Smazat skupinu „${g.name}“?`)) return;
    try {
      await postJson("/api/groups/delete", { id: src.current });
      await openSources();
      say("Skupina smazána.");
    } catch (err) {
      $("sg-msg").textContent = err.message;
    }
  }
});

$("sources-open").addEventListener("click", () => openSources());
