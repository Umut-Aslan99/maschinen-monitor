<script setup lang="ts">
import { computed, ref } from 'vue';
import { bandPath, domain, linear, linePath, nearest, niceTicks, timeTicks, useWidth } from '../chart';
import { dayTime, num, time } from '../format';

/** One signal over time: 2px line, min–max band for aggregated ranges, limit lines, crosshair + tooltip. */
const props = defineProps<{
  t: number[]; avg: (number | null)[]; min?: (number | null)[]; max?: (number | null)[];
  start: number; end: number; label: string; unit: string; decimals: number;
  warn?: number | null; crit?: number | null; height?: number;
}>();

const box = ref<HTMLElement | null>(null);
const width = useWidth(box);
const hover = ref<number | null>(null);
const M = { top: 12, right: 14, bottom: 24, left: 46 };
const H = computed(() => props.height ?? 170);
const aggregated = computed(() => !!props.min && props.min.some((v, i) => v !== null && v !== props.max?.[i]));

const geo = computed(() => {
  const values = [...props.avg, ...(aggregated.value ? [...(props.min ?? []), ...(props.max ?? [])] : [])]
    .filter((v): v is number => v !== null && v !== undefined);
  const limits = [props.warn, props.crit].filter((v): v is number => v !== null && v !== undefined);
  const [lo, hi] = domain([...values, ...limits]);
  const yTicks = niceTicks(lo, hi, 4);
  const y0 = Math.min(lo, yTicks[0] ?? lo);
  const y1 = Math.max(hi, yTicks[yTicks.length - 1] ?? hi);
  const x = linear(props.start, props.end, M.left, width.value - M.right);
  const y = linear(y0, y1, H.value - M.bottom, M.top);
  const xs = props.t.map(x);
  const ys = props.avg.map((v) => (v === null || v === undefined ? null : y(v)));
  return {
    x, y, xs, yTicks,
    xTicks: timeTicks(props.start, props.end, Math.max(2, Math.floor(width.value / 110))),
    line: linePath(xs, ys),
    band: aggregated.value ? bandPath(xs, (props.min ?? []).map((v) => (v === null ? null : y(v))), (props.max ?? []).map((v) => (v === null ? null : y(v)))) : '',
  };
});

const fmtX = (t: number) => (props.end - props.start > 86400 ? dayTime(t * 1000) : time(t * 1000));
const last = computed(() => [...props.avg].reverse().find((v) => v !== null) ?? null);
const summary = computed(() => `${props.label}: zuletzt ${num(last.value, props.decimals)} ${props.unit}`);

function move(e: PointerEvent) {
  if (!props.t.length) return;
  const rect = (e.currentTarget as SVGElement).getBoundingClientRect();
  const px = ((e.clientX - rect.left) / rect.width) * width.value;
  const t = props.start + ((px - M.left) / (width.value - M.left - M.right)) * (props.end - props.start);
  hover.value = nearest(props.t, t);
}
function key(e: KeyboardEvent) {
  if (!props.t.length) return;
  const i = hover.value ?? props.t.length - 1;
  if (e.key === 'ArrowLeft') hover.value = Math.max(0, i - 1);
  else if (e.key === 'ArrowRight') hover.value = Math.min(props.t.length - 1, i + 1);
  else if (e.key === 'Escape') hover.value = null;
  else return;
  e.preventDefault();
}
const tip = computed(() => {
  const i = hover.value;
  if (i === null || props.avg[i] === null || props.avg[i] === undefined) return null;
  const px = geo.value.xs[i] ?? 0;
  return {
    i, x: px, y: geo.value.y(props.avg[i] as number),
    left: px > width.value * 0.6 ? px - 12 : px + 12, alignRight: px > width.value * 0.6,
    when: fmtX(props.t[i] ?? 0), value: props.avg[i] as number,
    range: aggregated.value ? [props.min?.[i], props.max?.[i]] : null,
  };
});
</script>

<template>
  <div ref="box" class="chart-box">
    <svg :height="H" :viewBox="`0 0 ${width} ${H}`" role="img" :aria-label="summary" tabindex="0"
      @pointermove="move" @pointerleave="hover = null" @keydown="key" @blur="hover = null">
      <g>
        <line v-for="v in geo.yTicks" :key="'g' + v" :x1="M.left" :x2="width - M.right" :y1="geo.y(v)" :y2="geo.y(v)" stroke="var(--grid)" stroke-width="1" />
        <text v-for="v in geo.yTicks" :key="'l' + v" class="axis-text" :x="M.left - 8" :y="geo.y(v) + 3.5" text-anchor="end">{{ num(v) }}</text>
        <text v-for="t in geo.xTicks" :key="'x' + t" class="axis-text" :x="geo.x(t)" :y="H - 6" text-anchor="middle">{{ fmtX(t) }}</text>
      </g>
      <g v-for="lim in [{ v: warn, c: 'var(--warning)', n: 'Warnung' }, { v: crit, c: 'var(--critical)', n: 'Kritisch' }]" :key="lim.n">
        <template v-if="lim.v !== null && lim.v !== undefined">
          <line :x1="M.left" :x2="width - M.right" :y1="geo.y(lim.v)" :y2="geo.y(lim.v)" :stroke="lim.c" stroke-width="1" />
          <text class="axis-text" :x="width - M.right" :y="geo.y(lim.v) - 4" text-anchor="end">{{ lim.n }} {{ num(lim.v) }} {{ unit }}</text>
        </template>
      </g>
      <path v-if="geo.band" :d="geo.band" fill="var(--series-1)" fill-opacity="0.1" />
      <path :d="geo.line" fill="none" stroke="var(--series-1)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
      <g v-if="tip">
        <line :x1="tip.x" :x2="tip.x" :y1="M.top" :y2="H - M.bottom" stroke="var(--axis)" stroke-width="1" />
        <circle :cx="tip.x" :cy="tip.y" r="4" fill="var(--series-1)" stroke="var(--surface)" stroke-width="2" />
      </g>
    </svg>
    <div v-if="tip" class="tooltip" :style="{ left: `${tip.left}px`, top: '8px', transform: tip.alignRight ? 'translateX(-100%)' : undefined }" role="status">
      <div class="t-title">{{ tip.when }}</div>
      <div class="t-row"><span class="t-key" style="background: var(--series-1)"></span><b>{{ num(tip.value, decimals) }} {{ unit }}</b><span>{{ label }}</span></div>
      <div v-if="tip.range" class="t-row muted" style="font-size: 0.76rem">Spanne {{ num(tip.range[0] ?? null, decimals) }} – {{ num(tip.range[1] ?? null, decimals) }}</div>
    </div>
  </div>
</template>
