import { expect, it, vi } from 'vitest';
import { plot } from '../../pvyieldlens/frontend/src/charts';

it('keeps unavailable gaps and distinct second-level labels in a short power series', () => {
  const host = document.createElement('div');
  document.body.append(host);
  Object.defineProperties(host, { clientWidth: { value: 1200 }, clientHeight: { value: 260 } });
  // JSDOM has no SVG text layout; supply measured-width geometry for tick collision checks.
  const bounds = vi.spyOn(SVGElement.prototype, 'getBoundingClientRect').mockImplementation(function () {
    return new DOMRect(Number(this.getAttribute('x') ?? 0), 0, 60, 12);
  });
  try {
    plot(host, [
      { at: 1793491200, actual_power: 10 }, { at: 1793491201, actual_power: null },
      { at: 1793491202, actual_power: 20 }, { at: 1793491203, actual_power: 30 },
    ], [{ key: 'actual_power', label: 'Power', color: 'blue' }], 'W', {
      language: 'en', timezone: 'UTC', translate: key => key,
    });
    expect(host.querySelector('path')!.getAttribute('d')!.match(/M/g)).toHaveLength(2);
    const ticks = [...host.querySelectorAll('.time-tick')].map(node => node.textContent);
    expect(ticks.length).toBeGreaterThan(1);
    expect(new Set(ticks).size).toBe(ticks.length);
    expect(ticks).toContain('12:00:03 AM');
  } finally {
    bounds.mockRestore();
    host.remove();
  }
});
