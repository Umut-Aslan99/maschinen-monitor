<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { RouterLink } from 'vue-router';
import { api } from '../api';
import { live } from '../live';
import { int, num, pct } from '../format';
import { signalMeta } from '../meta';
import StateBadge from '../components/StateBadge.vue';
import Sparkline from '../components/Sparkline.vue';
import type { Overview } from '../types';

const data = ref<Overview | null>(null);
const error = ref(false);
const now = ref(Date.now());
let timer: ReturnType<typeof setInterval> | undefined;

onMounted(async () => {
  timer = setInterval(() => (now.value = Date.now()), 15000);
  try { data.value = await api.overview(); } catch { error.value = true; }
});
onBeforeUnmount(() => clearInterval(timer));
watch(() => live.overview, (o) => { if (o) data.value = o; });

// State changes arrive instantly over the WebSocket; OEE figures with the overview every 5 s.
const cards = computed(() => (data.value?.machines ?? []).map((m) => {
  const l = live.machines[m.id];
  const sig = signalMeta(m.id, m.spark.signal);
  const current = l?.values[m.spark.signal] ?? m.values[m.spark.signal] ?? null;
  return { ...m, state: l?.state ?? m.state, reason: l?.state ? l.reason : m.reason, since: l?.state ? l.since : m.since, sig, current };
}));
const meters = (o: Overview['machines'][number]['oee']) => [
  { label: 'Verfügbarkeit', v: o.availability }, { label: 'Leistung', v: o.performance }, { label: 'Qualität', v: o.quality },
];
</script>

<template>
  <div class="page-head">
    <div>
      <p class="eyebrow">Maschinen-Monitor</p>
      <h1>Halle 1 – live</h1>
      <p class="muted">Sechs simulierte Maschinen senden ihre Daten per MQTT. Das Dashboard zeigt Zustand, OEE der laufenden Schicht,
        Stillstandsgründe und Alarme in Echtzeit – statt Kennzahlen erst am Monatsende.</p>
    </div>
    <span v-if="data" class="chip">{{ data.shift.label }}</span>
  </div>

  <p v-if="error" class="alert alert-error" role="alert">Die Übersicht konnte nicht geladen werden. Bitte später erneut versuchen.</p>

  <template v-if="data">
    <section class="card hero" aria-label="Kennzahlen der Halle">
      <div>
        <span class="label">OEE Halle · {{ data.shift.label }}</span>
        <div class="hero-figure" data-testid="hall-oee">{{ pct(data.hall.oee) }}</div>
      </div>
      <div class="hero-tiles">
        <div><span class="label">In Produktion</span><strong>{{ cards.filter((c) => c.state === 'run').length }} / {{ data.hall.machines }}</strong></div>
        <RouterLink to="/alarme"><span class="label">Offene Alarme</span><strong :class="{ critical: data.hall.alarms > 0 }">{{ data.hall.alarms }}</strong></RouterLink>
        <RouterLink to="/stillstaende"><span class="label">Ungeklärte Stillstände</span><strong>{{ data.hall.unclassified }}</strong></RouterLink>
      </div>
    </section>

    <h2 class="section">Maschinen</h2>
    <div class="machines">
      <RouterLink v-for="m in cards" :key="m.id" class="card machine" :data-s="m.state ?? 'off'" :to="`/maschine/${m.id}`" :data-testid="`machine-${m.id}`">
        <header>
          <div><span class="id">{{ m.id }} · {{ m.kind }}</span><h2>{{ m.name }}</h2></div>
          <span v-if="m.alarms" class="chip" :class="{ 'chip-critical': m.critical }">⚠ {{ m.alarms }} Alarm{{ m.alarms > 1 ? 'e' : '' }}</span>
        </header>
        <StateBadge :state="m.state" :reason="m.reason" :since="m.since" :now="now" />
        <div class="figures">
          <div class="oee">{{ pct(m.oee.oee) }}<small>OEE Schicht</small></div>
          <div class="meters">
            <div v-for="x in meters(m.oee)" :key="x.label" class="meter-row">
              <span>{{ x.label }}</span><span class="meter"><span :style="{ width: `${x.v ?? 0}%` }"></span></span><b>{{ x.v === null ? '–' : `${Math.round(x.v)} %` }}</b>
            </div>
          </div>
        </div>
        <div v-if="m.sig" class="spark">
          <Sparkline :points="m.spark.points" :label="`${m.sig.label}, letzte 30 Minuten`" />
          <span>{{ m.sig.label }}<br /><b>{{ num(m.current, m.sig.decimals) }} {{ m.sig.unit }}</b></span>
        </div>
        <div class="foot-line">
          <span>Gut <b>{{ int(m.oee.good) }}</b></span>
          <span>Ausschuss <b>{{ int(m.oee.scrap) }}</b></span>
          <span>Soll bisher <b>{{ int(m.oee.target) }}</b></span>
        </div>
      </RouterLink>
    </div>

    <section class="card how" style="margin-top: 22px">
      <h2 style="font-size: 1.05rem">So funktioniert die Demo</h2>
      <ol>
        <li>Ein Simulator spielt sechs Maschinen (Fräsen, Drehen, Laser, Biegen, Spritzguss, Montage) und sendet alle 2 Sekunden Messwerte per MQTT.</li>
        <li>Das Backend (Python, FastAPI) speichert sie in TimescaleDB, überwacht Grenzwerte und schickt Änderungen per WebSocket an dieses Dashboard.</li>
        <li>Auf jeder Maschinenseite lässt sich eine Störung auslösen – sie erscheint hier und bei allen anderen Besuchern sofort.</li>
        <li>Die Spritzgießmaschine SGM-01 ist das Sorgenkind: Ihr Hydrauliköl wird regelmäßig zu heiß – die Grenzwertwarnung kommt meist Minuten vor der Störung.</li>
      </ol>
    </section>
  </template>
</template>
