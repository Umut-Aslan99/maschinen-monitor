import { reactive } from 'vue';
import type { Overview, StateCode } from './types';

interface MachineLive { state: StateCode | null; reason: string | null; since: string | null; values: Record<string, number> }
interface Toast { id: number; machine: string; text: string; critical: boolean }
type TelemetryListener = (machine: string, ts: string, values: Record<string, number>) => void;

/** Everything the server pushes over the WebSocket. Pages read it reactively; ticks tell them to refetch. */
export const live = reactive({
  connected: false,
  machines: {} as Record<string, MachineLive>,
  overview: null as Overview | null,
  alarmTick: 0,
  stopTick: 0,
  stateTick: 0,
  toasts: [] as Toast[],
});

const listeners = new Set<TelemetryListener>();
export function onTelemetry(fn: TelemetryListener) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

let socket: WebSocket | undefined;
let retry = 1000;
let toastId = 0;

export function connect() {
  if (socket || typeof WebSocket === 'undefined') return;
  socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/live`);
  socket.onopen = () => { live.connected = true; retry = 1000; };
  socket.onclose = () => {
    live.connected = false;
    socket = undefined;
    setTimeout(connect, retry);
    retry = Math.min(retry * 2, 15000);
  };
  socket.onmessage = (e) => handle(JSON.parse(e.data as string));
}

export function handle(msg: Record<string, any>) {
  switch (msg.type) {
    case 'hello':
      for (const [id, m] of Object.entries(msg.machines as Record<string, MachineLive>)) live.machines[id] = m;
      break;
    case 'telemetry': {
      const m = (live.machines[msg.machine] ??= { state: null, reason: null, since: null, values: {} });
      m.values = msg.values;
      for (const fn of listeners) fn(msg.machine, msg.ts, msg.values);
      break;
    }
    case 'state': {
      const m = (live.machines[msg.machine] ??= { state: null, reason: null, since: null, values: {} });
      Object.assign(m, { state: msg.state, reason: msg.reason, since: msg.ts });
      live.stateTick++;
      break;
    }
    case 'alarm':
      live.alarmTick++;
      if (msg.alarm.severity === 'critical') toast(msg.alarm.machine, msg.alarm.text, true);
      break;
    case 'alarm-cleared':
    case 'acked':
      live.alarmTick++;
      break;
    case 'classified':
      live.stopTick++;
      break;
    case 'overview':
      live.overview = msg.data;
      break;
  }
}

function toast(machine: string, text: string, critical: boolean) {
  const id = ++toastId;
  live.toasts = [...live.toasts.slice(-2), { id, machine, text, critical }];
  setTimeout(() => { live.toasts = live.toasts.filter((t) => t.id !== id); }, 7000);
}
