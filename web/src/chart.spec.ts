import { bandPath, domain, linePath, nearest, niceTicks, timeTicks } from './chart';

describe('chart helpers', () => {
  it('finds round ticks', () => {
    expect(niceTicks(0, 100, 4)).toEqual([0, 25, 50, 75, 100]);
    expect(niceTicks(36.2, 61.7, 4)).toEqual([40, 50, 60]);
  });

  it('pads the domain and keeps positive data above zero', () => {
    const [zero, top] = domain([0, 62]);
    expect(zero).toBe(0);
    expect(top).toBeCloseTo(66.96);
    expect(domain([])).toEqual([0, 1]);
    const [lo, hi] = domain([50, 50]);
    expect(lo).toBeLessThan(50);
    expect(hi).toBeGreaterThan(50);
  });

  it('puts time ticks on round Berlin times', () => {
    // 14 Oct 2026 10:03:20 CEST → ticks every 5 min from 10:05
    const start = Date.UTC(2026, 9, 14, 8, 3, 20) / 1000;
    const ticks = timeTicks(start, start + 900, 6);
    const fmt = (t: number) => new Intl.DateTimeFormat('de-DE', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Berlin' }).format(t * 1000);
    expect(ticks.map(fmt)).toEqual(['10:05', '10:10', '10:15']);
  });

  it('day ticks fall on Berlin midnight', () => {
    const start = Date.UTC(2026, 9, 7, 9) / 1000;
    const ticks = timeTicks(start, start + 7 * 86400, 8);
    const hours = ticks.map((t) => new Intl.DateTimeFormat('en-GB', { hour: '2-digit', hourCycle: 'h23', timeZone: 'Europe/Berlin' }).format(t * 1000));
    expect(new Set(hours)).toEqual(new Set(['00']));
  });

  it('finds the nearest sample', () => {
    expect(nearest([10, 20, 30], 24)).toBe(1);
    expect(nearest([10, 20, 30], 26)).toBe(2);
    expect(nearest([10], 99)).toBe(0);
  });

  it('breaks lines at missing values', () => {
    expect(linePath([0, 1, 2, 3], [5, null, 7, 8])).toBe('M0.0,5.0M2.0,7.0L3.0,8.0');
    expect(bandPath([0, 1], [1, 2], [3, 4])).toBe('M0.0,3.0L1.0,4.0L1.0,2.0L0.0,1.0Z');
  });
});
