import { duration, pct } from './format';

describe('format', () => {
  it('formats percentages the German way', () => {
    expect(pct(64.7)).toBe('64,7 %');
    expect(pct(null)).toBe('–');
  });

  it('formats durations', () => {
    expect(duration(47)).toBe('47 min');
    expect(duration(65)).toBe('1 h 05 min');
    expect(duration(3 * 1440 + 125)).toBe('3 d 2 h');
  });
});
