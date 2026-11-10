import { languages, selectLanguage, translate } from './i18n.js';

const catalogs = Object.fromEntries(await Promise.all(languages.map(async language => [language,
  await (await fetch(`static/locales/${language}.json`)).json()])));
let languageChoice = 'auto';
try {
  const saved = localStorage.getItem('pvyieldlens.language');
  if (languages.includes(saved)) languageChoice = saved;
} catch {
  // Language selection still works when browser storage is disabled.
}
let language = selectLanguage(navigator.languages?.length ? navigator.languages : [navigator.language || 'en'], languageChoice);
let configuration = null;
let snapshot = null;
let history = [];
let livePoints = [];
let lastHistoryKey = null;
let historyVersion = 0;
let lastHistoryDraw = '';
let formDirty = false;
const form = document.querySelector('#settings-form');
const t = (key, parameters) => translate(catalogs, language, key, parameters);
const number = (value, digits = 1) => value == null ? '—' : new Intl.NumberFormat(language, { maximumFractionDigits: digits }).format(value);
const el = id => document.getElementById(id);
const stamp = value => value == null ? '—' : new Intl.DateTimeFormat(language, {
  hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: snapshot?.timezone || configuration?.settings?.timezone || 'UTC',
}).format(new Date(value * 1000));

async function api(path, options = {}) {
  const response = await fetch(`api/${path}`, { credentials: 'same-origin', ...options,
    headers: { 'Content-Type': 'application/json', ...options.headers } });
  const body = await response.json();
  if (!response.ok) {
    const error = new Error(body.error || 'error');
    error.fields = body.fields || [];
    throw error;
  }
  return body;
}

function showPage(settings) {
  const returning = el('dashboard').hidden && !settings;
  el('dashboard').hidden = settings;
  el('configuration').hidden = !settings;
  el('overview-tab').classList.toggle('active', !settings);
  el('settings-tab').classList.toggle('active', settings);
  if (!settings) {
    if (returning) lastHistoryDraw = '';
    render();
    if (returning) fetchHistory().then(render).catch(error => {
      el('banner').hidden = false;
      el('banner').textContent = t(error.message);
    });
  }
}

function showMessage(id, key) {
  const node = el(id);
  node.dataset.i18n = key;
  node.textContent = t(key);
}

function applyLanguage() {
  document.documentElement.lang = language;
  document.querySelectorAll('[data-i18n]').forEach(node => { node.textContent = t(node.dataset.i18n); });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(node => { node.placeholder = t(node.dataset.i18nPlaceholder); });
  el('history-range').setAttribute('aria-label', t('history'));
  el('language-select').setAttribute('aria-label', t('language'));
  el('language-select').value = languageChoice;
  render();
}

function plot(id, data, series, unit) {
  const host = el(id);
  host.replaceChildren();
  const valid = data.flatMap(point => series.map(item => point[item.key])).filter(value => Number.isFinite(value));
  if (!data.length || !valid.length) {
    const message = document.createElement('div');
    message.className = 'chart-empty';
    message.textContent = t('plot_empty');
    host.append(message);
    return;
  }
  const width = Math.max(host.clientWidth, 320), height = host.clientHeight, left = 58, right = 18, top = 16, bottom = 34;
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
  for (let index = 0; index <= 4; index++) {
    const at = start + (end-start)*index/4;
    const text = new Intl.DateTimeFormat(language, { hour: '2-digit', minute: '2-digit',
      ...(end-start > 86400 ? { month:'numeric', day:'numeric' } : {}), timeZone:snapshot?.timezone || 'UTC' }).format(new Date(at*1000));
    add('text', { x:x(at), y:height-8, 'text-anchor':index === 0 ? 'start' : index === 4 ? 'end' : 'middle' }, text);
  }
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
    const last = selected.at(-1);
    if (Number.isFinite(last[item.key])) {
      const point = add('circle', { cx:x(last.at), cy:y(last[item.key]), r:3, fill:item.color });
      const title = document.createElementNS(svg.namespaceURI, 'title');
      title.textContent = `${t(item.label)}: ${number(last[item.key])} ${unit} · ${stamp(last.at)}`;
      point.append(title);
    }
  });
  host.append(svg);
}

const powerSeries = [{key:'estimated_power',label:'estimated',color:'#b65f00'}, {key:'actual_power',label:'actual',color:'#2563c6'}];

function render() {
  const settings = configuration?.settings;
  const live = snapshot?.realtime;
  const stat = snapshot?.statistics;
  el('setup-empty').hidden = Boolean(settings);
  el('connection-state').textContent = t(!settings ? 'unconfigured' : snapshot?.connected ? 'live' : 'offline');
  el('connection-state').classList.toggle('online', Boolean(snapshot?.connected));
  el('updated').textContent = t('updated', {time:stamp(snapshot?.calculated_at)});
  el('live-hint').textContent = t('realtime_hint', {window:settings?.realtime_window_seconds || 60,interval:settings?.update_seconds || 5});
  el('statistics-hint').textContent = t('statistics_hint', {interval:settings?.interval_minutes || 5});
  el('live-estimated').textContent = number(live?.estimated_power);
  el('live-actual').textContent = number(live?.actual_power);
  el('live-pr').textContent = number(live?.pr);
  el('live-opportunity').textContent = number(live?.optimizable_power);
  el('live-quality').textContent = t(live?.quality || 'waiting');
  el('live-coverage').textContent = `${t('coverage')} ${number(live?.coverage_percent)}%`;
  el('live-reason').textContent = live?.reason ? t(live.reason) : '';
  el('daily-energy').textContent = number(snapshot?.energy?.daily_kwh, 3);
  el('total-energy').textContent = number(snapshot?.energy?.total_kwh, 3);
  el('stat-estimated').textContent = `${number(stat?.estimated_power)} W`;
  el('stat-actual').textContent = `${number(stat?.actual_power)} W`;
  el('stat-pr').textContent = `${number(stat?.pr)}%`;
  el('stat-coverage').textContent = `${t('coverage')} ${number(stat?.coverage_percent)}% · ${t(stat?.quality || 'waiting')}`;
  el('last-settled').textContent = t('last_settled', {time:stamp(stat?.end)});
  el('timezone-note').textContent = `${t('timezone')}: ${snapshot?.timezone || settings?.timezone || 'UTC'}`;
  const warnings = [snapshot?.error, snapshot?.history_available === false ? 'history_unavailable' : null,
    snapshot?.energy?.daily_complete === false ? 'daily_energy_incomplete' : null].filter(Boolean);
  el('banner').hidden = !warnings.length;
  if (warnings.length) el('banner').textContent = warnings.map(key => t(key)).join(' ');
  el('source-rows').replaceChildren(...(snapshot?.sources || []).map(source => {
    const row = document.createElement('tr');
    const age = Math.max(0, Date.now()/1000 - source.reported_at);
    [source.entity_id, source.valid ? `${number(Number(source.state),2)} ${source.unit || ''}` : t('unavailable'), `${number(age,0)} s`].forEach(value => {
      const cell = document.createElement('td'); cell.textContent = value; row.append(cell);
    });
    return row;
  }));
  if (!el('dashboard').hidden) {
    plot('live-chart', livePoints, powerSeries, 'W');
    const drawKey = `${historyVersion}|${language}|${snapshot?.timezone}|${['history-chart', 'pr-chart'].map(id => `${el(id).clientWidth},${el(id).clientHeight}`).join('|')}`;
    if (drawKey !== lastHistoryDraw) {
      plot('history-chart', history, powerSeries, 'W');
      plot('pr-chart', history, [{key:'pr',label:'pr',color:'#2563c6'}], '%');
      lastHistoryDraw = drawKey;
    }
  }
}

async function loadConfiguration() {
  configuration = await api('config');
  if (!formDirty) {
    Object.entries(configuration.settings || {}).forEach(([key,value]) => {
      const input = form.elements.namedItem(key);
      if (input) input.value = value;
    });
    el('ha-url').value = configuration.connection.url;
  }
  el('connection-fields').hidden = configuration.mode === 'app';
  el('app-connection-note').hidden = configuration.mode !== 'app';
  render();
}

async function fetchHistory() {
  if (el('dashboard').hidden) return;
  const key = `${snapshot?.statistics?.revision}|${snapshot?.statistics?.end}|${el('history-range').value}`;
  const end = Date.now()/1000;
  history = (await api(`history?start=${Math.max(0,end-Number(el('history-range').value)*86400)}&end=${end}`)).windows.map(point => ({...point, at:point.end}));
  historyVersion += 1;
  lastHistoryKey = key;
}

async function poll() {
  try {
    snapshot = await api('snapshot');
    if (snapshot.calculated_at && livePoints.at(-1)?.at !== snapshot.calculated_at) {
      livePoints.push({at:snapshot.calculated_at,estimated_power:snapshot.realtime?.estimated_power ?? null,actual_power:snapshot.realtime?.actual_power ?? null});
      livePoints = livePoints.filter(point => point.at >= Date.now()/1000 - 1800).slice(-600);
    }
    if (!el('dashboard').hidden) {
      if (lastHistoryKey !== `${snapshot?.statistics?.revision}|${snapshot?.statistics?.end}|${el('history-range').value}`) await fetchHistory();
      const start = Math.max(0, Date.now()/1000 - Number(el('history-range').value)*86400);
      if (history[0]?.end <= start) {
        history = history.filter(point => point.end > start);
        historyVersion += 1;
      }
    }
    render();
  } catch (error) {
    el('banner').hidden = false;
    el('banner').textContent = t(error.message);
    el('connection-state').textContent = t('offline');
    el('connection-state').classList.remove('online');
  } finally {
    setTimeout(poll, (configuration?.settings?.update_seconds || 5)*1000);
  }
}

el('overview-tab').addEventListener('click', () => showPage(false));
el('settings-tab').addEventListener('click', () => showPage(true));
el('open-settings').addEventListener('click', () => showPage(true));
form.addEventListener('input', () => { formDirty = true; });
el('history-range').addEventListener('change', async () => {
  try { await fetchHistory(); render(); } catch (error) { el('banner').hidden = false; el('banner').textContent=t(error.message); }
});
window.addEventListener('languagechange', () => {
  language = selectLanguage(navigator.languages?.length ? navigator.languages : [navigator.language || 'en'], languageChoice);
  applyLanguage();
});
el('language-select').addEventListener('change', event => {
  languageChoice = event.target.value;
  try {
    if (languageChoice === 'auto') localStorage.removeItem('pvyieldlens.language');
    else localStorage.setItem('pvyieldlens.language', languageChoice);
  } catch {
    // Keep the current choice for this page when storage is unavailable.
  }
  language = selectLanguage(navigator.languages?.length ? navigator.languages : [navigator.language || 'en'], languageChoice);
  applyLanguage();
});

el('load-entities').addEventListener('click', async () => {
  const button = el('load-entities');
  button.disabled = true;
  showMessage('connection-result', 'connecting');
  try {
    const result = await api('connection', {method:'POST',body:JSON.stringify(configuration?.mode === 'app' ? null : {url:el('ha-url').value,token:el('ha-token').value})});
    for (const [role, units] of Object.entries({power:['W','kW'],temperature:['°C','°F','K'],irradiance:['W/m²','W/m2','W/m^2','kW/m²','kW/m2']})) {
      el(`${role}-options`).replaceChildren(...result.entities.filter(entity => units.includes(entity.unit)).map(entity => {
        const option = document.createElement('option'); option.value = entity.entity_id; option.textContent=`${entity.name} · ${entity.unit}`; return option;
      }));
    }
    configuration = {...configuration, settings:configuration?.settings || null, detectedTimezone:result.timezone};
    showMessage('connection-result', 'connected');
  } catch (error) { showMessage('connection-result', error.message); }
  finally { button.disabled=false; }
});

form.addEventListener('submit', async event => {
  event.preventDefault();
  const button=el('save-button'); button.disabled=true; showMessage('save-button', 'saving');
  form.querySelectorAll('[aria-invalid]').forEach(input => input.removeAttribute('aria-invalid'));
  const settings=Object.fromEntries([...new FormData(form)].map(([key,value]) => [key,key.endsWith('_entity') ? value.trim() : Number(value)]));
  settings.timezone=configuration?.detectedTimezone || configuration?.settings?.timezone || 'UTC';
  try {
    configuration=await api('config',{method:'PUT',body:JSON.stringify({settings,...(configuration?.mode==='app' ? {} : {connection:{url:el('ha-url').value,token:el('ha-token').value}})})});
    formDirty=false; el('ha-token').value=''; showMessage('save-result', 'saved'); livePoints=[]; lastHistoryKey=null; render();
  } catch (error) {
    showMessage('save-result', error.message);
    error.fields?.forEach(field => { const input=form.elements.namedItem(field.replace(/^settings\./,'')); if(input) input.setAttribute('aria-invalid','true'); });
  } finally { button.disabled=false; showMessage('save-button', 'save'); }
});

const chartResize = new ResizeObserver(() => render());
['history-chart', 'pr-chart'].forEach(id => chartResize.observe(el(id)));
applyLanguage();
try { await loadConfiguration(); } catch (error) { el('banner').hidden=false; el('banner').textContent=t(error.message); }
poll();
