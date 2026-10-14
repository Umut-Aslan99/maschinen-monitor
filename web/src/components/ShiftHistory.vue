<script setup lang="ts">
import { computed, ref } from 'vue';
import { linear, useWidth } from '../chart';
import { day, pct } from '../format';
import type { MachineDetail } from '../types';

/** OEE per shift over the last week – "Kennzahlen nicht erst am Monatsende". */
const props = defineProps<{ history: MachineDetail['history'] }>();
const box = ref<HTMLElement | null>(null);
const width = useWidth(box);
const hover = ref<number | null>(null);
const H = 180;
const M = { top: 10, right: 6, bottom: 30, left: 38 };
const geo = computed(() => {
  const n = Math.max(props.history.length, 1);
  const band = (width.value - M.left - M.right) / n;
  const bw = Math.min(24, band * 0.7);
  const y = linear(0, 100, H - M.bottom, M.top);
  const bars = props.history.map((h, i) => {
    const v = h.oee ?? 0;
    const x = M.left + band * i + (band - bw) / 2;
    return { i, x, w: bw, y: y(v), h: y(0) - y(v), item: h, cx: M.left + band * i + band / 2 };
  });
  return { y, bars, every: Math.ceil(n / Math.max(2, Math.floor(width.value / 70))) };
});
const label = (code: string) => ({ F: 'F', S: 'S', N: 'N' })[code] ?? code;
const barPath = (x: number, y: number, w: number, h: number) => {
  const r = Math.min(4, h, w / 2);
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
};
const tip = computed(() => (hover.value === null ? null : geo.value.bars[hover.value] ?? null));
</script>

<template>
  <div ref="box" class="chart-box">
    <svg :height="H" :viewBox="`0 0 ${width} ${H}`" role="img" :aria-label="`OEE je Schicht, ${history.length} Schichten`">
      <g v-for="v in [0, 25, 50, 75, 100]" :key="v">
        <line :x1="M.left" :x2="width - M.right" :y1="geo.y(v)" :y2="geo.y(v)" stroke="var(--grid)" stroke-width="1" />
        <text class="axis-text" :x="M.left - 8" :y="geo.y(v) + 3.5" text-anchor="end">{{ v }} %</text>
      </g>
      <g v-for="b in geo.bars" :key="b.i" tabindex="0" :aria-label="`${b.item.shift.label}: OEE ${pct(b.item.oee)}`"
        @pointerenter="hover = b.i" @pointerleave="hover = null" @focus="hover = b.i" @blur="hover = null">
        <rect :x="b.cx - (b.w + 12) / 2" :y="M.top" :width="b.w + 12" :height="H - M.top - M.bottom" fill="transparent" />
        <path v-if="b.h > 0" :d="barPath(b.x, b.y, b.w, b.h)" fill="var(--series-1)" :fill-opacity="hover === null || hover === b.i ? 1 : 0.55" />
        <text v-if="b.i % geo.every === 0" class="axis-text" :x="b.cx" :y="H - 16" text-anchor="middle">{{ day(b.item.shift.start).slice(0, 2) }} {{ label(b.item.shift.code) }}</text>
      </g>
    </svg>
    <div v-if="tip" class="tooltip" :style="{ left: `${tip.cx}px`, top: '0', transform: tip.cx > width * 0.6 ? 'translateX(-100%)' : undefined }" role="status">
      <div class="t-title">{{ tip.item.shift.label }}</div>
      <div class="t-row"><span class="t-key box" style="background: var(--series-1)"></span><b>{{ pct(tip.item.oee) }}</b><span>OEE</span></div>
      <div class="t-row muted" style="font-size: 0.76rem">V {{ pct(tip.item.availability) }} · L {{ pct(tip.item.performance) }} · Q {{ pct(tip.item.quality) }}</div>
    </div>
  </div>
</template>
