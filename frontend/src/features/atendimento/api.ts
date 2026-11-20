export type Queue = 'waiting' | 'bot' | 'mine' | 'assigned';
export interface Operator { id: string; name: string; tenant_id: string; role: 'admin' | 'operator' }
export interface Conversation {
  id: string; chat_id: string; customer_name: string | null; state: 'waiting' | 'bot' | 'assigned';
  assigned_user_id: string | null; last_interaction: string;
}
export interface Message {
  id: string; sender_type: 'customer' | 'bot' | 'operator'; sender_id: string | null;
  content: string; created_at: string; delivery_status: string | null;
}

export class ApiError extends Error {
  constructor(readonly status: number, message: string) { super(message); }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (typeof options.body === 'string') headers.set('Content-Type', 'application/json');
  if (options.method && options.method !== 'GET') {
    const token = document.cookie.split('; ').find(cookie => cookie.startsWith('nexus_atende_csrf='));
    if (token) headers.set('X-CSRF-Token', token.slice('nexus_atende_csrf='.length));
  }
  const result = await fetch(`/api/v1${path}`, { ...options, headers, cache: 'no-store' });
  if (!result.ok) {
    const body: { detail?: unknown } | null = await result.json().catch(() => null);
    throw new ApiError(result.status, typeof body?.detail === 'string' ? body.detail : `Não foi possível concluir a solicitação (${result.status}).`);
  }
  return result.status === 204 ? undefined as T : result.json();
}

export function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : 'A conexão falhou. Tente novamente.';
}
