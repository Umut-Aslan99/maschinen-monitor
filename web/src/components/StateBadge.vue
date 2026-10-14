<script setup lang="ts">
import { computed } from 'vue';
import { STATE_ICON, reasonText, stateLabel } from '../meta';
import { duration, minutesSince } from '../format';
import type { StateCode } from '../types';

const props = defineProps<{ state: StateCode | null; reason?: string | null; since?: string | null; now?: number }>();
const detail = computed(() => {
  const parts: string[] = [];
  if (props.reason && props.state !== 'off' && props.state !== 'planned') parts.push(reasonText(props.reason));
  if (props.since) parts.push(`seit ${duration(minutesSince(props.since, props.now))}`);
  return parts.join(' · ');
});
</script>

<template>
  <span class="state" :data-s="state ?? 'off'" data-testid="state">
    <span class="dot" aria-hidden="true">{{ state ? STATE_ICON[state] : '?' }}</span>
    {{ stateLabel(state) }}
    <small v-if="detail">{{ detail }}</small>
  </span>
</template>
