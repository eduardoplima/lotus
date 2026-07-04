// One candlestick chart per instrument tile (§11: createChart per container).

import {
  CandlestickSeries,
  createChart,
  type CandlestickData,
  type IChartApi,
  type UTCTimestamp,
} from "lightweight-charts";

import type { OhlcBar } from "./api";

export function createCandleTile(container: HTMLElement): IChartApi {
  const chart = createChart(container, {
    autoSize: true,
    layout: {
      // attributionLogo keeps the required TradingView mark visible (§11).
      attributionLogo: true,
      background: { color: "#161b22" },
      textColor: "#8b949e",
    },
    grid: {
      vertLines: { color: "#21262d" },
      horzLines: { color: "#21262d" },
    },
    rightPriceScale: { borderColor: "#21262d" },
    timeScale: { borderColor: "#21262d" },
  });
  return chart;
}

export function setCandleData(chart: IChartApi, bars: OhlcBar[]): void {
  const series = chart.addSeries(CandlestickSeries, {
    upColor: "#26a69a",
    downColor: "#ef5350",
    borderVisible: false,
    wickUpColor: "#26a69a",
    wickDownColor: "#ef5350",
  });

  const data: CandlestickData[] = bars.map((b) => ({
    time: (Date.parse(b.ts) / 1000) as UTCTimestamp,
    open: b.open,
    high: b.high,
    low: b.low,
    close: b.close,
  }));

  series.setData(data);
  chart.timeScale().fitContent();
}
