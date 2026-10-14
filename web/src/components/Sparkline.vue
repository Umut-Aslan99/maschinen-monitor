<script setup lang="ts">
import { computed, ref } from 'vue';
import { domain, linear, linePath, useWidth } from '../chart';

const props = defineProps<{ points: number[]; label: string }>();
const box = ref<HTMLElement | null>(null);
const width = useWidth(box, 200);
const H = 34;
const geo = computed(() => {
  const [lo, hi] = domain(props.points, 0.12);
  const x = linear(0, Math.max(props.points.length - 1, 1), 4, width.value - 6);
  const y = linear(lo, hi, H - 5, 5);
  const xs = props.points.map((_, i) => x(i));
  const ys = props.points.map((v) => y(v));
  return { path: linePath(xs, ys), end: xs.length ? { x: xs[xs.length - 1] ?? 0, y: ys[ys.length - 1] ?? 0 } : null };
});
</script>

<template>
  <div ref="box" class="chart-box">
    <svg :height="H" :viewBox="`0 0 ${width} ${H}`" role="img" :aria-label="label">
      <path :d="geo.path" fill="none" stroke="var(--series-1)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
      <circle v-if="geo.end" :cx="geo.end.x" :cy="geo.end.y" r="4" fill="var(--series-1)" stroke="var(--surface)" stroke-width="2" />
    </svg>
  </div>
</template>
