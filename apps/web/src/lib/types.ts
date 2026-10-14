export type Bar = { t: number; o: number; h: number; l: number; c: number; v: number; vw: number | null };

export type ClockState = {
  cursor_ts: number;
  index: number;
  total: number;
  speed: number;
  status: "paused" | "playing" | "finished";
};

export type Position = {
  symbol: string;
  asset_class: "stock" | "option";
  qty: number;
  avg_cost: number;
  last: number | null;
  market_value: number;
  unrealized_pnl: number;
  realized_pnl: number;
};

export type Account = {
  cash: number;
  equity: number;
  buying_power: number;
  realized_pnl: number;
  unrealized_pnl: number;
  positions: Position[];
};

export type Order = {
  id: string;
  symbol: string;
  asset_class: "stock" | "option";
  side: "buy" | "sell";
  qty: number;
  type: "market" | "limit" | "stop";
  limit_price: number | null;
  stop_price: number | null;
  take_profit: number | null;
  stop_loss: number | null;
  status: "open" | "filled" | "canceled" | "rejected";
  parent_id: string | null;
  tag: string | null;
  reason: string | null;
  created_ts: number | null;
  filled_ts: number | null;
  fill_price: number | null;
};

export type Fill = {
  order_id: string;
  symbol: string;
  side: "buy" | "sell";
  qty: number;
  price: number;
  commission: number;
  t: number;
  price_source: "real" | "stale" | "model" | "settlement";
};

export type Snapshot = {
  session: { id: string; symbol: string; starting_cash: number };
  state: ClockState;
  bars: Bar[];
  account: Account;
  orders: Order[];
  fills: Fill[];
};

export type ReplayEvent =
  | ({ type: "snapshot" } & Snapshot)
  | ({ type: "reset" } & Snapshot)
  | { type: "tick"; bar: Bar; state: ClockState; account: Account; fills: Fill[]; orders: Order[] | null }
  | { type: "state"; state: ClockState }
  | { type: "orders"; orders: Order[]; account?: Account }
  | { type: "error"; message: string };

export type OptionQuote = {
  symbol: string;
  underlying: string;
  expiry: string;
  right: "C" | "P";
  strike: number;
  price: number;
  iv: number;
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
  source: "real" | "model";
};

export type Chain = {
  spot: number;
  as_of: number;
  expiries: string[];
  expiry: string;
  atm_iv: number;
  real_contracts: number;
  rows: { strike: number; call: OptionQuote; put: OptionQuote }[];
};

export type SessionSummary = {
  id: string;
  symbol: string;
  start_date: string;
  end_date: string;
  status: string;
  speed: number;
  cursor_ts: number | null;
  starting_cash: number;
  equity: number | null;
  created_at: string;
};

export type JsonSchemaProp = {
  type?: "integer" | "number" | "boolean" | "string";
  title?: string;
  description?: string;
  default?: unknown;
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  exclusiveMaximum?: number;
};

export type StrategyInfo = {
  name: string;
  label: string;
  description: string;
  uses_options: boolean;
  params: { properties: Record<string, JsonSchemaProp> };
};

export type Metrics = {
  starting_equity: number;
  final_equity: number;
  net_pnl: number;
  total_return: number;
  cagr: number | null;
  max_drawdown: number;
  max_drawdown_duration_s: number;
  sharpe: number | null;
  sortino: number | null;
  trades: number;
  win_rate: number | null;
  profit_factor: number | null;
  expectancy: number | null;
  avg_win: number | null;
  avg_loss: number | null;
  largest_win: number | null;
  largest_loss: number | null;
  exposure: number;
  trading_days: number;
};

export type BacktestRun = {
  id: string;
  strategy: string;
  symbol: string;
  start_date: string;
  end_date: string;
  starting_cash: number;
  params: Record<string, unknown>;
  status: "queued" | "running" | "done" | "failed";
  progress: number;
  error: string | null;
  metrics: Metrics | null;
  created_at: string;
  finished_at: string | null;
};

export type Trade = {
  id: number;
  symbol: string;
  direction: "long" | "short";
  qty: number;
  entry_t: number;
  exit_t: number;
  entry_price: number;
  exit_price: number;
  pnl: number;
  commission: number;
  has_note: boolean;
};

export type GroupStat = { key: string; pnl: number; count: number; win_rate: number };

export type Analytics = {
  metrics: Metrics;
  equity: { t: number; equity: number }[];
  drawdown: { t: number; dd: number }[];
  histogram: { from: number; to: number; count: number }[];
  by_time_of_day: GroupStat[];
  by_weekday: GroupStat[];
  heatmap: { weekday: string; bucket: string; pnl: number; count: number }[];
  trades: Trade[];
};

export type Note = {
  id: number;
  title: string;
  body: string;
  tags: string[];
  trade_id: number | null;
  session_id: string | null;
  run_id: string | null;
  screenshot: string | null;
  created_at: string;
  updated_at: string;
  trade: (Omit<Trade, "id" | "commission" | "has_note">) | null;
};

export type DataStatus = {
  alpaca_configured: boolean;
  bars: { symbol: string; source: string; first: string; last: string; bars: number; days: number }[];
  iv: { index: string; first: string; last: string; days: number }[];
  options: { underlying: string; contracts: number; bars: number; first: string; last: string }[];
};

export type JobStatus = {
  job_id: string;
  status: "deferred" | "queued" | "in_progress" | "complete" | "not_found";
  progress?: string;
  message?: string;
  success?: boolean;
  result?: unknown;
};
