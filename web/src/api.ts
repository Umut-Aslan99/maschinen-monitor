import type { Alarm, MachineDetail, Meta, Overview, Pareto, RangeKey, Series, Stop } from './types';

/** The server said no; `message` is written for the user (German). */
export class ApiError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

async function call<T>(method: string, url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().then((j: { detail?: unknown }) => j.detail, () => undefined);
    throw new ApiError(typeof detail === 'string' ? detail : 'Das hat nicht geklappt.', res.status);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const api = {
  meta: () => call<Meta>('GET', '/api/meta'),
  overview: () => call<Overview>('GET', '/api/overview'),
  machine: (id: string) => call<MachineDetail>('GET', `/api/machines/${encodeURIComponent(id)}`),
  series: (id: string, range: RangeKey) => call<Series>('GET', `/api/machines/${encodeURIComponent(id)}/series?range=${range}`),
  fault: (id: string, reason: string) => call<{ text: string }>('POST', `/api/machines/${encodeURIComponent(id)}/fault`, { reason }),
  downtime: (range: string, machine?: string) =>
    call<Pareto>('GET', `/api/downtime?range=${range}${machine ? `&machine=${encodeURIComponent(machine)}` : ''}`),
  stops: (opts: { unclassified?: boolean; machine?: string } = {}) => {
    const q = new URLSearchParams();
    if (opts.unclassified) q.set('unclassified', 'true');
    if (opts.machine) q.set('machine', opts.machine);
    return call<Stop[]>('GET', `/api/stops?${q}`);
  },
  classify: (machine: string, start: string, reason: string) =>
    call<{ text: string }>('PUT', `/api/stops/${encodeURIComponent(machine)}/${encodeURIComponent(start)}`, { reason }),
  alarms: (open = false) => call<Alarm[]>('GET', `/api/alarms${open ? '?open=true' : ''}`),
  ack: (id: number) => call<{ id: number }>('POST', `/api/alarms/${id}/ack`),
  pushSubscribe: (sub: PushSubscriptionJSON) => call<{ ok: boolean }>('POST', '/api/push', sub),
  pushUnsubscribe: (endpoint: string) => call<void>('DELETE', `/api/push?endpoint=${encodeURIComponent(endpoint)}`),
};
