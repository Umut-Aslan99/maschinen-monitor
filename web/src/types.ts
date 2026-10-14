// Mirrors the JSON of the FastAPI backend (monitor/store.py).

export type StateCode = 'run' | 'down' | 'setup' | 'planned' | 'off';
export type Severity = 'warning' | 'critical';

export interface SignalMeta { key: string; label: string; unit: string; warn: number | null; crit: number | null; decimals: number }
export interface MachineMeta { id: string; name: string; kind: string; cycleS: number; shifts: string[]; signals: SignalMeta[] }
export interface Meta {
  machines: MachineMeta[];
  reasons: { code: string; text: string; kind: 'unplanned' | 'setup' | 'planned' }[];
  classifiable: string[];
  states: Record<StateCode, string>;
  injectable: string[];
  pushKey: string | null;
}

export interface OeeView {
  oee: number | null; availability: number | null; performance: number | null; quality: number | null;
  plannedMin: number; runMin: number; downMin: number; setupMin: number; good: number; scrap: number; target: number;
  lossMin: { availability: number; performance: number; quality: number };
}
export interface ShiftView { code: string; label: string; start: string; end: string }

export interface MachineCard {
  id: string; name: string; kind: string; state: StateCode | null; reason: string | null; since: string | null;
  values: Record<string, number>; oee: OeeView; alarms: number; critical: boolean;
  spark: { signal: string; points: number[] };
}
export interface Overview {
  now: string; shift: ShiftView;
  hall: { oee: number | null; running: number; machines: number; alarms: number; unclassified: number };
  machines: MachineCard[];
}

export interface Stop {
  machine: string; start: string; end: string; state: StateCode; reason: string | null; text: string;
  min: number; classified: boolean; open: boolean;
}
export interface Alarm {
  id: number; machine: string; machineName: string; code: string; source: 'machine' | 'rule'; severity: Severity;
  text: string; raisedAt: string; clearedAt: string | null; ackedAt: string | null;
}
export interface MachineDetail {
  id: string; name: string; kind: string; cycleS: number; shifts: string[];
  state: StateCode | null; reason: string | null; since: string | null; values: Record<string, number>;
  shift: ShiftView; oee: OeeView;
  losses: { reason: string; text: string; kind: string; min: number }[];
  history: { shift: ShiftView; oee: number | null; availability: number | null; performance: number | null; quality: number | null }[];
  stops: Stop[]; alarms: Alarm[];
}
export interface Interval { start: string; end: string; state: StateCode; reason: string | null }
export interface Series {
  range: RangeKey; start: string; end: string; t: number[];
  signals: Record<string, { avg: (number | null)[]; min: (number | null)[]; max: (number | null)[] }>;
  timeline: Interval[];
}
export type RangeKey = '15m' | '8h' | '24h' | '7d';
export interface Pareto {
  start: string; end: string; machine: string | null;
  items: { reason: string; text: string; kind: string; count: number; min: number; share: number; cumulative: number }[];
}
