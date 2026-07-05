// Instrument chart: candles + volume subpane (+ optional funding subpane).
// Lightweight Charts v5 — API verified against the installed typings:
// createChart / chart.addSeries(Def, opts, paneIndex) / chart.panes()[i].setHeight().
// The required TradingView attribution stays on via layout.attributionLogo.

import {
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  createChart,
  type IChartApi,
  type UTCTimestamp,
} from "lightweight-charts";

import type { FundingRate, OhlcBar } from "./api";

const TOKENS = {
  panel: "#faf8f2",
  text: "#6a6c66",
  line: "#dcd8cd",
  up: "#3f8f5e",
  down: "#c24a41",
  iris: "#6d55c9",
};

function toUtc(ts: string): UTCTimestamp {
  return Math.floor(new Date(ts).getTime() / 1000) as UTCTimestamp;
}

export interface InstrumentChart {
  chart: IChartApi;
  destroy(): void;
}

export function renderInstrumentChart(
  container: HTMLElement,
  bars: OhlcBar[],
  funding: FundingRate[] | null,
): InstrumentChart {
  const chart = createChart(container, {
    autoSize: true,
    layout: {
      attributionLogo: true, // license requirement — do not strip
      background: { color: TOKENS.panel },
      textColor: TOKENS.text,
      fontFamily: "'JetBrains Mono', monospace",
      fontSize: 11,
    },
    grid: {
      vertLines: { color: TOKENS.line, style: 1 },
      horzLines: { color: TOKENS.line, style: 1 },
    },
    rightPriceScale: { borderColor: TOKENS.line },
    timeScale: { borderColor: TOKENS.line, timeVisible: true },
    crosshair: { mode: 0 },
  });

  const candles = chart.addSeries(CandlestickSeries, {
    upColor: TOKENS.up,
    downColor: TOKENS.down,
    wickUpColor: TOKENS.up,
    wickDownColor: TOKENS.down,
    borderVisible: false,
  });
  candles.setData(
    bars.map((b) => ({
      time: toUtc(b.ts),
      open: b.open,
      high: b.high,
      low: b.low,
      close: b.close,
    })),
  );

  // Volume subpane (pane 1). Iris wash — green/red stay reserved for P&L sign.
  const volume = chart.addSeries(
    HistogramSeries,
    { color: "rgba(109,85,201,0.35)", priceFormat: { type: "volume" } },
    1,
  );
  volume.setData(
    bars
      .filter((b) => b.volume !== null)
      .map((b) => ({ time: toUtc(b.ts), value: b.volume as number })),
  );

  // Funding subpane (pane 2) for perps: annualized %, hourly accrual × 24 × 365.
  if (funding && funding.length > 0) {
    const fundingSeries = chart.addSeries(
      LineSeries,
      {
        color: TOKENS.iris,
        lineWidth: 1,
        priceFormat: { type: "custom", formatter: (v: number) => `${v.toFixed(1)}%` },
      },
      2,
    );
    fundingSeries.setData(
      funding.map((f) => ({ time: toUtc(f.ts), value: f.rate * 24 * 365 * 100 })),
    );
  }

  const panes = chart.panes();
  if (panes[1]) panes[1].setHeight(90);
  if (panes[2]) panes[2].setHeight(80);

  chart.timeScale().fitContent();
  return { chart, destroy: () => chart.remove() };
}
