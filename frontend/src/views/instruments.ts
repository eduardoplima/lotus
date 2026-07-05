// Instruments — OHLC dashboard (left switcher, candles + volume [+ funding]).

import { api, type FundingRate, type OhlcBar } from "../api";
import { renderInstrumentChart, type InstrumentChart } from "../chart";

interface InstrumentSpec {
  key: string;
  symbol: string; // API symbol
  label: string;
  meta: string;
  timeframes: string[];
  funding: boolean;
  gated?: string; // gated message (no chart)
  overlayNote?: string; // GEX/positioning honesty note
}

const INSTRUMENTS: InstrumentSpec[] = [
  {
    key: "MES",
    symbol: "MES",
    label: "MES",
    meta: "CME · IBKR",
    timeframes: ["1h", "1d"],
    funding: false,
    overlayNote:
      "GEX overlay disabled — no positioning data ingested (options feed sits behind the " +
      "replication gate). Walls are assumption-dependent and are never fabricated.",
  },
  {
    key: "BTCUSDT",
    symbol: "BTCUSDT",
    label: "BTCUSDT",
    meta: "Binance spot",
    timeframes: ["1h", "1d"],
    funding: false,
  },
  {
    key: "BTC-PERP",
    symbol: "BTC",
    label: "BTC-PERP",
    meta: "Hyperliquid perp",
    timeframes: ["1h"],
    funding: true,
  },
  {
    key: "SPY",
    symbol: "SPY",
    label: "SPY",
    meta: "ARCA · IBKR",
    timeframes: ["1h", "1d"],
    funding: false,
  },
  {
    key: "XSP",
    symbol: "XSP",
    label: "XSP",
    meta: "Cboe mini-SPX",
    timeframes: [],
    funding: false,
    gated:
      "Options ingestion for the volatility track is pending — the replication gate is RED. " +
      "Nothing is charted from unvalidated data.",
  },
];

const state = { selected: "MES", timeframe: "1d" };
let activeChart: InstrumentChart | null = null;

export async function renderInstruments(root: HTMLElement): Promise<void> {
  root.innerHTML = `
    <div class="lo-page lo-page--dash">
      <div class="lo-label">Dashboards / Instruments</div>
      <h2 class="lo-h2">Instruments — OHLC</h2>
      <div class="lo-instr">
        <nav class="lo-switcher" id="switcher"></nav>
        <div class="lo-panel lo-chartcard">
          <div class="lo-chartbar">
            <div class="lo-tf" id="tf"></div>
            <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
              <span id="assume-slot"></span>
              <span class="lo-chip" id="prov">·</span>
            </div>
          </div>
          <div class="lo-charthost" id="charthost"></div>
        </div>
      </div>
    </div>`;

  const switcher = root.querySelector<HTMLElement>("#switcher")!;
  for (const spec of INSTRUMENTS) {
    const btn = document.createElement("button");
    btn.innerHTML =
      `<span class="sym">${spec.label}</span><span class="meta">${spec.meta}</span>` +
      (spec.gated ? `<span class="gated"> GATED</span>` : "");
    btn.addEventListener("click", () => {
      state.selected = spec.key;
      if (!spec.timeframes.includes(state.timeframe) && spec.timeframes.length > 0) {
        state.timeframe = spec.timeframes[spec.timeframes.length - 1];
      }
      void update(root);
    });
    btn.dataset.key = spec.key;
    switcher.appendChild(btn);
  }
  await update(root);
}

async function update(root: HTMLElement): Promise<void> {
  const spec = INSTRUMENTS.find((s) => s.key === state.selected)!;

  root.querySelectorAll<HTMLButtonElement>("#switcher button").forEach((b) => {
    b.classList.toggle("active", b.dataset.key === spec.key);
  });

  const tf = root.querySelector<HTMLElement>("#tf")!;
  tf.innerHTML = "";
  for (const t of spec.timeframes) {
    const btn = document.createElement("button");
    btn.textContent = t;
    btn.classList.toggle("active", t === state.timeframe);
    btn.addEventListener("click", () => {
      state.timeframe = t;
      void update(root);
    });
    tf.appendChild(btn);
  }

  const assumeSlot = root.querySelector<HTMLElement>("#assume-slot")!;
  assumeSlot.innerHTML = spec.overlayNote
    ? `<span class="lo-badge-assume" title="${spec.overlayNote}">⚠ assumption-dependent · overlay off</span>`
    : "";

  const host = root.querySelector<HTMLElement>("#charthost")!;
  const prov = root.querySelector<HTMLElement>("#prov")!;
  activeChart?.destroy();
  activeChart = null;

  if (spec.gated) {
    host.classList.remove("lo-charthost");
    host.classList.add("lo-gatedpanel");
    host.innerHTML = `
      <div class="inner">
        <div class="lo-gate" style="margin-bottom:12px;"><span class="lo-gate__dot"></span>GATE REPLICATION · RED</div>
        <p>${spec.gated}</p>
      </div>`;
    prov.textContent = "no data — gated";
    return;
  }
  host.classList.add("lo-charthost");
  host.classList.remove("lo-gatedpanel");
  host.innerHTML = "";

  let bars: OhlcBar[] = [];
  let funding: FundingRate[] | null = null;
  try {
    bars = await api.bars(spec.symbol, state.timeframe);
    if (spec.funding) funding = await api.funding(spec.symbol);
  } catch (err) {
    host.classList.remove("lo-charthost");
    host.classList.add("lo-gatedpanel");
    host.innerHTML = `<div class="inner"><p>Failed to load bars: ${String(err)}</p></div>`;
    return;
  }
  if (bars.length === 0) {
    host.classList.remove("lo-charthost");
    host.classList.add("lo-gatedpanel");
    host.innerHTML = `<div class="inner"><p>No ${state.timeframe} bars ingested for ${spec.label}. The hole is recorded, not filled.</p></div>`;
    prov.textContent = "no data";
    return;
  }

  activeChart = renderInstrumentChart(host, bars, funding);
  const last = bars[bars.length - 1];
  prov.textContent = `${last.source} · vintage ${last.vintage} · ${bars.length} bars`;
}
