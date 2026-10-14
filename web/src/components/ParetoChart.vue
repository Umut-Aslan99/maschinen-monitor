<script setup lang="ts">
import { computed } from 'vue';
import { duration } from '../format';
import type { Pareto } from '../types';

/** Downtime by reason, largest first. Cumulative share as a column of text – no second axis. */
const props = defineProps<{ data: Pareto }>();
const top = computed(() => Math.max(...props.data.items.map((i) => i.min), 1));
</script>

<template>
  <div class="legend">
    <span><i class="box" style="background: var(--series-1)"></i>Ungeplanter Stillstand</span>
    <span><i class="box" style="background: var(--series-2)"></i>Rüsten / Werkzeugwechsel</span>
  </div>
  <p v-if="!data.items.length" class="muted">Keine Stillstände im gewählten Zeitraum.</p>
  <div class="hbars" role="list" data-testid="pareto">
    <div v-for="item in data.items" :key="item.reason" class="hbar" role="listitem" tabindex="0"
      :title="`${item.count}× · ${item.share} % der Stillstandszeit · kumuliert ${item.cumulative} %`">
      <span>{{ item.text }}</span>
      <span class="track">
        <span class="bar" :style="{ left: 0, width: `${(item.min / top) * 100}%`, background: item.kind === 'setup' ? 'var(--series-2)' : 'var(--series-1)' }"></span>
      </span>
      <span class="val">{{ duration(item.min) }}<small>{{ item.share }} % · kum. {{ item.cumulative }} %</small></span>
    </div>
  </div>
</template>
