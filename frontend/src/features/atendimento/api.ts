export type Queue = 'waiting' | 'bot' | 'mine' | 'assigned' | 'closed';
export type QueueCounts = Record<Queue, number | null>;
export const departmentLabels = { comercial: 'Comercial', financeiro: 'Financeiro', suporte: 'Suporte', sac: 'SAC' };
export type Department = keyof typeof departmentLabels;
export type OperatorFunction = { id: string; name: string; department: Department };
export interface Operator { id: string; name: string; tenant_id: string; role: 'admin' | 'operator'; platform_admin: boolean }
export interface Conversation {
  id: string; chat_id: string; customer_name: string | null; state: 'waiting' | 'bot' | 'assigned' | 'closed';
  assigned_user_id: string | null; last_interaction: string; origin_name: string | null;
  department: Department | null;
}
export interface Message {
  id: string; sender_type: 'customer' | 'bot' | 'operator'; sender_id: string | null;
  content: string; created_at: string; delivery_status: string | null;
}

export class ApiError extends Error {
  constructor(readonly status: number, message: string) { super(message); }
}

function csrfToken(): string | undefined {
  const prefix = 'nexus_atende_csrf=';
  return document.cookie.split('; ').find(cookie => cookie.startsWith(prefix))?.slice(prefix.length);
}

export function upload<T>(path: string, file: File, onProgress: (percent: number | null) => void, onSent: () => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open('PUT', `/api/v1${path}`);
    request.responseType = 'json';
    const token = csrfToken();
    if (token) request.setRequestHeader('X-CSRF-Token', token);
    request.upload.onprogress = event => onProgress(event.lengthComputable ? Math.round(event.loaded / event.total * 100) : null);
    request.upload.onload = onSent;
    request.onload = () => {
      if (request.status >= 200 && request.status < 300 && request.response) {
        resolve(request.response);
        return;
      }
      const body: { detail?: unknown } | null = request.response;
      const fallback = request.status === 413 ? 'O arquivo excede o limite de 4 MiB.' : `O servidor não confirmou a importação (HTTP ${request.status}).`;
      reject(new ApiError(request.status, typeof body?.detail === 'string' ? body.detail : fallback));
    };
    request.onerror = () => reject(new ApiError(0, 'A conexão caiu durante a importação. Confira a lista de fontes antes de tentar novamente.'));
    request.send(file);
  });
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (typeof options.body === 'string') headers.set('Content-Type', 'application/json');
  if (options.method && options.method !== 'GET') {
    const token = csrfToken();
    if (token) headers.set('X-CSRF-Token', token);
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
