import type { ForecastInterval } from './models';
import type { Language } from './i18n';

export interface ChartPoint {
  at: number;
  estimated_power?: number | null;
  actual_power?: number | null;
  pr?: number | null;
  power_w?: number | null;
  interval?: ForecastInterval;
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
  tooltip?: (point: ChartPoint) => string;
  currentTime?: number;
}

export function plot(host: HTMLElement, data: ChartPoint[], series: ChartSeries[], unit: string,
  { language, timezone, translate: t, tooltip, currentTime }: ChartOptions) {
  const number = (value: number, digits = 1) => new Intl.NumberFormat(language, { maximumFractionDigits: digits }).format(value);
  const stamp = (value: number) => new Intl.DateTimeFormat(language, {
    hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: timezone,
  }).format(new Date(value * 1000));
  host.replaceChildren();
  const valid = data.flatMap(point => series.map(item => point[item.key]))
    .filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
  if (!data.length || !valid.length) {
    const message = document.createElement('div');
    message.className = 'chart-empty';
    message.textContent = t('plot_empty');
    host.append(message);
    return;
  }
  const width = Math.max(host.clientWidth, 1), height = host.clientHeight, left = 48, right = 12, top = 16, bottom = 34;
  const start = data[0].at, end = Math.max(data[data.length - 1].at, start + 1);
  const maximum = Math.max(1, ...valid) * 1.1;
  const minimum = Math.min(0, ...valid);
  const x = (at: number) => left + (at - start) / (end - start) * (width - left - right);
  const y = (value: number) => top + (maximum - value) / (maximum - minimum) * (height - top - bottom);
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', series.map(item => t(item.label)).join(' / '));
  const add = <K extends keyof SVGElementTagNameMap>(tag: K, attrs: Record<string, string | number>, text?: string) => {
    const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
    if (text !== undefined) node.textContent = text;
    svg.append(node);
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
  const formatter = new Intl.DateTimeFormat(language, { timeZone: timezone,
    ...(duration > 86400 ? { month: 'short', day: 'numeric' } : {}),
    ...(duration <= 86400 || step < 86400 ? { hour: '2-digit', minute: '2-digit', ...(duration < 300 ? { second: '2-digit' } : {}) } : {}),
  });
  let previousTick: SVGTextElement | undefined;
  times.forEach((at, index) => {
    const text = formatter.format(new Date(at * 1000));
    if (previousTick && (text === previousTick.textContent || x(at) - Number(previousTick.getAttribute('x')) < spacing)) return;
    previousTick = add('text', { x: x(at), y: height - 8, class: 'time-tick',
      'text-anchor': index === 0 ? 'start' : index === times.length - 1 ? 'end' : 'middle' }, text);
  });
  const stride = Math.max(1, Math.ceil(data.length / 600));
  const selected = data.filter((point, index) => index % stride === 0 || index === data.length - 1 || series.some(item => point[item.key] == null));
  series.forEach(item => {
    let connected = false;
    const commands = selected.map(point => {
      const value = point[item.key];
      if (value == null || !Number.isFinite(value)) { connected = false; return ''; }
      const command = `${connected ? 'L' : 'M'}${x(point.at).toFixed(2)},${y(value).toFixed(2)}`;
      connected = true;
      return command;
    });
    add('path', { d: commands.join(' '), stroke: item.color, class: 'series' });
    (tooltip ? selected : selected.slice(-1)).forEach(point => {
      const value = point[item.key];
      if (value == null || !Number.isFinite(value)) return;
      const dot = add('circle', { cx: x(point.at), cy: y(value), r: tooltip ? 5 : 3, fill: item.color });
      const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
      title.textContent = tooltip ? tooltip(point) : `${t(item.label)}: ${number(value)} ${unit} · ${stamp(point.at)}`;
      dot.append(title);
    });
  });
  const marker = currentTime === undefined ? null : add('line', { class: 'current-time', y1: top, y2: height - bottom });
  host.append(svg);
  const ticks = [...svg.querySelectorAll<SVGTextElement>('.time-tick')];
  ticks.slice(1).forEach((tick, index) => {
    const previous = ticks.slice(0, index + 1).reverse().find(node => node.isConnected)!;
    if (tick.getBoundingClientRect().left < previous.getBoundingClientRect().right + 8) tick.remove();
  });
  const updateTime = (at: number) => {
    if (!marker) return;
    marker.setAttribute('x1', String(x(at)));
    marker.setAttribute('x2', String(x(at)));
    marker.style.display = at < start || at > end ? 'none' : '';
    marker.setAttribute('aria-label', `${t('forecast_now')}: ${stamp(at)}`);
  };
  if (currentTime !== undefined) updateTime(currentTime);
  return updateTime;
}
