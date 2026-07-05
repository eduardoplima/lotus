// Read-only client for the Lotus API (localhost, proxied by Vite in dev).

export interface InstrumentOut {
  id: number;
  symbol: string;
  sec_type: string;
  exchange: string;
  currency: string;
}

export interface OhlcBar {
  ts: string;
  timeframe: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
  source: string;
  captured_at: string;
  vintage: string;
}

export interface FundingRate {
  ts: string;
  rate: number;
  premium: number | null;
  source: string;
  vintage: string;
}

export interface Hypothesis {
  id: number;
  statement: string;
  baseline: string;
  signal_threshold: string;
  dev_split_def: string;
  kill_test: string;
  kill_criteria: string;
  status: "registered" | "live" | "killed";
  registered_at: string;
  killed_at: string | null;
  kill_reason: string | null;
}

export interface BacktestRun {
  id: number;
  hypothesis_id: number | null;
  strategy: string;
  params: Record<string, unknown>;
  data_window: Record<string, unknown>;
  cost_model: Record<string, unknown>;
  code_version: string;
  created_at: string;
}

export interface BacktestResult {
  id: number;
  run_id: number;
  headline: Record<string, any>;
  stress_windows: Record<string, string>;
  tail: Record<string, any>;
  computed_at: string;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`);
  if (!res.ok) throw new Error(`GET /api${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  instruments: () => get<InstrumentOut[]>("/instruments"),
  bars: (symbol: string, timeframe: string, limit = 5000) =>
    get<OhlcBar[]>(
      `/instruments/${encodeURIComponent(symbol)}/bars?timeframe=${timeframe}&limit=${limit}`,
    ),
  funding: (symbol: string, limit = 2000) =>
    get<FundingRate[]>(`/instruments/${encodeURIComponent(symbol)}/funding?limit=${limit}`),
  hypotheses: () => get<Hypothesis[]>("/hypotheses"),
  cemetery: () => get<Hypothesis[]>("/cemetery"),
  runs: () => get<BacktestRun[]>("/backtest-runs"),
  result: (runId: number) => get<BacktestResult>(`/backtest-runs/${runId}/result`),
  meta: () => get<Record<string, unknown>>("/meta"),
};
