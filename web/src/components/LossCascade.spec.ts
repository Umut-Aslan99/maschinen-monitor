import { mount } from '@vue/test-utils';
import LossCascade from './LossCascade.vue';
import type { OeeView } from '../types';

const oee: OeeView = {
  oee: 82.2, availability: 89.6, performance: 94.3, quality: 97.4, plannedMin: 450, runMin: 403, downMin: 47, setupMin: 0,
  good: 370, scrap: 10, target: 450, lossMin: { availability: 47, performance: 23, quality: 10 },
};

describe('LossCascade', () => {
  it('walks from planned time to value-adding time', () => {
    const rows = mount(LossCascade, { props: { oee } }).findAll('.hbar');
    expect(rows.map((r) => r.find('.val').text().replace(' min', ''))).toEqual(['450', '−47', '−23', '−10', '370']);
    // The last loss bar ends where the value-adding time ends: 370 / 450.
    const quality = rows[3]!.find('.bar').attributes('style');
    expect(quality).toContain(`left: ${(370 / 450) * 100}%`);
  });
});
