<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { RouterLink } from 'vue-router';
import { api, ApiError } from '../api';
import { live, onTelemetry } from '../live';
import { duration, int, num, pct, when } from '../format';
import { machineMeta, meta, reasonText } from '../meta';
import ChartFrame from '../components/ChartFrame.vue';
import ClassifyStop from '../components/ClassifyStop.vue';
import LossCascade from '../components/LossCascade.vue';
import ShiftHistory from '../components/ShiftHistory.vue';
import StateBadge from '../components/StateBadge.vue';
import StateTimeline from '../components/StateTimeline.vue';
import TimeSeriesChart from '../components/TimeSeriesChart.vue';
import type { MachineDetail, RangeKey, Series } from '../types';

const props = defineProps<{ id: string }>();
const RANGES: { key: RangeKey; label: string }[] = [
  { key: '15m', label: '15 min live' }, { key: '8h', label: '8 h' }, { key: '24h', label: '24 h' }, { key: '7d', label: '7 Tage' },
];
const SPAN: Record<RangeKey, number> = { '15m': 900, '8h': 28800, '24h': 86400, '7d': 604800 };

const detail = ref<MachineDetail | null>(null);
const series = ref<Series | null>(null);
const range = ref<RangeKey>('15m');
const now = ref(Date.now());
const notFound = ref(false);
const historyLoading = ref(false);
const faultReason = ref('HYD');
const faultMsg = ref<{ ok: boolean; text: string } | null>(null);
const m = computed(() => machineMeta(props.id));
const state = computed(() => live.machines[props.id]?.state ?? detail.value?.state ?? null);
const stateInfo = computed(() => {
  const l = live.machines[props.id];
  return l?.state ? { reason: l.reason, since: l.since } : { reason: detail.value?.reason ?? null, since: detail.value?.since ?? null };
});

async function loadDetail() {
  try { detail.value = await api.machine(props.id); } catch (e) { if (e instanceof ApiError && e.status === 404) notFound.value = true; }
}
async function loadSeries() { series.value = await api.series(props.id, range.value).catch(() => series.value); }

let timer: ReturnType<typeof setInterval> | undefined;
let refetch: ReturnType<typeof setTimeout> | undefined;
const later = (fn: () => void) => { clearTimeout(refetch); refetch = setTimeout(fn, 800); };
let unlisten: (() => void) | undefined;

onMounted(async () => {
  await Promise.all([loadDetail(), loadSeries()]);
  historyLoading.value = await fetch('/api/health').then((r) => r.json()).then((h: { history?: string }) => h.history === 'loading', () => false);
  timer = setInterval(() => { now.value = Date.now(); void loadDetail(); if (range.value !== '15m') void loadSeries(); }, 30000);
  // 15-minute view: new samples are appended as they arrive, older ones drop off the left edge.
  unlisten = onTelemetry((machine, ts, values) => {
    const s = series.value;
    if (machine !== props.id || !s || range.value !== '15m') return;
    const t = Date.parse(ts) / 1000;
    if (s.t.length && t <= (s.t[s.t.length - 1] ?? 0)) return;
    const cut = t - SPAN['15m'];
    const keep = s.t.findIndex((x) => x > cut);
    const drop = keep < 0 ? 0 : keep;
    s.t = [...s.t.slice(drop), t];
    for (const [key, v] of Object.entries(values)) {
      const sig = s.signals[key];
      if (!sig) continue;
      sig.avg = [...sig.avg.slice(drop), v];
      sig.min = [...sig.min.slice(drop), v];
      sig.max = [...sig.max.slice(drop), v];
    }
    s.end = new Date(t * 1000).toISOString();
    s.start = new Date(cut * 1000).toISOString();
    const lastIv = s.timeline[s.timeline.length - 1];
    if (lastIv) lastIv.end = s.end;
  });
});
onBeforeUnmount(() => { clearInterval(timer); clearTimeout(refetch); unlisten?.(); });
watch(range, loadSeries);
watch(() => props.id, () => { notFound.value = false; void loadDetail(); void loadSeries(); });
watch(() => [live.stateTick, live.alarmTick, live.stopTick], () => later(() => { void loadDetail(); if (range.value === '15m') void loadSeries(); }));

const startS = computed(() => (series.value ? Date.parse(series.value.start) / 1000 : 0));
const endS = computed(() => (series.value ? Date.parse(series.value.end) / 1000 : 0));

async function fault() {
  faultMsg.value = null;
  try {
    const r = await api.fault(props.id, faultReason.value);
    faultMsg.value = { ok: true, text: `„${r.text}“ ausgelöst – gleich hier und in der Hallenübersicht zu sehen.` };
  } catch (e) {
    faultMsg.value = { ok: false, text: e instanceof ApiError ? e.message : 'Auslösen fehlgeschlagen.' };
  }
}
</script>

<template>
  <RouterLink class="btn btn-sm btn-ghost" to="/">← Halle</RouterLink>
  <p v-if="notFound" class="alert alert-error" role="alert">Diese Maschine gibt es nicht.</p>

  <template v-if="m && detail">
    <div class="page-head">
      <div>
        <p class="eyebrow">{{ m.id }} · {{ m.kind }}</p>
        <h1>{{ m.name }}</h1>
        <p style="margin-top: 12px"><StateBadge :state="state" :reason="stateInfo.reason" :since="stateInfo.since" :now="now" /></p>
      </div>
      <form class="fault card" style="padding: 12px 14px" @submit.prevent="fault" data-tour="fault">
        <label class="label" for="fault-reason" style="flex-basis: 100%">Demo: Störung auslösen</label>
        <select id="fault-reason" v-model="faultReason" class="select" data-testid="fault-reason">
          <option v-for="code in meta.injectable" :key="code" :value="code">{{ reasonText(code) }}</option>
        </select>
        <button class="btn btn-primary btn-sm" type="submit" :disabled="state !== 'run'" data-testid="fault">Auslösen</button>
        <span v-if="state !== 'run'" class="muted" style="font-size: 0.8rem; flex-basis: 100%">Nur an einer produzierenden Maschine möglich.</span>
      </form>
    </div>
    <p v-if="faultMsg" class="alert" :class="faultMsg.ok ? 'alert-ok' : 'alert-error'" role="status" data-testid="fault-msg" style="margin-bottom: 14px">{{ faultMsg.text }}</p>

    <div class="kpis">
      <div class="card kpi main"><span class="label">OEE · {{ detail.shift.label }}</span><span class="value" data-testid="machine-oee">{{ pct(detail.oee.oee) }}</span></div>
      <div class="card kpi"><span class="label">Verfügbarkeit</span><span class="value">{{ pct(detail.oee.availability) }}</span><span class="sub">{{ duration(detail.oee.runMin) }} von {{ duration(detail.oee.plannedMin) }} produziert</span></div>
      <div class="card kpi"><span class="label">Leistung</span><span class="value">{{ pct(detail.oee.performance) }}</span><span class="sub">Idealtakt {{ num(m.cycleS) }} s</span></div>
      <div class="card kpi"><span class="label">Qualität</span><span class="value">{{ pct(detail.oee.quality) }}</span><span class="sub">{{ int(detail.oee.scrap) }} Ausschuss</span></div>
      <div class="card kpi"><span class="label">Teile</span><span class="value">{{ int(detail.oee.good) }}</span><span class="sub">gut · Soll bisher {{ int(detail.oee.target) }}</span></div>
    </div>

    <div class="toolbar" style="margin-top: 22px">
      <h2 class="section" style="margin: 0">Verlauf</h2>
      <span class="grow"></span>
      <div class="segmented" role="group" aria-label="Zeitraum">
        <button v-for="r in RANGES" :key="r.key" type="button" :aria-pressed="range === r.key" @click="range = r.key">{{ r.label }}</button>
      </div>
    </div>

    <p v-if="historyLoading" class="alert" role="status" style="margin-bottom: 12px">Der Verlauf der letzten Tage wird gerade nachgeladen (nach einer Ruhephase der Demo) – längere Zeiträume sind gleich vollständig.</p>
    <div v-if="series" class="signals" data-tour="signals">
      <ChartFrame title="Zustand" :sub="range === '15m' ? 'Letzte 15 Minuten, live' : `Letzte ${RANGES.find((r) => r.key === range)?.label}`">
        <StateTimeline :intervals="series.timeline" :start="startS" :end="endS" />
        <template #table>
          <table class="data"><thead><tr><th>Von</th><th>Bis</th><th>Zustand</th><th>Grund</th></tr></thead>
            <tbody><tr v-for="iv in series.timeline" :key="iv.start"><td>{{ when(iv.start) }}</td><td>{{ when(iv.end) }}</td><td>{{ meta.states[iv.state] }}</td><td>{{ reasonText(iv.reason) }}</td></tr></tbody></table>
        </template>
      </ChartFrame>
      <ChartFrame v-for="sig in m.signals" :key="sig.key" :title="`${sig.label} (${sig.unit})`"
        :sub="range === '15m' ? 'Messwert alle 2 Sekunden' : 'Mittelwert mit Spanne (Minimum–Maximum)'" :data-testid="`signal-${sig.key}`">
        <TimeSeriesChart :t="series.t" :avg="series.signals[sig.key]?.avg ?? []" :min="series.signals[sig.key]?.min" :max="series.signals[sig.key]?.max"
          :start="startS" :end="endS" :label="sig.label" :unit="sig.unit" :decimals="sig.decimals" :warn="sig.warn" :crit="sig.crit" />
        <template #table>
          <table class="data"><thead><tr><th>Zeit</th><th class="right">Wert ({{ sig.unit }})</th><th class="right">Min.</th><th class="right">Max.</th></tr></thead>
            <tbody><tr v-for="(t, i) in series.t.slice(-60).reverse()" :key="t">
              <td>{{ when(new Date(t * 1000).toISOString()) }}</td>
              <td class="right num">{{ num(series.signals[sig.key]?.avg[series.t.length - 1 - i] ?? null, sig.decimals) }}</td>
              <td class="right num">{{ num(series.signals[sig.key]?.min[series.t.length - 1 - i] ?? null, sig.decimals) }}</td>
              <td class="right num">{{ num(series.signals[sig.key]?.max[series.t.length - 1 - i] ?? null, sig.decimals) }}</td>
            </tr></tbody></table>
        </template>
      </ChartFrame>
    </div>

    <div class="charts" style="margin-top: 14px">
      <ChartFrame data-tour="losses" title="Wohin die Schichtzeit ging" :sub="`${detail.shift.label}, bis jetzt`">
        <LossCascade :oee="detail.oee" />
        <template #table>
          <table class="data"><thead><tr><th>Grund</th><th class="right">Minuten</th></tr></thead>
            <tbody><tr v-for="l in detail.losses" :key="l.reason"><td>{{ l.text }}</td><td class="right num">{{ num(l.min) }}</td></tr>
              <tr><td>Leistungsverlust</td><td class="right num">{{ detail.oee.lossMin.performance }}</td></tr>
              <tr><td>Qualitätsverlust</td><td class="right num">{{ detail.oee.lossMin.quality }}</td></tr></tbody></table>
        </template>
      </ChartFrame>
      <ChartFrame title="OEE je Schicht" sub="Letzte 7 Tage, abgeschlossene Schichten">
        <ShiftHistory :history="detail.history" />
        <template #table>
          <table class="data"><thead><tr><th>Schicht</th><th class="right">OEE</th><th class="right">V</th><th class="right">L</th><th class="right">Q</th></tr></thead>
            <tbody><tr v-for="h in [...detail.history].reverse()" :key="h.shift.start"><td>{{ h.shift.label }}</td><td class="right num">{{ pct(h.oee) }}</td>
              <td class="right num">{{ pct(h.availability) }}</td><td class="right num">{{ pct(h.performance) }}</td><td class="right num">{{ pct(h.quality) }}</td></tr></tbody></table>
        </template>
      </ChartFrame>
    </div>

    <div class="grid-2" style="margin-top: 14px">
      <section class="card panel">
        <h2>Stillstände (24 h)</h2>
        <ul class="list" data-testid="stops">
          <li v-for="s in detail.stops.slice(0, 10)" :key="s.start" :data-s="s.state" style="flex-wrap: wrap">
            <span class="state" :data-s="s.state" style="padding: 4px 8px"><span class="dot" aria-hidden="true">{{ s.state === 'setup' ? '⚙' : '!' }}</span>{{ s.text }}</span>
            <span class="grow"><small>{{ when(s.start) }} · {{ s.open ? 'läuft seit ' : '' }}{{ duration(s.min) }}{{ s.classified ? ' · nachträglich zugeordnet' : '' }}</small></span>
            <ClassifyStop v-if="s.reason === 'UNK' && s.state === 'down'" :machine="detail.id" :start="s.start" @done="loadDetail" />
          </li>
          <li v-if="!detail.stops.length" class="muted">Keine Stillstände in den letzten 24 Stunden.</li>
        </ul>
        <RouterLink v-if="detail.stops.length > 10" class="btn btn-sm btn-ghost" to="/stillstaende" style="margin-top: 8px">Alle Stillstände →</RouterLink>
      </section>
      <section class="card panel">
        <h2>Alarme</h2>
        <ul class="list">
          <li v-for="a in detail.alarms.slice(0, 10)" :key="a.id">
            <span class="chip" :class="{ 'chip-critical': a.severity === 'critical' }">{{ a.severity === 'critical' ? '⚠ Kritisch' : 'Warnung' }}</span>
            <span class="grow">{{ a.text }}<small>{{ when(a.raisedAt) }} · {{ a.clearedAt ? `beendet ${when(a.clearedAt)}` : 'aktiv' }} · {{ a.source === 'rule' ? 'Grenzwert' : 'Maschine' }}</small></span>
          </li>
          <li v-if="!detail.alarms.length" class="muted">Keine Alarme.</li>
        </ul>
        <RouterLink v-if="detail.alarms.length > 10" class="btn btn-sm btn-ghost" to="/alarme" style="margin-top: 8px">Alle Alarme →</RouterLink>
      </section>
    </div>
  </template>
</template>
