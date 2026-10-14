<script setup lang="ts">
import { computed, ref } from 'vue';
import { RouterLink, RouterView } from 'vue-router';
import { live } from './live';

const theme = ref(document.documentElement.dataset.theme ?? (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'));
function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = theme.value;
  try { localStorage.setItem('theme', theme.value); } catch { /* private mode */ }
}
const openAlarms = computed(() => live.overview?.hall.alarms ?? 0);
</script>

<template>
  <a class="sr-only" href="#main">Zum Inhalt</a>
  <header class="band">
    <div class="band-inner">
      <span class="brand">
        <a class="who" href="https://umut-aslan.dev">Umut Aslan</a><span class="sep">/</span><RouterLink class="what" to="/">Maschinen-Monitor</RouterLink>
      </span>
      <nav class="nav" aria-label="Bereiche">
        <RouterLink to="/" active-class="" exact-active-class="active">Halle</RouterLink>
        <RouterLink to="/stillstaende" active-class="active">Stillstände</RouterLink>
        <RouterLink to="/alarme" active-class="active">Alarme<template v-if="openAlarms"> ({{ openAlarms }})</template></RouterLink>
      </nav>
      <div class="tools">
        <span class="live-pill" :class="{ on: live.connected }" data-testid="live"><i aria-hidden="true"></i>{{ live.connected ? 'Live' : 'Getrennt' }}</span>
        <button class="tool" type="button" :aria-label="theme === 'dark' ? 'Helles Design' : 'Dunkles Design'" @click="toggleTheme">{{ theme === 'dark' ? '☀' : '☾' }}</button>
      </div>
    </div>
    <div class="bar" aria-hidden="true"></div>
  </header>

  <main id="main" class="page">
    <p class="workspace-note" role="note">
      <span><strong>Simulierte Halle, live für alle Besucher.</strong> Ausgelöste Störungen, Quittierungen und Zuordnungen sehen auch
        andere. Alle Maschinen und Daten sind frei erfunden.</span>
    </p>
    <RouterView />
  </main>

  <footer class="foot">
    <div class="foot-inner">
      <span>Ein Demo-Projekt von <a href="https://umut-aslan.dev">Umut Aslan</a> · Vue 3 · Python FastAPI · MQTT · TimescaleDB</span>
      <span><a href="https://umut-aslan.dev/impressum/">Impressum</a> · <a href="https://umut-aslan.dev/datenschutz/">Datenschutz</a></span>
    </div>
  </footer>

  <div class="toasts" aria-live="polite">
    <div v-for="t in live.toasts" :key="t.id" class="toast" :class="{ critical: t.critical }" role="status">
      <span aria-hidden="true">⚠</span>
      <span><RouterLink :to="`/maschine/${t.machine}`">{{ t.machine }}</RouterLink> {{ t.text }}</span>
    </div>
  </div>
</template>
