export function plot(id, data, series, unit, {language, timezone, translate, tooltip = null, currentTime = null}) {
  const host = document.getElementById(id);
  const t = translate;
  const number = (value, digits = 1) => new Intl.NumberFormat(language, {maximumFractionDigits:digits}).format(value);
  const stamp = value => new Intl.DateTimeFormat(language, {hour:'2-digit', minute:'2-digit', second:'2-digit', timeZone:timezone}).format(new Date(value*1000));
  host.replaceChildren();
  const valid = data.flatMap(point => series.map(item => point[item.key])).filter(value => Number.isFinite(value));
  if (!data.length || !valid.length) {
    const message = document.createElement('div');
    message.className = 'chart-empty';
    message.textContent = t('plot_empty');
    host.append(message);
    return;
  }
  const width = Math.max(host.clientWidth, 1), height = host.clientHeight, left = 48, right = 12, top = 16, bottom = 34;
  const start = data[0].at, end = Math.max(data.at(-1).at, start + 1);
  const maximum = Math.max(1, ...valid) * 1.1;
  const minimum = Math.min(0, ...valid);
  const x = at => left + (at - start) / (end - start) * (width - left - right);
  const y = value => top + (maximum - value) / (maximum - minimum) * (height - top - bottom);
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', series.map(item => t(item.label)).join(' / '));
  const add = (tag, attrs, text) => {
    const node = document.createElementNS(svg.namespaceURI, tag);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
    if (text != null) node.textContent = text;
    svg.append(node);
    return node;
  };
  for (let index = 0; index <= 4; index++) {
    const value = minimum + (maximum - minimum) * index / 4;
    add('line', { x1: left, x2: width-right, y1: y(value), y2: y(value), class: 'grid' });
    add('text', { x: left-10, y: y(value)+4, 'text-anchor': 'end' }, number(value, 0));
  }
  add('text', { x: left, y: 9 }, unit);
  const duration = end-start;
  const spacing = duration > 86400 ? 120 : 76;
  const count = Math.max(2, Math.min(6, Math.floor((width-left-right)/spacing)+1));
  const step = [1, 5, 10, 15, 30, 60, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400, 172800, 604800]
    .find(value => value >= duration/(count-1)) || 604800;
  const times = [start, ...Array.from({length:Math.max(0, Math.ceil(end/step)-Math.ceil(start/step))},
    (_, index) => (Math.ceil(start/step)+index)*step).filter(at => at > start && at < end), end];
  const formatter = new Intl.DateTimeFormat(language, {timeZone:timezone,
    ...(duration > 86400 ? {month:'short', day:'numeric'} : {}),
    ...(duration <= 86400 || step < 86400 ? {hour:'2-digit', minute:'2-digit', ...(duration < 300 ? {second:'2-digit'} : {})} : {})});
  let previousTick = null;
  times.forEach((at, index) => {
    const text = formatter.format(new Date(at*1000));
    if (previousTick && (text === previousTick.textContent || x(at)-Number(previousTick.getAttribute('x')) < spacing)) return;
    previousTick = add('text', {x:x(at), y:height-8, class:'time-tick',
      'text-anchor':index === 0 ? 'start' : index === times.length-1 ? 'end' : 'middle'}, text);
  });
  const stride = Math.max(1, Math.ceil(data.length / 600));
  const selected = data.filter((point,index) => index % stride === 0 || index === data.length-1 || series.some(item => point[item.key] == null));
  series.forEach(item => {
    let connected = false;
    const commands = selected.map(point => {
      if (!Number.isFinite(point[item.key])) { connected = false; return ''; }
      const command = `${connected ? 'L' : 'M'}${x(point.at).toFixed(2)},${y(point[item.key]).toFixed(2)}`;
      connected = true;
      return command;
    });
    add('path', { d:commands.join(' '), stroke:item.color, class:'series' });
    (tooltip ? selected : [selected.at(-1)]).filter(point => Number.isFinite(point[item.key])).forEach(point => {
      const dot = add('circle', {cx:x(point.at), cy:y(point[item.key]), r:tooltip ? 5 : 3, fill:item.color});
      const title = document.createElementNS(svg.namespaceURI, 'title');
      title.textContent = tooltip ? tooltip(point) : `${t(item.label)}: ${number(point[item.key])} ${unit} · ${stamp(point.at)}`;
      dot.append(title);
    });
  });
  const marker = currentTime == null ? null : add('line', {class:'current-time', y1:top, y2:height-bottom});

  host.append(svg);
  const ticks = [...svg.querySelectorAll('.time-tick')];
  ticks.slice(1).forEach((tick, index) => {
    const previous = ticks.slice(0,index+1).findLast(node => node.isConnected);
    if (tick.getBoundingClientRect().left < previous.getBoundingClientRect().right + 8) tick.remove();
  });
  const updateTime = at => {
    if (!marker) return;
    marker.setAttribute('x1', x(at));
    marker.setAttribute('x2', x(at));
    marker.style.display = at < start || at > end ? 'none' : '';
    marker.setAttribute('aria-label', `${t('forecast_now')}: ${stamp(at)}`);
  };
  updateTime(currentTime);
  return updateTime;
}
