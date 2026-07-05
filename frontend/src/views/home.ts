// Home — editorial. The hero stat is the research ledger; the kill count is
// the headline figure on purpose (publishing failures is the credibility
// mechanism). Numbers come from the real registry, never hardcoded.

import { api } from "../api";

export async function renderHome(root: HTMLElement): Promise<void> {
  let registered = 0;
  let live = 0;
  let killed = 0;
  try {
    const hyps = await api.hypotheses();
    registered = hyps.length;
    live = hyps.filter((h) => h.status === "live").length;
    killed = hyps.filter((h) => h.status === "killed").length;
  } catch {
    /* API down: ledger shows zeros rather than invented numbers */
  }

  root.innerHTML = `
    <div class="lo-page lo-page--editorial">
      <div class="lo-hero">
        <div class="lo-label">Quantitative research platform</div>
        <h1>Systematic research under falsification discipline.</h1>
        <p class="lead">
          Lotus ingests market data with provenance and point-in-time integrity, and evaluates
          strategy hypotheses under pre-registration: baseline, frozen thresholds, a kill test,
          and numeric kill criteria — committed before the test data is touched.
        </p>
        <div class="lo-ledger">
          <div><div class="num">${registered}</div><div class="lo-label">registered</div></div>
          <div><div class="num live">${live}</div><div class="lo-label">live</div></div>
          <div><div class="num">${killed}</div><div class="lo-label">killed</div></div>
          <div class="note">The kill count is the headline figure on purpose. Killed hypotheses
          are first-class content — the visible denominator of everything we tried.</div>
        </div>
      </div>

      <section class="lo-section">
        <h2 class="lo-h2">Research tracks</h2>
        <div class="lo-tracks">
          <div class="lo-track">
            <div class="status" style="color:var(--lo-neg)"><span class="dot"></span>GATE: REPLICATION — RED</div>
            <h3>Volatility lab</h3>
            <div class="venues">SPX / XSP options</div>
            <p>Blocked until the engine reproduces the CBOE PUT index. No proprietary vol work
            past a red gate.</p>
          </div>
          <div class="lo-track">
            <div class="status" style="color:var(--lo-accent)"><span class="dot"></span>ACTIVE · DEV</div>
            <h3>Crypto systematic</h3>
            <div class="venues">Binance spot · Hyperliquid perps</div>
            <p>Spot and perp ingestion live with full funding history. First registered
            hypothesis tested — and killed at its replication gate.</p>
          </div>
          <div class="lo-track">
            <div class="status" style="color:var(--lo-faint)"><span class="dot"></span>DORMANT</div>
            <h3>Order-flow lab</h3>
            <div class="venues">B3 futures</div>
            <p>Defined as a track; no ingestion, no hypotheses. Nothing is claimed for it.</p>
          </div>
        </div>
      </section>
    </div>`;
}
