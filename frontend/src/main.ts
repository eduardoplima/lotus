// M0 entry: render one daily-candle tile for a single instrument.

import { fetchBars } from "./api";
import { createCandleTile, setCandleData } from "./chart";

const SYMBOL = "SPY";

function buildTile(symbol: string): { chartEl: HTMLElement; statusEl: HTMLElement } {
  const grid = document.getElementById("grid")!;
  const tile = document.createElement("section");
  tile.className = "tile";

  const status = document.createElement("div");
  status.className = "status";
  status.textContent = `${symbol} — loading…`;

  const chartEl = document.createElement("div");
  chartEl.className = "chart";

  tile.append(status, chartEl);
  grid.append(tile);
  return { chartEl, statusEl: status };
}

async function main(): Promise<void> {
  const { chartEl, statusEl } = buildTile(SYMBOL);
  const chart = createCandleTile(chartEl);
  try {
    const bars = await fetchBars(SYMBOL, "1d");
    if (bars.length === 0) {
      statusEl.textContent = `${SYMBOL} — no bars stored yet. Run: python -m backend.cli ingest ${SYMBOL}`;
      return;
    }
    setCandleData(chart, bars);
    statusEl.textContent = `${SYMBOL} — ${bars.length} daily bars (source: ${bars[0].source})`;
  } catch (err) {
    statusEl.textContent = `${SYMBOL} — error: ${(err as Error).message}`;
  }
}

void main();
