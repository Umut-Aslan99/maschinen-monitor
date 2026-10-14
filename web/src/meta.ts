import { shallowRef } from 'vue';
import type { MachineMeta, Meta, SignalMeta, StateCode } from './types';

/** Machine catalog, reasons and state names – loaded once before the app mounts. */
export const meta = shallowRef<Meta>({ machines: [], reasons: [], classifiable: [], states: {} as Record<StateCode, string>, injectable: [], pushKey: null });

export const machineMeta = (id: string): MachineMeta | undefined => meta.value.machines.find((m) => m.id === id);
export const reasonText = (code: string | null) => (code ? meta.value.reasons.find((r) => r.code === code)?.text ?? code : '');
export const stateLabel = (s: StateCode | null) => (s ? meta.value.states[s] : 'Unbekannt');
export const signalMeta = (machineId: string, key: string): SignalMeta | undefined => machineMeta(machineId)?.signals.find((s) => s.key === key);

/** Icon per state – the state never relies on colour alone. */
export const STATE_ICON: Record<StateCode, string> = { run: '▶', down: '!', setup: '⚙', planned: 'Ⅱ', off: '–' };
