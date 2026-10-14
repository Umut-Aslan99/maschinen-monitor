<script setup lang="ts">
import { ref } from 'vue';
import { api, ApiError } from '../api';
import { meta, reasonText } from '../meta';

/** Assign a reason to an unexplained stop – what the operator would do on the shop-floor terminal. */
const props = defineProps<{ machine: string; start: string }>();
const emit = defineEmits<{ done: [text: string] }>();
const reason = ref('');
const busy = ref(false);
const error = ref('');

async function save() {
  if (!reason.value) return;
  busy.value = true;
  error.value = '';
  try {
    emit('done', (await api.classify(props.machine, props.start, reason.value)).text);
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Speichern fehlgeschlagen.';
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <form class="fault" @submit.prevent="save">
    <select v-model="reason" class="select" aria-label="Stillstandsgrund" data-testid="classify-reason">
      <option value="" disabled>Grund wählen …</option>
      <option v-for="code in meta.classifiable" :key="code" :value="code">{{ reasonText(code) }}</option>
    </select>
    <button class="btn btn-sm" type="submit" :disabled="!reason || busy">Zuordnen</button>
    <span v-if="error" class="critical" role="alert">{{ error }}</span>
  </form>
</template>
