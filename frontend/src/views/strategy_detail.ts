// Strategy detail — hypothesis block, kill/gate banners, frozen parameters as
// a monospace config artifact, results with tail metrics at equal weight,
// stress-window table, run-provenance footer.

import { api, type BacktestResult, type BacktestRun, type Hypothesis } from "../api";

const WIN_RATE_TOOLTIP = "win rate is not evidence for short-convexity strategies";

function configRow(k: string, v: unknown): string {
  const value = typeof v === "object" ? JSON.stringify(v) : String(v ?? "—");
  return `<div class="row"><span class="k">${k}</span><span class="v">${value}</span></div>`;
}

function metricCell(label: string, value: string, cls = ""): string {
  return `<div class="cell"><div class="lo-label">${label}</div><div class="v ${cls}">${value}</div></div>`;
}

export async function renderStrategyDetail(root: HTMLElement, id: string): Promise<void> {
  if (id === "gate-replication") return renderGateDetail(root);
  if (id.startsWith("hyp-")) {
    const hyps = await api.hypotheses();
    const h = hyps.find((x) => x.id === Number(id.slice(4)));
    if (h) return renderHypothesisDetail(root, h);
  }
  if (id.startsWith("run-")) {
    const runs = await api.runs();
    const run = runs.find((x) => x.id === Number(id.slice(4)));
    if (run) {
      const result = await api.result(run.id).catch(() => null);
      return renderRunDetail(root, run, result);
    }
  }
  root.innerHTML = `<div class="lo-page lo-page--detail"><p>Unknown strategy: ${id}</p></div>`;
}

function renderGateDetail(root: HTMLElement): void {
  root.innerHTML = `
    <div class="lo-page lo-page--detail">
      <div class="lo-dhead">
        <h1>put_index_replication</h1>
        <span class="lo-label">short-vol</span>
        <span class="lo-pill lo-pill--gate">gate: replication</span>
      </div>
      <div class="lo-gatebanner">
        <strong>REPLICATION GATE · RED</strong>
        <span>Before any proprietary hypothesis on the volatility track, the engine must
        reproduce a known public benchmark — the CBOE PUT index. This requires historical
        options chains (open interest + greeks) that are not yet ingested. Until this gate
        is green, proprietary vol results would not be trustworthy and are not produced.</span>
      </div>
      <section class="lo-section">
        <div class="lo-label">What unblocks it</div>
        <div class="lo-config" style="margin-top:10px;">
          ${configRow("required data", "SPX/XSP EOD option chains with OI + greeks (vendor: ThetaData / OptionsDX — not yet contracted)")}
          ${configRow("gate test", "reproduce CBOE PUT index levels within tolerance on overlapping window")}
          ${configRow("status", "RED — ingestion pending")}
        </div>
      </section>
    </div>`;
}

function renderHypothesisDetail(root: HTMLElement, h: Hypothesis): void {
  const killed = h.status === "killed";
  root.innerHTML = `
    <div class="lo-page lo-page--detail">
      <div class="lo-dhead">
        <h1>intraday_regime_momentum</h1>
        <span class="lo-label">regime-overlay</span>
        <span class="lo-pill ${killed ? "lo-pill--killed" : ""}">${h.status}</span>
      </div>
      ${
        killed
          ? `<div class="lo-killbanner lo-hatch">
              <div class="t">† KILLED · ${h.killed_at?.slice(0, 10) ?? ""}</div>
              <div><strong>Kill test that fired:</strong> ${h.kill_test}</div>
              <div style="margin-top:6px; color:var(--lo-dim);">${h.kill_reason ?? ""}</div>
            </div>`
          : ""
      }
      <div class="lo-hypo">
        <div class="lo-label">Pre-registered claim</div>
        <div class="claim">${h.statement}</div>
        <div class="baseline">vs baseline · ${h.baseline}</div>
      </div>
      <section class="lo-section">
        <div class="lo-label">Frozen parameters (ex-ante)</div>
        <div class="lo-config" style="margin-top:10px;">
          ${configRow("signal_threshold", h.signal_threshold)}
          ${configRow("dev_split", h.dev_split_def)}
          ${configRow("kill_criteria", h.kill_criteria)}
          ${configRow("registered_at", h.registered_at)}
        </div>
      </section>
      <div class="lo-provfoot">
        <span class="lo-chip">hypothesis #${h.id} · registry: postgres · cemetery entry on file</span>
      </div>
    </div>`;
}

function renderRunDetail(root: HTMLElement, run: BacktestRun, result: BacktestResult | null): void {
  const returns = result?.headline?.stats_returns ?? {};
  const pnls = result?.headline?.stats_pnls ?? {};
  const tail = result?.tail ?? {};
  const currency = Object.keys(pnls)[0] ?? "";
  const pnl = pnls[currency] ?? {};

  const sharpe = returns["Sharpe Ratio (252 days)"];
  const maxDd = tail["max_drawdown_frac"];
  const worstTrade = tail["worst_trade_pnl"];
  const hitRate = pnl["Win Rate"];

  const stressRows = Object.entries(result?.stress_windows ?? {})
    .map(
      ([w, cov]) =>
        `<tr><td>${w}</td><td class="${cov === "covered" ? "" : "neg"}">${cov}</td></tr>`,
    )
    .join("");

  root.innerHTML = `
    <div class="lo-page lo-page--detail">
      <div class="lo-dhead">
        <h1>${run.strategy}</h1>
        <span class="lo-label">momentum</span>
        <span class="lo-pill">engine-validation</span>
      </div>
      <div class="lo-hypo">
        <div class="lo-label">Run kind</div>
        <div class="claim">Engine-plumbing validation on ${String(run.data_window["instrument_id"] ?? "?")} —
        <em>plumbing, not edge</em>. No pre-registered hypothesis (hypothesis_id = null); this result
        must not be read as a discovery.</div>
        <div class="baseline">vs baseline · none (validation run)</div>
      </div>
      <section class="lo-section">
        <div class="lo-label">Frozen parameters</div>
        <div class="lo-config" style="margin-top:10px;">
          ${Object.entries(run.params).map(([k, v]) => configRow(k, v)).join("")}
          ${configRow("cost_model", run.cost_model)}
        </div>
      </section>
      ${
        result
          ? `<section class="lo-section">
              <div class="lo-label">Results — net of pessimistic costs</div>
              <div class="lo-results">
                ${metricCell("Net Sharpe (252d)", typeof sharpe === "number" ? sharpe.toFixed(2) : "—")}
                ${metricCell("Max drawdown", typeof maxDd === "number" ? `${(maxDd * 100).toFixed(2)}%` : "—", typeof maxDd === "number" && maxDd < 0 ? "neg" : "")}
                ${metricCell("Worst trade", typeof worstTrade === "number" ? `${worstTrade.toFixed(2)} ${currency}` : "—", typeof worstTrade === "number" && worstTrade < 0 ? "neg" : "")}
                ${metricCell("PnL (total)", pnl["PnL (total)"] !== undefined ? `${Number(pnl["PnL (total)"]).toFixed(2)} ${currency}` : "—", Number(pnl["PnL (total)"]) >= 0 ? "pos" : "neg")}
              </div>
              <div class="lo-hit" title="${WIN_RATE_TOOLTIP}">
                hit rate ${typeof hitRate === "number" ? (hitRate * 100).toFixed(1) + "%" : "—"} ⓘ
              </div>
            </section>
            <section class="lo-section">
              <div class="lo-label">Stress-window coverage</div>
              <div class="lo-table-wrap">
                <table class="lo-table" style="margin-top:10px;">
                  <thead><tr><th>window</th><th>coverage</th></tr></thead>
                  <tbody>${stressRows}</tbody>
                </table>
              </div>
            </section>`
          : `<p style="color:var(--lo-dim)">No result recorded for this run.</p>`
      }
      <div class="lo-provfoot">
        <span class="lo-chip">
          data ${String(run.data_window["start"] ?? "").slice(0, 10)} → ${String(run.data_window["end"] ?? "").slice(0, 10)}
          · ${String(run.data_window["n_bars"] ?? "?")} bars
          · git ${run.code_version.slice(0, 12)}
          · run ${run.created_at.slice(0, 19)}Z
        </span>
      </div>
    </div>`;
}
