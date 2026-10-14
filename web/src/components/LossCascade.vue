<script setup lang="ts">
import { computed } from 'vue';
import { pct } from '../format';
import type { OeeView } from '../types';

/** From planned time to value-adding time: where the shift's minutes went (a horizontal waterfall). */
const props = defineProps<{ oee: OeeView }>();
const rows = computed(() => {
  const o = props.oee;
  const planned = Math.max(o.plannedMin, 1);
  const afterA = o.plannedMin - o.lossMin.availability;
  const afterP = afterA - o.lossMin.performance;
  const valuable = Math.max(afterP - o.lossMin.quality, 0);
  const s = (v: number) => (v / planned) * 100;
  return [
    { label: 'Geplante Produktionszeit', from: 0, to: s(o.plannedMin), min: o.plannedMin, loss: false, hint: 'Schichtzeit ohne Pausen' },
    { label: 'Verfügbarkeitsverluste', from: s(afterA), to: s(o.plannedMin), min: o.lossMin.availability, loss: true, hint: 'Störungen und Rüsten' },
    { label: 'Leistungsverluste', from: s(afterP), to: s(afterA), min: o.lossMin.performance, loss: true, hint: 'langsamer als Idealtakt, Kurzstopps' },
    { label: 'Qualitätsverluste', from: s(valuable), to: s(afterP), min: o.lossMin.quality, loss: true, hint: 'Zeit für Ausschussteile' },
    { label: 'Wertschöpfende Zeit', from: 0, to: s(valuable), min: Math.round(valuable), loss: false, hint: `entspricht OEE ${pct(o.oee)}` },
  ];
});
</script>

<template>
  <div class="legend">
    <span><i class="box" style="background: var(--series-1)"></i>Zeit</span>
    <span><i class="box" style="background: var(--series-2)"></i>Verlust</span>
  </div>
  <div class="hbars" role="list">
    <div v-for="r in rows" :key="r.label" class="hbar" role="listitem">
      <span>{{ r.label }}<small class="hint">{{ r.hint }}</small></span>
      <span class="track">
        <span class="bar" :class="{ float: r.loss }"
          :style="{ left: `${r.from}%`, width: `${Math.max(r.to - r.from, 0)}%`, background: r.loss ? 'var(--series-2)' : 'var(--series-1)' }"></span>
      </span>
      <span class="val">{{ r.loss ? '−' : '' }}{{ r.min }} min</span>
    </div>
  </div>
</template>
