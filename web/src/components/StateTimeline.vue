<script setup lang="ts">
import { computed, ref } from 'vue';
import { linear, timeTicks, useWidth } from '../chart';
import { dayTime, duration, time } from '../format';
import { STATE_ICON, reasonText, stateLabel } from '../meta';
import type { Interval, StateCode } from '../types';

/** Machine states as a strip over time – one segment per state interval, 2px surface gaps between them. */
const props = defineProps<{ intervals: Interval[]; start: number; end: number }>();
const box = ref<HTMLElement | null>(null);
const width = useWidth(box);
const hover = ref<number | null>(null);
const H = 30;
const M = { left: 2, right: 2 };
const ORDER: StateCode[] = ['run', 'down', 'setup', 'planned', 'off'];

const geo = computed(() => {
  const x = linear(props.start, props.end, M.left, width.value - M.right);
  const rects = props.intervals.map((iv, i) => {
    const a = Math.max(Date.parse(iv.start) / 1000, props.start);
    const b = Math.min(Date.parse(iv.end) / 1000, props.end);
    const x0 = x(a);
    const w = Math.max(x(b) - x0 - 2, 1);
    return { i, x: x0, w, iv, minutes: (b - a) / 60 };
  }).filter((r) => r.minutes > 0);
  return { x, rects, ticks: timeTicks(props.start, props.end, Math.max(2, Math.floor(width.value / 110))) };
});
const fmt = (t: number) => (props.end - props.start > 86400 ? dayTime(t * 1000) : time(t * 1000));
const present = computed(() => ORDER.filter((s) => props.intervals.some((iv) => iv.state === s)));
const tip = computed(() => {
  const r = hover.value === null ? undefined : geo.value.rects.find((x) => x.i === hover.value);
  if (!r) return null;
  const mid = r.x + r.w / 2;
  return { r, left: Math.min(Math.max(mid, 80), width.value - 80) };
});
</script>

<template>
  <div ref="box" class="chart-box">
    <svg :height="H + 22" :viewBox="`0 0 ${width} ${H + 22}`" role="img" :aria-label="`Zustandsverlauf mit ${geo.rects.length} Abschnitten`">
      <rect v-for="r in geo.rects" :key="r.i" :x="r.x" y="0" :width="r.w" :height="H" rx="2" :data-s="r.iv.state"
        fill="var(--st)" tabindex="0" :aria-label="`${stateLabel(r.iv.state)} ${reasonText(r.iv.reason)} ${duration(r.minutes)}`"
        @pointerenter="hover = r.i" @pointerleave="hover = null" @focus="hover = r.i" @blur="hover = null" />
      <text v-for="t in geo.ticks" :key="t" class="axis-text" :x="geo.x(t)" :y="H + 16" text-anchor="middle">{{ fmt(t) }}</text>
    </svg>
    <div v-if="tip" class="tooltip" :style="{ left: `${tip.left}px`, top: `${H + 6}px`, transform: 'translateX(-50%)' }" role="status">
      <div class="t-title">{{ fmt(Date.parse(tip.r.iv.start) / 1000) }} – {{ fmt(Date.parse(tip.r.iv.end) / 1000) }}</div>
      <div class="t-row"><span class="t-key box" :data-s="tip.r.iv.state" style="background: var(--st)"></span>
        <b>{{ duration(tip.r.minutes) }}</b><span>{{ stateLabel(tip.r.iv.state) }}<template v-if="tip.r.iv.reason && tip.r.iv.state !== 'off'"> · {{ reasonText(tip.r.iv.reason) }}</template></span></div>
    </div>
    <div class="legend timeline-legend">
      <span v-for="s in present" :key="s"><i class="box" :data-s="s" style="background: var(--st)"></i>{{ STATE_ICON[s] }} {{ stateLabel(s) }}</span>
    </div>
  </div>
</template>
