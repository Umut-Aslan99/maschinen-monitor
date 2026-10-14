<script setup lang="ts">
import { ref } from 'vue';

defineProps<{ title: string; sub?: string }>();
const table = ref(false);
</script>

<template>
  <section class="card chart-card">
    <header>
      <div>
        <h2>{{ title }}</h2>
        <p v-if="sub" class="sub">{{ sub }}</p>
      </div>
      <div class="chart-tools">
        <slot name="tools" />
        <button class="btn btn-sm btn-ghost" type="button" :aria-pressed="table" @click="table = !table">
          {{ table ? 'Diagramm' : 'Tabelle' }}
        </button>
      </div>
    </header>
    <slot name="legend" />
    <div v-if="table" class="table-wrap"><slot name="table" /></div>
    <slot v-else />
  </section>
</template>
