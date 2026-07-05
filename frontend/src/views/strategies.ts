// Strategy catalogue — hypotheses (registry + cemetery), engine-validation
// runs, and the replication gate. Killed strategies are first-class content.

import { api, type BacktestResult, type BacktestRun, type Hypothesis } from "../api";

export interface CatalogueCard {
  id: string; // route id
  name: string;
  archetype: string;
  status: "registered" | "live" | "killed" | "engine-validation" | "gate";
  sharpe: number | null;
  maxDd: number | null; // fraction, negative
  note: string;
}

const state = { archetype: "all", status: "all" };

const GATE_CARD: CatalogueCard = {
  id: "gate-replication",
  name: "put_index_replication",
  archetype: "short-vol",
  status: "gate",
  sharpe: null,
  maxDd: null,
  note: "Replication gate for the volatility track (CBOE PUT). RED — no proprietary vol work until green.",
};

function hypothesisCard(h: Hypothesis): CatalogueCard {
  const name = h.statement.match(/\[(H\d)\//)
    ? `intraday_regime_momentum · ${h.statement.match(/\[(H\d)\//)![1]}`
    : `hypothesis #${h.id}`;
  return {
    id: `hyp-${h.id}`,
    name,
    archetype: "regime-overlay",
    status: h.status === "killed" ? "killed" : h.status,
    sharpe: null,
    maxDd: null,
    note:
      h.status === "killed"
        ? `† killed ${h.killed_at?.slice(0, 10) ?? ""} — R1 replication gate fired`
        : h.statement.slice(0, 110),
  };
}

function runCard(run: BacktestRun, result: BacktestResult | null): CatalogueCard {
  const inst = String(run.data_window["instrument_id"] ?? run.data_window["symbol"] ?? "?");
  const returns = result?.headline?.stats_returns ?? {};
  const sharpe = returns["Sharpe Ratio (252 days)"] ?? null;
  const maxDd = result?.tail?.max_drawdown_frac ?? null;
  return {
    id: `run-${run.id}`,
    name: `${run.strategy} · ${inst.split(".")[0]}`,
    archetype: "momentum",
    status: "engine-validation",
    sharpe: typeof sharpe === "number" ? sharpe : null,
    maxDd: typeof maxDd === "number" ? maxDd : null,
    note: "plumbing, not edge — engine validation run, no pre-registered hypothesis",
  };
}

export async function loadCatalogue(): Promise<CatalogueCard[]> {
  const [hyps, runs] = await Promise.all([api.hypotheses(), api.runs()]);
  const results = await Promise.all(
    runs.map((r) => api.result(r.id).catch(() => null)),
  );
  // Deduplicate runs by (strategy, instrument): keep the most recent.
  const seen = new Set<string>();
  const runCards: CatalogueCard[] = [];
  for (let i = 0; i < runs.length; i++) {
    const card = runCard(runs[i], results[i]);
    if (seen.has(card.name)) continue;
    seen.add(card.name);
    runCards.push(card);
  }
  return [GATE_CARD, ...hyps.map(hypothesisCard), ...runCards];
}

const ARCHETYPES = ["all", "trend", "carry", "momentum", "regime-overlay", "short-vol", "positioning"];
const STATUSES = ["all", "registered", "killed", "engine-validation", "gate"];

function pillClass(status: CatalogueCard["status"]): string {
  if (status === "live") return "lo-pill lo-pill--live";
  if (status === "killed") return "lo-pill lo-pill--killed";
  if (status === "gate") return "lo-pill lo-pill--gate";
  return "lo-pill";
}

function fmtMetric(v: number | null, pct = false): string {
  if (v === null) return "—";
  return pct ? `${(v * 100).toFixed(2)}%` : v.toFixed(2);
}

export async function renderStrategies(root: HTMLElement): Promise<void> {
  root.innerHTML = `
    <div class="lo-page lo-page--dash">
      <div class="lo-label">Dashboards / Strategies</div>
      <h2 class="lo-h2">Strategy catalogue</h2>
      <div class="lo-gatebanner">
        <strong>REPLICATION GATE · RED</strong>
        <span>The engine has not yet reproduced a public benchmark for the volatility track.
        No proprietary vol hypothesis is evaluated until it does.</span>
        <a href="#/dashboard/strategies/gate-replication">View gate →</a>
      </div>
      <div class="lo-chips" id="chips-arch"></div>
      <div class="lo-chips" id="chips-status"></div>
      <div class="lo-cards" id="cards"></div>
    </div>`;

  const cards = await loadCatalogue();

  const renderChips = (el: HTMLElement, values: string[], key: "archetype" | "status") => {
    el.innerHTML = "";
    for (const v of values) {
      const b = document.createElement("button");
      b.textContent = v;
      b.classList.toggle("active", state[key] === v);
      b.addEventListener("click", () => {
        state[key] = v;
        renderChips(el, values, key);
        renderCards();
      });
      el.appendChild(b);
    }
  };

  const renderCards = () => {
    const host = root.querySelector<HTMLElement>("#cards")!;
    host.innerHTML = "";
    const visible = cards.filter(
      (c) =>
        (state.archetype === "all" || c.archetype === state.archetype) &&
        (state.status === "all" || c.status === state.status),
    );
    for (const c of visible) {
      const el = document.createElement("article");
      el.className = "lo-card" + (c.status === "killed" ? " lo-hatch" : "");
      el.innerHTML = `
        <div class="top">
          <span class="lo-label">${c.archetype}</span>
          <span class="${pillClass(c.status)}">${c.status === "gate" ? "gate: replication" : c.status}</span>
        </div>
        <h3>${c.name}</h3>
        <div class="metrics">
          <div class="metric"><div class="lo-label">Net Sharpe</div><div class="v">${fmtMetric(c.sharpe)}</div></div>
          <div class="metric"><div class="lo-label">Max DD</div><div class="v ${c.maxDd !== null && c.maxDd < 0 ? "" : ""}">${fmtMetric(c.maxDd, true)}</div></div>
        </div>
        <p class="note">${c.note}</p>`;
      el.addEventListener("click", () => {
        window.location.hash = `#/dashboard/strategies/${c.id}`;
      });
      host.appendChild(el);
    }
    if (visible.length === 0) {
      host.innerHTML = `<p style="color:var(--lo-dim)">No strategies match the current filters.</p>`;
    }
  };

  renderChips(root.querySelector("#chips-arch")!, ARCHETYPES, "archetype");
  renderChips(root.querySelector("#chips-status")!, STATUSES, "status");
  renderCards();
}
