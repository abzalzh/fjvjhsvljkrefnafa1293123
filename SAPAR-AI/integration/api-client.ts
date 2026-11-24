import type { Destination, TripPreferences, TripResponse, ParseRequest, ParseResponse, ExplainRequest, ExplainResponse, ErrorResponse } from './api-types';

export class SaparApiError extends Error {
  constructor(public status: number, public body: unknown) {
    super(`SAPAR API returned HTTP ${status}`);
  }
}

export function createSaparClient(baseUrl: string) {
  const base = baseUrl.replace(/\/$/, '');
  async function request<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
    const response = await fetch(`${base}/api${path}`, {
      method: body === undefined ? 'GET' : 'POST',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
    const data: unknown = await response.json();
    if (!response.ok) throw new SaparApiError(response.status, data as ErrorResponse);
    return data as T;
  }
  return {
    destinations: (signal?: AbortSignal) => request<Destination[]>('/destinations', undefined, signal),
    destination: (id: string, signal?: AbortSignal) => request<Destination>(`/destinations/${encodeURIComponent(id)}`, undefined, signal),
    generate: (p: TripPreferences, signal?: AbortSignal) => request<TripResponse>('/trips/generate', p, signal),
    recalculate: (p: TripPreferences, signal?: AbortSignal) => request<TripResponse>('/trips/recalculate', p, signal),
    parse: (p: ParseRequest, signal?: AbortSignal) => request<ParseResponse>('/ai/parse', p, signal),
    explain: (p: ExplainRequest, signal?: AbortSignal) => request<ExplainResponse>('/ai/explain', p, signal),
  };
}
