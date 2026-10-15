<script setup lang="ts">
import { onMounted, ref, watch } from 'vue';
import { RouterLink } from 'vue-router';
import { api } from '../api';
import { live } from '../live';
import { duration, when } from '../format';
import { meta } from '../meta';
import ChartFrame from '../components/ChartFrame.vue';
import ClassifyStop from '../components/ClassifyStop.vue';
import ParetoChart from '../components/ParetoChart.vue';
import type { Pareto, Stop } from '../types';

const RANGES = [{ key: 'shift', label: 'Diese Schicht' }, { key: '24h', label: '24 h' }, { key: '7d', label: '7 Tage' }];
const range = ref('7d');
const machine = ref('');
const pareto = ref<Pareto | null>(null);
const open = ref<Stop[]>([]);
const done = ref<string | null>(null);

async function load() {
  [pareto.value, open.value] = await Promise.all([
    api.downtime(range.value, machine.value || undefined),
    api.stops({ unclassified: true }),
  ]);
}
onMounted(load);
watch([range, machine], load);
watch(() => live.stopTick, load);

function classified(stop: Stop, text: string) {
  done.value = `${stop.machine}, ${when(stop.start)}: als „${text}“ zugeordnet.`;
  void load();
}
</script>

<template>
  <div class="page-head">
    <div>
      <p class="eyebrow">Stillstände</p>
      <h1>Warum stehen die Maschinen?</h1>
      <p class="muted">Stillstandszeit nach Grund, größter Verlust zuerst (Pareto). Ungeklärte Stillstände ordnet der Bediener nachträglich
        zu – erst dann taugen die Zahlen für Entscheidungen.</p>
    </div>
  </div>

  <div class="toolbar">
    <div class="segmented" role="group" aria-label="Zeitraum">
      <button v-for="r in RANGES" :key="r.key" type="button" :aria-pressed="range === r.key" @click="range = r.key">{{ r.label }}</button>
    </div>
    <select v-model="machine" class="select" aria-label="Maschine" data-testid="pareto-machine">
      <option value="">Alle Maschinen</option>
      <option v-for="m in meta.machines" :key="m.id" :value="m.id">{{ m.id }} · {{ m.name }}</option>
    </select>
  </div>

  <ChartFrame v-if="pareto" data-tour="pareto" title="Stillstandszeit nach Grund" :sub="`${machine || 'Alle Maschinen'} · ${RANGES.find((r) => r.key === range)?.label}`">
    <ParetoChart :data="pareto" />
    <template #table>
      <table class="data"><thead><tr><th>Grund</th><th class="right">Anzahl</th><th class="right">Minuten</th><th class="right">Anteil</th><th class="right">Kumuliert</th></tr></thead>
        <tbody><tr v-for="i in pareto.items" :key="i.reason"><td>{{ i.text }}</td><td class="right num">{{ i.count }}</td><td class="right num">{{ i.min }}</td>
          <td class="right num">{{ i.share }} %</td><td class="right num">{{ i.cumulative }} %</td></tr></tbody></table>
    </template>
  </ChartFrame>

  <h2 class="section">Ungeklärte Stillstände (24 h)</h2>
  <p v-if="done" class="alert alert-ok" role="status" style="margin-bottom: 12px">{{ done }}</p>
  <section class="card panel">
    <ul class="list" data-testid="unclassified" data-tour="unclassified">
      <li v-for="s in open" :key="s.machine + s.start" style="flex-wrap: wrap">
        <RouterLink class="mono" :to="`/maschine/${s.machine}`">{{ s.machine }}</RouterLink>
        <span class="grow">{{ when(s.start) }} · {{ s.open ? 'läuft seit ' : '' }}{{ duration(s.min) }}</span>
        <ClassifyStop :machine="s.machine" :start="s.start" @done="(text) => classified(s, text)" />
      </li>
      <li v-if="!open.length" class="muted">Alle Stillstände der letzten 24 Stunden sind zugeordnet.</li>
    </ul>
  </section>
</template>
