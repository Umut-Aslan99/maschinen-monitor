import { handle, live, onTelemetry } from './live';

describe('live store', () => {
  it('applies state changes and counts them', () => {
    const before = live.stateTick;
    handle({ type: 'state', machine: 'CNC-01', ts: '2026-10-14T10:00:00Z', state: 'down', reason: 'WZB' });
    expect(live.machines['CNC-01']).toMatchObject({ state: 'down', reason: 'WZB', since: '2026-10-14T10:00:00Z' });
    expect(live.stateTick).toBe(before + 1);
  });

  it('passes telemetry to listeners until they unsubscribe', () => {
    const seen: string[] = [];
    const off = onTelemetry((m, ts) => seen.push(`${m}@${ts}`));
    handle({ type: 'telemetry', machine: 'SGM-01', ts: 't1', values: { oil_temp: 48 } });
    off();
    handle({ type: 'telemetry', machine: 'SGM-01', ts: 't2', values: { oil_temp: 49 } });
    expect(seen).toEqual(['SGM-01@t1']);
    expect(live.machines['SGM-01']?.values).toEqual({ oil_temp: 49 });
  });

  it('shows a toast for critical alarms only and keeps at most three', () => {
    live.toasts = [];
    handle({ type: 'alarm', alarm: { machine: 'KAN-01', text: 'Öltemperatur erhöht', severity: 'warning' } });
    expect(live.toasts).toHaveLength(0);
    for (let i = 0; i < 4; i++) handle({ type: 'alarm', alarm: { machine: 'SGM-01', text: `Hydraulik ${i}`, severity: 'critical' } });
    expect(live.toasts.map((t) => t.text)).toEqual(['Hydraulik 1', 'Hydraulik 2', 'Hydraulik 3']);
  });
});
