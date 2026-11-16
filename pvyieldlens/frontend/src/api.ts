import type { Configuration, ConfigurationSaveResult, ConfigurationUpdate, ConnectionInput, ConnectionResult, ForecastRefreshResult, ForecastView, HistoryResponse, LiveHistoryResponse, Snapshot } from './models';

export class ApiError extends Error {
  constructor(public code: string, public fields: string[] = []) {
    super(code);
    this.name = 'ApiError';
  }
}

async function request(path: string, options: RequestInit = {}): Promise<unknown> {
  let response: Response;
  let body: unknown;
  try {
    response = await fetch(`api/${path}`, {
      credentials: 'same-origin', ...options,
      headers: { 'Content-Type': 'application/json', ...options.headers },
    });
    body = await response.json();
  } catch {
    throw new ApiError('error');
  }
  if (!response.ok) {
    const error = body !== null && typeof body === 'object' ? body : {};
    throw new ApiError('error' in error && typeof error.error === 'string' ? error.error : 'error',
      'fields' in error && Array.isArray(error.fields) ? error.fields.filter((field): field is string => typeof field === 'string') : []);
  }
  return body;
}

let configurationRequest: Promise<Configuration> | null = null;

export const api = {
  getConfiguration(): Promise<Configuration> {
    configurationRequest ??= request('config').then(body => body as Configuration).finally(() => { configurationRequest = null; });
    return configurationRequest;
  },
  async saveConfiguration(update: ConfigurationUpdate): Promise<ConfigurationSaveResult> {
    return await request('config', { method: 'PUT', body: JSON.stringify(update) }) as ConfigurationSaveResult;
  },
  async discoverEntities(connection: ConnectionInput | null): Promise<ConnectionResult> {
    return await request('connection', { method: 'POST', body: JSON.stringify(connection) }) as ConnectionResult;
  },
  async getSnapshot(): Promise<Snapshot> { return await request('snapshot') as Snapshot; },
  async getLiveHistory(): Promise<LiveHistoryResponse> { return await request('live-history') as LiveHistoryResponse; },
  async getForecast(): Promise<ForecastView> { return await request('forecast') as ForecastView; },
  async refreshForecast(): Promise<ForecastRefreshResult> {
    return await request('forecast/refresh', { method: 'POST' }) as ForecastRefreshResult;
  },
  async getHistory(start: number, end: number): Promise<HistoryResponse> {
    return await request(`history?${new URLSearchParams({ start: String(start), end: String(end) })}`) as HistoryResponse;
  },
};
