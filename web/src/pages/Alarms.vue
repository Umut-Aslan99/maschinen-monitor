<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { RouterLink } from 'vue-router';
import { api, ApiError } from '../api';
import { live } from '../live';
import { when } from '../format';
import { meta } from '../meta';
import { disablePush, enablePush, pushState, type PushState } from '../push';
import type { Alarm } from '../types';

const alarms = ref<Alarm[]>([]);
const push = ref<PushState>('unsupported');
const pushError = ref('');
const active = computed(() => alarms.value.filter((a) => !a.clearedAt));
const history = computed(() => alarms.value.filter((a) => a.clearedAt));

async function load() { alarms.value = await api.alarms(); }
onMounted(async () => {
  await load();
  push.value = await pushState().catch(() => 'unsupported' as const);
});
watch(() => live.alarmTick, load);

async function ack(a: Alarm) {
  await api.ack(a.id).catch(() => undefined);
  await load();
}
async function togglePush() {
  pushError.value = '';
  try {
    push.value = push.value === 'on' ? await disablePush() : await enablePush(meta.value.pushKey ?? '');
  } catch (e) {
    pushError.value = e instanceof ApiError ? e.message : 'Benachrichtigungen konnten nicht eingerichtet werden.';
  }
}
</script>

<template>
  <div class="page-head">
    <div>
      <p class="eyebrow">Alarme</p>
      <h1>Alarme</h1>
      <p class="muted">Maschinenalarme (von der Steuerung) und Grenzwertalarme (vom Backend überwacht: mehrere Messwerte in Folge über
        der Grenze, mit Hysterese). Quittieren zeigt allen: jemand kümmert sich.</p>
    </div>
  </div>

  <section v-if="meta.pushKey" class="card panel" style="margin-bottom: 18px">
    <h2>Alarme aufs Handy</h2>
    <p class="muted" style="font-size: 0.9rem">Kritische Alarme als Push-Benachrichtigung – höchstens eine alle 5 Minuten, endet automatisch nach
      24 Stunden. Auf dem iPhone zuerst „Zum Home-Bildschirm“ hinzufügen.</p>
    <p style="margin-top: 10px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap">
      <button v-if="push !== 'unsupported' && push !== 'denied'" class="btn btn-sm" :class="{ 'btn-primary': push === 'off' }" type="button" @click="togglePush">
        {{ push === 'on' ? 'Benachrichtigungen aus' : 'Benachrichtigungen an' }}
      </button>
      <span v-else class="muted" style="font-size: 0.86rem">{{ push === 'denied' ? 'Benachrichtigungen sind im Browser blockiert.' : 'Dieser Browser unterstützt keine Push-Benachrichtigungen.' }}</span>
      <span v-if="push === 'on'" class="chip chip-good">✓ aktiv</span>
      <span v-if="pushError" class="critical" role="alert">{{ pushError }}</span>
    </p>
  </section>

  <h2 class="section" style="margin-top: 0">Aktiv ({{ active.length }})</h2>
  <section class="card panel" data-tour="alarms">
    <ul class="list" data-testid="active-alarms">
      <li v-for="a in active" :key="a.id">
        <span class="chip" :class="{ 'chip-critical': a.severity === 'critical' }">{{ a.severity === 'critical' ? '⚠ Kritisch' : 'Warnung' }}</span>
        <span class="grow"><RouterLink :to="`/maschine/${a.machine}`" class="mono">{{ a.machine }}</RouterLink> {{ a.text }}
          <small>seit {{ when(a.raisedAt) }} · {{ a.source === 'rule' ? 'Grenzwert' : 'Maschine' }}{{ a.ackedAt ? ` · quittiert ${when(a.ackedAt)}` : '' }}</small></span>
        <button v-if="!a.ackedAt" class="btn btn-sm" type="button" @click="ack(a)">Quittieren</button>
      </li>
      <li v-if="!active.length" class="muted">Keine aktiven Alarme.</li>
    </ul>
  </section>

  <h2 class="section">Verlauf</h2>
  <div class="card table-wrap">
    <table class="data">
      <thead><tr><th>Beginn</th><th>Ende</th><th>Maschine</th><th>Alarm</th><th>Art</th><th>Quittiert</th></tr></thead>
      <tbody>
        <tr v-for="a in history" :key="a.id">
          <td>{{ when(a.raisedAt) }}</td><td>{{ a.clearedAt ? when(a.clearedAt) : '' }}</td>
          <td><RouterLink :to="`/maschine/${a.machine}`" class="mono">{{ a.machine }}</RouterLink></td>
          <td class="wrap-cell">{{ a.severity === 'critical' ? '⚠ ' : '' }}{{ a.text }}</td>
          <td>{{ a.source === 'rule' ? 'Grenzwert' : 'Maschine' }}</td><td>{{ a.ackedAt ? when(a.ackedAt) : '–' }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
