// Typed client for the localhost FastAPI backend (reached via the Vite proxy).

export interface OhlcBar {
  ts: string; // ISO datetime
  timeframe: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
  source: string;
  captured_at: string;
}

export async function fetchBars(symbol: string, timeframe = "1d"): Promise<OhlcBar[]> {
  const res = await fetch(
    `/api/instruments/${encodeURIComponent(symbol)}/bars?timeframe=${timeframe}`,
  );
  // 404 = instrument not ingested yet. That is an empty state, not an error:
  // return [] so the UI can show the friendly "run the ingest" hint.
  if (res.status === 404) {
    return [];
  }
  if (!res.ok) {
    throw new Error(`bars request failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as OhlcBar[];
}
