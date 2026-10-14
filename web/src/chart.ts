import { onBeforeUnmount, onMounted, ref, type Ref } from 'vue';

/** Container width, kept current with a ResizeObserver – charts draw in real pixels so strokes stay 2px. */
export function useWidth(el: Ref<HTMLElement | null>, fallback = 600) {
  const width = ref(fallback);
  let ro: ResizeObserver | undefined;
  onMounted(() => {
    if (!el.value) return;
    width.value = el.value.clientWidth || fallback;
    if (typeof ResizeObserver !== 'undefined') {
      ro = new ResizeObserver(([e]) => { if (e) width.value = Math.max(e.contentRect.width, 120); });
      ro.observe(el.value);
    }
  });
  onBeforeUnmount(() => ro?.disconnect());
  return width;
}

export function linear(d0: number, d1: number, r0: number, r1: number) {
  const k = d1 === d0 ? 0 : (r1 - r0) / (d1 - d0);
  return (v: number) => r0 + (v - d0) * k;
}

/** About `count` round tick values covering [lo, hi]. */
export function niceTicks(lo: number, hi: number, count = 4): number[] {
  if (!(hi > lo)) return [lo];
  const raw = (hi - lo) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = ([1, 2, 2.5, 5, 10].map((f) => f * mag).find((s) => s >= raw) ?? 10 * mag);
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(+v.toFixed(10));
  return out;
}

/** Padded domain containing all values (and reference lines). */
export function domain(values: number[], pad = 0.08): [number, number] {
  if (!values.length) return [0, 1];
  let lo = Math.min(...values);
  let hi = Math.max(...values);
  if (hi === lo) { lo -= 1; hi += 1; }
  const p = (hi - lo) * pad;
  return [lo >= 0 && lo - p < 0 ? 0 : lo - p, hi + p];
}

const STEPS = [60, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400];
const berlinOffset = (t: number) => {
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Berlin', timeZoneName: 'longOffset' }).formatToParts(new Date(t * 1000));
  const m = /GMT([+-])(\d{2}):(\d{2})/.exec(parts.find((p) => p.type === 'timeZoneName')?.value ?? '');
  return m ? (m[1] === '-' ? -1 : 1) * (Number(m[2]) * 3600 + Number(m[3]) * 60) : 0;
};

/** Time ticks (unix seconds) on round local (Berlin) times – at most `max` of them. */
export function timeTicks(start: number, end: number, max = 6): number[] {
  const step = STEPS.find((s) => (end - start) / s <= max) ?? 86400 * Math.ceil((end - start) / 86400 / max);
  const off = berlinOffset(start);
  const out: number[] = [];
  for (let t = Math.ceil((start + off) / step) * step - off; t <= end; t += step) out.push(t);
  return out;
}

/** Index of the sample closest to time x (t sorted ascending). */
export function nearest(t: number[], x: number): number {
  let lo = 0;
  let hi = t.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if ((t[mid] ?? 0) < x) lo = mid; else hi = mid;
  }
  return Math.abs((t[lo] ?? 0) - x) <= Math.abs((t[hi] ?? 0) - x) ? lo : hi;
}

/** SVG path through the points, broken where a value is missing. */
export function linePath(xs: number[], ys: (number | null)[]): string {
  let d = '';
  let pen = false;
  ys.forEach((y, i) => {
    if (y === null || y === undefined) { pen = false; return; }
    d += `${pen ? 'L' : 'M'}${(xs[i] ?? 0).toFixed(1)},${y.toFixed(1)}`;
    pen = true;
  });
  return d;
}

/** Closed band between lower and upper values (min/max of aggregated buckets). */
export function bandPath(xs: number[], lo: (number | null)[], hi: (number | null)[]): string {
  const idx = xs.map((_, i) => i).filter((i) => lo[i] != null && hi[i] != null);
  if (idx.length < 2) return '';
  const top = idx.map((i) => `${(xs[i] ?? 0).toFixed(1)},${(hi[i] as number).toFixed(1)}`);
  const bottom = idx.reverse().map((i) => `${(xs[i] ?? 0).toFixed(1)},${(lo[i] as number).toFixed(1)}`);
  return `M${top.join('L')}L${bottom.join('L')}Z`;
}
