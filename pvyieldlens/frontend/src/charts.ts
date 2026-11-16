import type { ForecastInterval, WindowResult } from './models';
import type { Language } from './i18n';
import { formatTimes } from './timezones';

export interface ChartPoint {
  at: number;
  estimated_power?: number | null;
  actual_power?: number | null;
  pr?: number | null;
  power_w?: number | null;
  interval?: ForecastInterval;
  window?: WindowResult;
  breakBefore?: boolean;
}
export interface ChartSeries {
  key: 'estimated_power' | 'actual_power' | 'pr' | 'power_w';
  label: string;
  color: string;
}
export interface ChartOptions {
  language: Language;
  timezone: string;
  translate: (key: string) => string;
  tooltip?: (point: ChartPoint) => ChartTooltip;
  currentTime?: number;
  range?: { start: number; end: number };
  selection?: 'nearest' | 'interval';
  selectedAt?: number | null;
}
export interface ChartTooltip {
  title: string;
  rows: { label: string; value: string; color?: string }[];
}
export interface ChartHandle {
  updateTime(at: number): void;
  selectedAt(): number | null;
  dispose(): void;
}

let chartId = 0;

export function plot(host: HTMLElement, data: ChartPoint[], series: ChartSeries[], unit: string,
  { language, timezone, translate: t, tooltip, currentTime, range, selection = 'nearest', selectedAt }: ChartOptions): ChartHandle {
  const number = (value: number, digits = 1) => new Intl.NumberFormat(language, { maximumFractionDigits: digits }).format(value);
  const stamps = formatTimes(data.map(point => point.at), language, timezone, {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
  const labels = new Map(data.map((point, index) => [point.at, stamps[index]]));
  host.replaceChildren();
  const valid = data.flatMap(point => series.map(item => point[item.key]))
    .filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
  if (!data.length) {
    const message = document.createElement('div');
    message.className = 'chart-empty';
    message.textContent = t('plot_empty');
    host.append(message);
    return { updateTime() {}, selectedAt: () => null, dispose() {} };
  }
  const width = Math.max(host.clientWidth, 1), height = host.clientHeight, left = 48, right = 12, top = 16, bottom = 34;
  const start = range?.start ?? data[0].at, end = Math.max(range?.end ?? data[data.length - 1].at, start + 1);
  const maximum = Math.max(1, ...valid) * 1.1;
  const minimum = Math.min(0, ...valid);
  const x = (at: number) => left + (at - start) / (end - start) * (width - left - right);
  const y = (value: number) => top + (maximum - value) / (maximum - minimum) * (height - top - bottom);
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('role', 'group');
  svg.setAttribute('aria-label', series.map(item => t(item.label)).join(' / '));
  const add = <K extends keyof SVGElementTagNameMap>(tag: K, attrs: Record<string, string | number>, text?: string, parent: SVGElement = svg) => {
    const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
    if (text !== undefined) node.textContent = text;
    parent.append(node);
    return node;
  };
  Array.from({ length: 5 }, (_, index) => minimum + (maximum - minimum) * index / 4).forEach(value => {
    add('line', { x1: left, x2: width - right, y1: y(value), y2: y(value), class: 'grid' });
    add('text', { x: left - 10, y: y(value) + 4, 'text-anchor': 'end' }, number(value, 0));
  });
  add('text', { x: left, y: 9 }, unit);
  const duration = end - start;
  const spacing = duration > 86400 ? 120 : 76;
  const count = Math.max(2, Math.min(6, Math.floor((width - left - right) / spacing) + 1));
  const step = [1, 5, 10, 15, 30, 60, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400, 172800, 604800]
    .find(value => value >= duration / (count - 1)) ?? 604800;
  const times = [start, ...Array.from({ length: Math.max(0, Math.ceil(end / step) - Math.ceil(start / step)) },
    (_, index) => (Math.ceil(start / step) + index) * step).filter(at => at > start && at < end), end];
  const ticks = formatTimes(times, language, timezone, {
    ...(duration > 86400 ? { month: 'short', day: 'numeric' } : {}),
    ...(duration <= 86400 || step < 86400 ? { hour: '2-digit', minute: '2-digit', ...(duration < 300 ? { second: '2-digit' } : {}) } : {}),
  });
  let previousTick: SVGTextElement | undefined;
  times.forEach((at, index) => {
    const text = ticks[index];
    if (previousTick && (text === previousTick.textContent || x(at) - Number(previousTick.getAttribute('x')) < spacing)) return;
    previousTick = add('text', { x: x(at), y: height - 8, class: 'time-tick',
      'text-anchor': index === 0 ? 'start' : index === times.length - 1 ? 'end' : 'middle' }, text);
  });
  const clipId = `chart-clip-${++chartId}`;
  const defs = add('defs', {});
  const clip = add('clipPath', { id: clipId }, undefined, defs);
  add('rect', { x: left, y: top, width: width - left - right, height: height - top - bottom }, undefined, clip);
  const drawing = add('g', { 'clip-path': `url(#${clipId})` });
  const stride = Math.max(1, Math.ceil(data.length / 600));
  series.forEach(item => {
    const runs: { at: number; value: number; point: ChartPoint }[][] = [];
    let run: typeof runs[number] = [];
    data.forEach((point, index) => {
      const value = point[item.key];
      if (value == null || !Number.isFinite(value)) { run = []; return; }
      const previous = data[index - 1]?.interval;
      if (!run.length || point.breakBefore || point.interval && previous && point.interval.start > previous.end) {
        run = [];
        runs.push(run);
      }
      run.push({ at: point.at, value, point });
    });
    const commands = runs.map(points => {
      // Split before thinning so the last valid sample on either side of a gap survives.
      const sampled = points.filter((_, index) => index % stride === 0 || index === points.length - 1);
      if (selection === 'interval') {
        const first = sampled[0], last = sampled[sampled.length - 1];
        if (first.point.interval && first.point.interval.start < first.at) {
          sampled.unshift({ ...first, at: Math.max(start, first.point.interval.start) });
        }
        if (last.point.interval && last.point.interval.end > last.at) {
          sampled.push({ ...last, at: Math.min(end, last.point.interval.end) });
        }
      }
      const vertices = sampled.map(point => ({ x: x(point.at), y: y(point.value) }));
      if (vertices.length === 1) add('circle', { cx: vertices[0].x, cy: vertices[0].y, r: 3, fill: item.color, class: 'series-point' }, undefined, drawing);
      const slopes = vertices.slice(1).map((point, index) => (point.y - vertices[index].y) / (point.x - vertices[index].x));
      const tangents = vertices.map((point, index) => {
        if (index === 0) return slopes[0];
        if (index === vertices.length - 1) return slopes[index - 1];
        const before = slopes[index - 1], after = slopes[index];
        if (before * after <= 0) return 0;
        const leftWidth = point.x - vertices[index - 1].x, rightWidth = vertices[index + 1].x - point.x;
        // Weighted harmonic tangents preserve shape with irregular sampling intervals.
        return 3 * (leftWidth + rightWidth) / ((leftWidth + 2 * rightWidth) / before + (2 * leftWidth + rightWidth) / after);
      });
      return vertices.map((point, index) => {
        const coordinate = `${point.x.toFixed(2)},${point.y.toFixed(2)}`;
        if (!index) return `M${coordinate}`;
        if (vertices.length === 2) return `L${coordinate}`;
        const previous = vertices[index - 1], third = (point.x - previous.x) / 3;
        return `C${(previous.x + third).toFixed(2)},${(previous.y + tangents[index - 1] * third).toFixed(2)} ${(point.x - third).toFixed(2)},${(point.y - tangents[index] * third).toFixed(2)} ${coordinate}`;
      }).join(' ');
    });
    add('path', { d: commands.join(' '), stroke: item.color, class: 'series' }, undefined, drawing);
  });
  const marker = currentTime === undefined ? null : add('line', { class: 'current-time', y1: top, y2: height - bottom }, undefined, drawing);
  const interaction = add('g', {});
  const guide = add('line', { class: 'chart-guide', y1: top, y2: height - bottom, visibility: 'hidden' }, undefined, interaction);
  const markers = series.map(item => add('circle', { r: 4, fill: item.color, class: 'active-series-marker', visibility: 'hidden' }, undefined, interaction));
  const hit = add('rect', { class: 'chart-hit-area', x: left, y: top, width: width - left - right, height: height - top - bottom,
    fill: 'transparent', tabindex: 0, role: 'slider', 'aria-label': series.map(item => t(item.label)).join(' / '),
    'aria-valuemin': start, 'aria-valuemax': end, 'aria-valuenow': start }, undefined, interaction);
  const tip = document.createElement('div');
  tip.className = 'chart-tooltip';
  tip.setAttribute('role', 'tooltip');
  tip.id = `chart-tooltip-${chartId}`;
  hit.setAttribute('aria-describedby', tip.id);
  tip.hidden = true;
  host.append(svg, tip);
  let active: ChartPoint | undefined;
  const hide = () => {
    active = undefined;
    tip.hidden = true;
    guide.setAttribute('visibility', 'hidden');
    markers.forEach(marker => marker.setAttribute('visibility', 'hidden'));
  };
  const show = (point: ChartPoint | undefined) => {
    if (!point || point.at < start || point.at > end) { hide(); return; }
    active = point;
    guide.setAttribute('x1', String(x(point.at)));
    guide.setAttribute('x2', String(x(point.at)));
    guide.setAttribute('visibility', 'visible');
    markers.forEach((marker, index) => {
      const value = point[series[index].key];
      marker.setAttribute('visibility', value == null || !Number.isFinite(value) ? 'hidden' : 'visible');
      if (value != null && Number.isFinite(value)) {
        marker.setAttribute('cx', String(x(point.at)));
        marker.setAttribute('cy', String(y(value)));
      }
    });
    const content = tooltip?.(point) ?? { title: labels.get(point.at)!, rows: series.map(item => {
      const value = point[item.key];
      return { label: t(item.label), value: `${value == null ? '—' : number(value)} ${unit}`, color: item.color };
    }) };
    const title = document.createElement('strong');
    title.textContent = content.title;
    tip.replaceChildren(title);
    content.rows.forEach(row => {
      const line = document.createElement('div');
      const label = document.createElement('span');
      label.textContent = row.label;
      if (row.color) label.style.color = row.color;
      const value = document.createElement('span');
      value.textContent = row.value;
      line.append(label, value);
      tip.append(line);
    });
    tip.hidden = false;
    hit.setAttribute('aria-valuenow', String(point.at));
    hit.setAttribute('aria-valuetext', tip.textContent!);
    const bounds = host.getBoundingClientRect();
    const visibleLeft = Math.max(0, -bounds.left), visibleRight = Math.min(width, window.innerWidth - bounds.left);
    const visibleTop = Math.max(0, -bounds.top), visibleBottom = Math.min(height, window.innerHeight - bounds.top);
    tip.style.maxWidth = `${Math.max(0, visibleRight - visibleLeft)}px`;
    tip.style.maxHeight = `${Math.max(0, visibleBottom - visibleTop)}px`;
    tip.style.left = `${Math.max(visibleLeft, Math.min(x(point.at) + 12, visibleRight - tip.offsetWidth))}px`;
    tip.style.top = `${Math.max(visibleTop, Math.min(top + 8, visibleBottom - tip.offsetHeight))}px`;
    const scrollable = tip.scrollHeight > tip.clientHeight;
    tip.style.pointerEvents = scrollable ? 'auto' : 'none';
    tip.tabIndex = scrollable ? 0 : -1;
  };
  const inspect = (event: PointerEvent) => {
    const bounds = svg.getBoundingClientRect();
    const at = start + Math.max(0, Math.min(1, ((event.clientX - bounds.left) * width / (bounds.width || width) - left) / (width - left - right))) * (end - start);
    show(selection === 'interval'
      ? data.find(point => point.interval && point.interval.start <= at && (at < point.interval.end || at === end && point.interval.end === end))
      : data.reduce((nearest, point) => Math.abs(point.at - at) < Math.abs(nearest.at - at) ? point : nearest));
  };
  const listeners = new AbortController();
  const events = { signal: listeners.signal };
  let touchStart: { x: number; y: number } | undefined;
  hit.addEventListener('pointermove', event => { if (event.pointerType !== 'touch') inspect(event); }, events);
  host.addEventListener('pointerleave', event => { if (event.pointerType !== 'touch') hide(); }, events);
  hit.addEventListener('pointerdown', event => {
    if (event.pointerType === 'touch') touchStart = { x: event.clientX, y: event.clientY };
  }, events);
  hit.addEventListener('pointerup', event => {
    if (event.pointerType === 'touch' && touchStart && Math.hypot(event.clientX - touchStart.x, event.clientY - touchStart.y) < 10) inspect(event);
    touchStart = undefined;
  }, events);
  hit.addEventListener('pointercancel', () => { touchStart = undefined; hide(); }, events);
  hit.addEventListener('keydown', event => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    event.preventDefault();
    const index = active ? data.indexOf(active) + (event.key === 'ArrowRight' ? 1 : -1) : event.key === 'ArrowRight' ? 0 : data.length - 1;
    show(data[Math.max(0, Math.min(data.length - 1, index))]);
  }, events);
  document.addEventListener('pointerdown', event => { if (!host.contains(event.target as Node)) hide(); }, events);
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    if (document.activeElement === tip) hit.focus({ preventScroll: true });
    hide();
  }, events);
  hit.addEventListener('blur', event => { if (event.relatedTarget !== tip) hide(); }, events);
  tip.addEventListener('blur', event => { if (event.relatedTarget !== hit) hide(); }, events);
  const visibleTicks = [...svg.querySelectorAll<SVGTextElement>('.time-tick')];
  visibleTicks.slice(1).forEach((tick, index) => {
    const previous = visibleTicks.slice(0, index + 1).reverse().find(node => node.isConnected)!;
    if (tick.getBoundingClientRect().left < previous.getBoundingClientRect().right + 8) tick.remove();
  });
  const updateTime = (at: number) => {
    if (!marker) return;
    marker.setAttribute('x1', String(x(at)));
    marker.setAttribute('x2', String(x(at)));
    marker.style.display = at < start || at > end ? 'none' : '';
    marker.setAttribute('aria-label', `${t('forecast_now')}: ${formatTimes([at], language, timezone, { hour: '2-digit', minute: '2-digit', second: '2-digit' })[0]}`);
  };
  if (currentTime !== undefined) updateTime(currentTime);
  if (selectedAt != null) show(data.find(point => point.at === selectedAt));
  return { updateTime, selectedAt: () => active?.at ?? null, dispose: () => {
    listeners.abort();
    hide();
    interaction.remove();
    tip.remove();
  } };
}
