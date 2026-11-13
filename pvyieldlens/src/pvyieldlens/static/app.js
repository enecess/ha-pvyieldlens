import { plot } from './charts.js';
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
let historySummary = null;
let currentPage = 'live';
let previousDataPage = 'live';
let livePoints = [];
let lastHistoryKey = null;
let historyVersion = 0;
let lastHistoryDraw = '';
let forecastData = null;
let selectedForecastDay = null;
let lastForecastDraw = '';
let forecastVersion = 0;
let forecastRequest = null;
let updateForecastTime = null;
const forecastKey = view => `${view?.fetched_at}|${view?.timezone}|${view?.today?.start}|${view?.seven_days?.end}`;
const chartOptions = () => ({language, timezone:snapshot?.timezone || configuration?.settings?.timezone || 'UTC', translate:t});
const editedFields = new Set();
let entitiesLoaded = false;
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

function showPage(page) {
  if (page === currentPage) return;
  if (page === 'settings') previousDataPage = currentPage;
  currentPage = page;
  window.scrollTo(0, 0);
  ['live', 'history', 'forecast'].forEach(name => {
    el(`${name}-page`).hidden = page !== name;
    el(`${name}-tab`).classList.toggle('active', page === name);
    el(`${name}-tab`).setAttribute('aria-current', page === name ? 'page' : 'false');
  });
  el('configuration').hidden = page !== 'settings';
  el('data-navigation').hidden = page === 'settings';
  render();
  if (page === 'settings') loadEntities();
  if (page === 'forecast') fetchForecast();
  if (page === 'history') fetchHistory().then(render).catch(error => {
    el('banner').hidden = false;
    el('banner').textContent = t(error.message);
  });
}

function showSettingsCategory(category) {
  document.querySelectorAll('[data-settings-section]').forEach(section => {
    section.hidden = section.dataset.settingsSection !== category;
  });
  document.querySelectorAll('[data-settings-category]').forEach(button => {
    button.setAttribute('aria-pressed', String(button.dataset.settingsCategory === category));
  });
}

function updateForecastControls() {
  ['forecast_tilt_deg', 'forecast_azimuth_deg'].forEach(name => {
    form.elements.namedItem(name).required = form.elements.namedItem('forecast_enabled').checked;
  });
  el('forecast-azimuth-row').hidden = el('forecast-direction').value !== 'custom';
}

function revealInvalid(input) {
  showSettingsCategory(input.closest('[data-settings-section]').dataset.settingsSection);
  const details = input.closest('details');
  if (details) details.open = true;
  if (input.name === 'forecast_azimuth_deg') {
    el('forecast-direction').value = 'custom';
    updateForecastControls();
  }
  input.focus();
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
  el('settings-button').setAttribute('aria-label', t('settings'));
  el('data-navigation').setAttribute('aria-label', t('data_pages'));
  el('settings-categories').setAttribute('aria-label', t('settings_categories'));
  el('forecast-days').setAttribute('aria-label', t('forecast_daily'));
  el('history-range').setAttribute('aria-label', t('history'));
  el('language-select').setAttribute('aria-label', t('language'));
  el('language-select').value = languageChoice;
  ['live-coverage', 'stat-coverage'].forEach(id => { el(id).title = t('coverage_help'); });
  render();
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
  el('history-energy').textContent = number(historySummary?.estimated_energy_kwh, 3);
  el('history-pr').textContent = number(historySummary?.pr);
  el('stat-coverage').textContent = `${number(historySummary?.coverage_percent)}%`;
  const boundaryFormat = new Intl.DateTimeFormat(language, {year:'numeric', month:'short', day:'numeric',
    hour:'2-digit', minute:'2-digit', second:'2-digit', timeZone:snapshot?.timezone || settings?.timezone || 'UTC'});
  el('history-boundaries').textContent = historySummary?.start == null ? t('history_no_periods') :
    t('history_boundaries', {start:boundaryFormat.format(new Date(historySummary.start*1000)),
      end:boundaryFormat.format(new Date(historySummary.end*1000)), timezone:snapshot?.timezone || settings?.timezone || 'UTC'});
  el('settings-back').textContent = `← ${t('back_to', {page:t(previousDataPage === 'live' ? 'live_page' : previousDataPage)})}`;
  el('draft-status').hidden = !editedFields.size;
  const location = configuration?.location;
  el('forecast-location').textContent = location ? `${location.location_name || t('ha_location')} · ${number(location.latitude, 5)}, ${number(location.longitude, 5)} · ${location.timezone}` : t('location_unavailable');
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
  el('source-empty').hidden = Boolean(snapshot?.sources?.length);
  if (currentPage === 'live') plot('live-chart', livePoints, powerSeries, 'W', chartOptions());
  if (currentPage === 'history') {
    const drawKey = `${historyVersion}|${language}|${snapshot?.timezone}|${['history-chart', 'pr-chart'].map(id => `${el(id).clientWidth},${el(id).clientHeight}`).join('|')}`;
    if (drawKey !== lastHistoryDraw) {
      plot('history-chart', history, powerSeries, 'W', chartOptions());
      plot('pr-chart', history, [{key:'pr',label:'pr',color:'#2563c6'}], '%', chartOptions());
      lastHistoryDraw = drawKey;
    }
  }
  if (currentPage === 'forecast') renderForecast();
}

async function loadConfiguration() {
  configuration = await api('config');
  Object.entries(configuration.settings || {}).forEach(([key,value]) => {
    const input = form.elements.namedItem(key);
    if (input && !editedFields.has(key)) input.value = value;
  });
  Object.entries(configuration.forecast_settings).forEach(([key, value]) => {
    const input = form.elements.namedItem(`forecast_${key}`);
    if (!editedFields.has(input.name)) {
      if (key === 'enabled') input.checked = value;
      else input.value = value ?? '';
    }
  });
  if (!editedFields.has('forecast_azimuth_deg')) {
    const azimuth = form.elements.namedItem('forecast_azimuth_deg').value;
    el('forecast-direction').value = ['0', '90', '180', '270'].includes(azimuth) ? azimuth : azimuth ? 'custom' : '';
  }
  updateForecastControls();
  if (!editedFields.has('ha-url')) el('ha-url').value = configuration.connection.url;
  el('connection-fields').hidden = configuration.mode === 'app';
  el('app-connection-note').hidden = configuration.mode !== 'app';
  render();
  if (!el('configuration').hidden) loadEntities();
}

async function fetchHistory(force = false) {
  if (currentPage !== 'history') return;
  const key = `${snapshot?.statistics?.revision}|${snapshot?.statistics?.end}|${el('history-range').value}`;
  const end = Date.now()/1000;
  const start = Math.max(0, end - Number(el('history-range').value)*86400);
  if (!force && key === lastHistoryKey && !history.some(point => point.start < start)) return;
  const result = await api(`history?start=${start}&end=${end}`);
  history = result.windows.filter(point => point.start >= result.requested_range.start && point.end <= result.requested_range.end)
    .map(point => ({...point, at:point.end}));
  historySummary = result.summary;
  historyVersion += 1;
  lastHistoryKey = key;
}

async function fetchForecast() {
  if (currentPage !== 'forecast' || forecastRequest) return;
  forecastRequest = api('forecast');
  try {
    const result = await forecastRequest;
    if (JSON.stringify([forecastData?.fetched_at, forecastData?.timezone, forecastData?.days, forecastData?.intervals]) !==
        JSON.stringify([result.fetched_at, result.timezone, result.days, result.intervals])) forecastVersion += 1;
    forecastData = result;
    if (currentPage === 'forecast') renderForecast();
  } catch (error) {
    el('forecast-error').textContent = t(error.message);
  } finally {
    forecastRequest = null;
  }
}

function renderForecast() {
  const light = snapshot?.forecast;
  const view = light && (!forecastData || light.calculated_at >= forecastData.calculated_at) ? light : forecastData;
  const matching = forecastData && forecastKey(view) === forecastKey(forecastData);
  const timezone = view?.timezone || snapshot?.timezone || 'UTC';
  const dateFormat = new Intl.DateTimeFormat(language, {month:'short', day:'numeric', timeZone:timezone});
  const timeFormat = new Intl.DateTimeFormat(language, {year:'numeric', month:'short', day:'numeric',
    hour:'2-digit', minute:'2-digit', hourCycle:'h23', timeZone:timezone, timeZoneName:'longOffset'});
  const time = value => timeFormat.format(new Date(value*1000));
  const intervalTime = new Intl.DateTimeFormat(language, {hour:'2-digit', minute:'2-digit', hourCycle:'h23',
    timeZone:timezone, timeZoneName:'longOffset'});
  const status = view?.status || 'loading';
  el('forecast-status').dataset.status = status;
  el('forecast-status').textContent = t(`forecast_status_${status}`);
  el('forecast-error').textContent = view?.last_error ? t('forecast_fetch_failed') : '';
  el('forecast-remaining').textContent = number(view?.remaining_today?.kwh, 3);
  el('forecast-tomorrow').textContent = number(view?.tomorrow?.kwh, 3);
  el('forecast-seven-days').textContent = `${number(view?.seven_days?.kwh, 3)} kWh`;
  el('forecast-fetched').textContent = view?.fetched_at == null ? t('forecast_never_fetched') : t('forecast_fetched', {time:time(view.fetched_at)});
  el('forecast-timezone').textContent = `${t('timezone')}: ${timezone}`;
  el('forecast-refresh-state').textContent = view?.refreshing ? t('forecast_refreshing') : '';
  el('forecast-refresh').disabled = Boolean(view?.refreshing) || ['disabled', 'location_unavailable'].includes(status);
  const days = matching ? forecastData.days : [];
  if (days.length && !days.some(day => day.day === selectedForecastDay)) selectedForecastDay = days[0].day;
  el('forecast-data').hidden = !days.length;
  const selected = days.find(day => day.day === selectedForecastDay);
  el('forecast-day-heading').textContent = selected ? dateFormat.format(new Date(selected.start*1000)) : t('forecast_hourly');
  el('forecast-day-total').textContent = `${number(selected?.kwh, 3)} kWh`;
  el('forecast-day-coverage').textContent = selected ? `${t(selected.quality)} · ${t('coverage')} ${number(selected.coverage_percent)}%` : '';
  const drawKey = `${forecastVersion}|${matching}|${selectedForecastDay}|${language}|${timezone}|${el('forecast-chart').clientWidth},${el('forecast-chart').clientHeight}`;
  if (drawKey !== lastForecastDraw) {
    const maximum = Math.max(1, ...days.map(day => day.kwh ?? 0));
    el('forecast-days').replaceChildren(...days.map(day => {
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.day = day.day;
      button.setAttribute('aria-pressed', String(day.day === selectedForecastDay));
      const date = dateFormat.format(new Date(day.start*1000));
      button.setAttribute('aria-label', `${date}: ${number(day.kwh, 3)} kWh · ${t(day.quality)}`);
      const label = document.createElement('span');
      label.className = 'day-label';
      label.textContent = date;
      const bar = document.createElement('span');
      bar.className = `day-bar${day.kwh == null ? ' unavailable' : ''}`;
      bar.style.setProperty('--bar-height', `${day.kwh == null ? 100 : Math.max(1, day.kwh/maximum*100)}%`);
      bar.setAttribute('aria-hidden', 'true');
      const value = document.createElement('span');
      value.textContent = number(day.kwh, 3);
      button.append(label, bar, value);
      button.addEventListener('click', () => {selectedForecastDay = day.day; renderForecast(); el('forecast-days').querySelector(`[data-day="${day.day}"]`).focus({preventScroll:true});});
      return button;
    }));
    const rows = selected ? forecastData.intervals.filter(row => row.end > selected.start && row.start < selected.end)
      .map(row => ({...row, start:Math.max(row.start, selected.start), end:Math.min(row.end, selected.end),
        energy_kwh:row.energy_kwh == null ? null : row.energy_kwh *
          (Math.min(row.end, selected.end)-Math.max(row.start, selected.start))/(row.end-row.start)})) : [];
    const details = row => `${time(row.start)} – ${time(row.end)} · ${t('forecast_poa')}: ${number(row.poa_w_m2)} W/m² · ${t('forecast_air')}: ${number(row.air_temperature_c)} °C · ${t('forecast_cell')}: ${number(row.cell_temperature_c)} °C · ${t('forecast_power')}: ${number(row.power_w)} W · ${t('forecast_interval_energy')}: ${number(row.energy_kwh, 3)} kWh`;
    updateForecastTime = plot('forecast-chart', rows.flatMap(row => [
      {at:row.start, power_w:row.power_w, interval:row}, {at:row.end, power_w:row.power_w, interval:row}]),
      [{key:'power_w',label:'forecast_power',color:'#b65f00'}], 'W',
      {language, timezone, translate:t, tooltip:point => details(point.interval), currentTime:Date.now()/1000});
    el('forecast-rows').replaceChildren(...rows.map(row => {
      const tr = document.createElement('tr');
      const period = document.createElement('td');
      [row.start, row.end].forEach((at, index) => {
        const instant = document.createElement('time');
        instant.dateTime = new Date(at*1000).toISOString();
        instant.setAttribute('aria-label', time(at));
        instant.title = time(at);
        instant.textContent = `${index ? '→ ' : ''}${index && at === selected.end ? `${dateFormat.format(new Date(at*1000))} ` : ''}${intervalTime.format(new Date(at*1000))}`;
        period.append(instant);
      });
      tr.append(period);
      [number(row.poa_w_m2), number(row.air_temperature_c),
        number(row.cell_temperature_c), number(row.power_w), number(row.energy_kwh,3)].forEach(value => {
        const cell = document.createElement('td'); cell.textContent = value; tr.append(cell);
      });
      return tr;
    }));
    lastForecastDraw = drawKey;
  }
  updateForecastTime?.(Date.now()/1000);
}

async function poll() {
  try {
    const previousForecast = snapshot?.forecast;
    snapshot = await api('snapshot');
    if (configuration) configuration.location = snapshot.location;
    if (currentPage === 'forecast' && (!forecastData || snapshot.forecast?.calculated_at >= forecastData.calculated_at) &&
        (forecastKey(snapshot.forecast) !== forecastKey(forecastData) ||
        previousForecast?.refreshing && !snapshot.forecast?.refreshing)) await fetchForecast();
    if (snapshot.calculated_at && livePoints.at(-1)?.at !== snapshot.calculated_at) {
      livePoints.push({at:snapshot.calculated_at,estimated_power:snapshot.realtime?.estimated_power ?? null,actual_power:snapshot.realtime?.actual_power ?? null});
      livePoints = livePoints.filter(point => point.at >= Date.now()/1000 - 1800).slice(-600);
    }
    await fetchHistory();
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

['live', 'history', 'forecast'].forEach(page => el(`${page}-tab`).addEventListener('click', () => showPage(page)));
el('forecast-refresh').addEventListener('click', async () => {
  el('forecast-refresh').disabled = true;
  el('forecast-refresh-state').textContent = t('forecast_refreshing');
  try {
    await api('forecast/refresh', {method:'POST'});
    if (snapshot?.forecast) snapshot.forecast.refreshing = true;
    if (forecastData) forecastData.refreshing = true;
  } catch (error) {
    el('forecast-error').textContent = t(error.message);
    el('forecast-refresh').disabled = false;
    el('forecast-refresh-state').textContent = '';
  }
});
el('settings-button').addEventListener('click', () => showPage('settings'));
el('settings-back').addEventListener('click', () => showPage(previousDataPage));
el('open-settings').addEventListener('click', () => showPage('settings'));
el('open-forecast-settings').addEventListener('click', () => {
  showPage('settings');
  showSettingsCategory('forecast');
});
document.querySelectorAll('[data-settings-category]').forEach(button => {
  button.addEventListener('click', () => showSettingsCategory(button.dataset.settingsCategory));
});
form.addEventListener('input', event => {
  editedFields.add(event.target.name || event.target.id);
  if (event.target.setCustomValidity) event.target.setCustomValidity('');
  event.target.removeAttribute('aria-invalid');
  el('draft-status').hidden = false;
  el('save-result').textContent = '';
  delete el('save-result').dataset.i18n;
  updateForecastControls();
});
el('forecast-direction').addEventListener('change', event => {
  if (event.target.value !== 'custom') form.elements.namedItem('forecast_azimuth_deg').value = event.target.value;
  editedFields.add('forecast_azimuth_deg');
  updateForecastControls();
});
el('history-range').addEventListener('change', async () => {
  try { await fetchHistory(true); render(); } catch (error) { el('banner').hidden = false; el('banner').textContent=t(error.message); }
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

async function loadEntities(manual = false) {
  const button = el('load-entities');
  if (button.disabled || (!manual && (entitiesLoaded || !(configuration?.mode === 'app' ||
      (configuration?.connection.url && configuration.connection.token_set))))) return;
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
    entitiesLoaded = true;
    showMessage('connection-result', 'connected');
  } catch (error) { showMessage('connection-result', error.message); }
  finally { button.disabled=false; }
}

el('load-entities').addEventListener('click', () => loadEntities(true));

form.addEventListener('submit', async event => {
  event.preventDefault();
  form.querySelectorAll('[aria-invalid]').forEach(input => input.removeAttribute('aria-invalid'));
  const azimuth = form.elements.namedItem('forecast_azimuth_deg');
  azimuth.setCustomValidity(azimuth.value !== '' && azimuth.valueAsNumber >= 360 ? t('azimuth_help') : '');
  const noct = form.elements.namedItem('forecast_noct_c');
  noct.setCustomValidity(noct.value !== '' && noct.valueAsNumber <= 20 ? t('noct_help') : '');
  const invalid = [...form.elements].find(input => input.willValidate && !input.validity.valid);
  if (invalid) {
    revealInvalid(invalid);
    invalid.reportValidity();
    return;
  }
  const button = el('save-button');
  button.disabled = true;
  showMessage('save-button', 'saving');
  const settings = Object.fromEntries([...new FormData(form)].filter(([key]) => !key.startsWith('forecast_'))
    .map(([key, value]) => [key, key.endsWith('_entity') ? value.trim() : Number(value)]));
  settings.timezone = configuration?.detectedTimezone || configuration?.settings?.timezone || 'UTC';
  const forecast_settings = {
    enabled:form.elements.namedItem('forecast_enabled').checked,
    tilt_deg:form.elements.namedItem('forecast_tilt_deg').value === '' ? null : form.elements.namedItem('forecast_tilt_deg').valueAsNumber,
    azimuth_deg:azimuth.value === '' ? null : azimuth.valueAsNumber,
    noct_c:noct.valueAsNumber,
  };
  try {
    configuration = await api('config', {method:'PUT', body:JSON.stringify({settings, forecast_settings,
      ...(configuration?.mode === 'app' ? {} : {connection:{url:el('ha-url').value, token:el('ha-token').value}})})});
    editedFields.clear();
    el('ha-token').value = '';
    showMessage('save-result', 'saved');
    if (configuration.monitoring_changed) livePoints = [];
    lastHistoryKey = null;
    render();
  } catch (error) {
    showMessage('save-result', error.message);
    const invalidInputs = (error.fields || []).map(field => field.startsWith('connection.') ? el(`ha-${field.split('.')[1]}`) :
      form.elements.namedItem(field.replace(/^settings\./, '').replace(/^forecast_settings\./, 'forecast_'))).filter(Boolean);
    if (error.message === 'connection_required') invalidInputs.push(el('ha-token'));
    invalidInputs.forEach(input => input.setAttribute('aria-invalid', 'true'));
    const first = [...form.elements].find(input => invalidInputs.includes(input));
    if (first) revealInvalid(first);
  } finally {
    button.disabled = false;
    showMessage('save-button', 'save');
  }
});

const chartResize = new ResizeObserver(() => render());
['live-chart', 'history-chart', 'pr-chart', 'forecast-chart'].forEach(id => chartResize.observe(el(id)));
applyLanguage();
try { await loadConfiguration(); } catch (error) { el('banner').hidden=false; el('banner').textContent=t(error.message); }
poll();
