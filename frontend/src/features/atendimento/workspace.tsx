'use client';

import { Button } from '@astryxdesign/core/Button';
import { VStack } from '@astryxdesign/core/Layout';
import Image from 'next/image';
import { useEffect, useState, type FormEvent } from 'react';
import logo from '../../assets/nexus-atende.webp';
import { api, ApiError, errorMessage, type Conversation, type Operator, type Queue } from './api';
import { Thread } from './thread';
import { Settings } from './settings';
import { PasswordSettings } from './PasswordSettings';
import { ClientSettings } from './ClientSettings';

const queues: { id: Queue; label: string }[] = [
  { id: 'waiting', label: 'Em espera' }, { id: 'mine', label: 'Meus atendimentos' },
  { id: 'bot', label: 'Com a IA' }, { id: 'assigned', label: 'Todos atribuídos' },
];
export const fieldStyle = 'w-full rounded-lg border border-current/20 bg-transparent px-3 py-2 focus-visible:outline-2 focus-visible:outline-offset-2';
const time = new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit' });

function Login({ onLogin }: { onLogin: (operator: Operator) => void }) {
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [company, setCompany] = useState('');
  const [companies, setCompanies] = useState<{ id: string; name: string }[]>();
  useEffect(() => {
    const controller = new AbortController();
    api<{ id: string; name: string }[]>('/auth/companies', { signal: controller.signal }).then(items => {
      setCompanies(items);
      const value = new URLSearchParams(window.location.search).get('empresa');
      if (value && items.some(item => item.id === value)) setCompany(value);
    }).catch(failure => { if (!controller.signal.aborted) setError(errorMessage(failure)); });
    return () => controller.abort();
  }, []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const credentials = Object.fromEntries(new FormData(event.currentTarget));
    setBusy(true); setError('');
    const tenantId = credentials.tenant_id === 'platform' ? null : credentials.tenant_id;
    try { onLogin(await api<Operator>('/auth/login', { method: 'POST', body: JSON.stringify({ ...credentials, tenant_id: tenantId }) })); }
    catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(false); }
  }
  return <main className="grid min-h-dvh place-items-center bg-slate-100 p-6 text-slate-900">
    <form onSubmit={submit} className="grid w-full max-w-md gap-5 rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
      <header><h1><Image src={logo} alt="Nexus Atende" className="h-auto w-64 max-w-full rounded-lg" unoptimized /></h1><p className="mt-3 text-slate-600">Acesse o painel de atendimento.</p></header>
      <label className="grid gap-2 text-sm font-medium">Empresa<select required name="tenant_id" value={company} onChange={event => setCompany(event.target.value)} className={fieldStyle}>
        <option value="" disabled>{companies ? 'Selecione a empresa' : 'Selecione o tipo de acesso'}</option>
        {companies?.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
        <option value="platform">SuperAdmin</option>
      </select></label>
      <label className="grid gap-2 text-sm font-medium">E-mail<input required type="email" name="email" autoComplete="username" className={fieldStyle} /></label>
      <label className="grid gap-2 text-sm font-medium">Senha<input required type="password" name="password" autoComplete="current-password" className={fieldStyle} /></label>
      {error && <p role="alert" className="text-red-700">{error}</p>}
      <Button type="submit" label="Entrar" variant="primary" isLoading={busy} />
    </form>
  </main>;
}

export function Workspace() {
  const [operator, setOperator] = useState<Operator | null | undefined>(undefined);
  const [queue, setQueue] = useState<Queue>('waiting');
  const [offset, setOffset] = useState(0);
  const [rows, setRows] = useState<Conversation[]>([]);
  const [selected, setSelected] = useState<string>();
  const [revision, setRevision] = useState(0);
  const [view, setView] = useState<'inbox' | 'settings' | 'password' | 'clients'>('inbox');
  const [error, setError] = useState('');
  const [queueError, setQueueError] = useState('');
  const [connected, setConnected] = useState(false);
  const refresh = () => setRevision(value => value + 1);

  useEffect(() => {
    const controller = new AbortController();
    api<Operator>('/auth/me', { signal: controller.signal }).then(setOperator).catch(failure => {
      if (controller.signal.aborted) return;
      if (!(failure instanceof ApiError && failure.status === 401)) setError(errorMessage(failure));
      setOperator(null);
    });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!operator) return;
    const events = new EventSource('/api/v1/conversations/events');
    events.addEventListener('change', refresh);
    events.onopen = () => setConnected(true);
    events.onerror = () => setConnected(false);
    const timer = window.setInterval(refresh, 20_000);
    return () => { events.close(); window.clearInterval(timer); };
  }, [operator]);

  useEffect(() => {
    if (!operator) return;
    const controller = new AbortController();
    api<Conversation[]>(`/conversations?queue=${queue}&offset=${offset}`, { signal: controller.signal }).then(items => {
      setRows(items); setQueueError('');
    }).catch(failure => {
      if (controller.signal.aborted) return;
      if (failure instanceof ApiError && failure.status === 401) setOperator(null);
      else setQueueError(`Fila de conversas · ${errorMessage(failure)}`);
    });
    return () => controller.abort();
  }, [operator, queue, offset, revision]);

  async function logout() {
    try { await api('/auth/logout', { method: 'POST' }); }
    catch (failure) {
      if (!(failure instanceof ApiError && failure.status === 401)) { setError(errorMessage(failure)); return; }
    }
    setOperator(null); setRows([]); setSelected(undefined); setQueue('waiting'); setOffset(0); setView('inbox'); setConnected(false); setQueueError('');
  }

  if (operator === undefined) return <main className="p-8" aria-busy>Carregando sessão…</main>;
  if (!operator) return <><Login onLogin={actor => { setError(''); setOperator(actor); }} />{error && <p role="alert" className="p-4 text-center text-red-700">{error}</p>}</>;
  const active = rows.find(row => row.id === selected);
  return <main className="min-h-dvh bg-slate-100 text-slate-900">
    <header className="flex flex-wrap items-center justify-between gap-3 bg-nexus-petroleo px-5 py-4 text-white">
      <h1><Image src={logo} alt="Nexus Atende" className="h-auto w-32 rounded-md" unoptimized /></h1>
      <nav aria-label="Área de trabalho" className="flex flex-wrap items-center gap-4 text-sm">
        <button className="underline" onClick={() => setView('inbox')}>Atendimento</button>
        {operator.role === 'admin' && <button className="underline" onClick={() => setView('settings')}>Configurações</button>}
        {operator.platform_admin && <button className="underline" onClick={() => setView('clients')}>Clientes</button>}
        <button className="underline" onClick={() => setView('password')}>Alterar senha</button>
        <p>{operator.name}</p><button className="underline" onClick={logout}>Sair</button>
      </nav>
    </header>
    {error && <p role="alert" className="bg-red-50 px-5 py-2 text-red-800">{error}</p>}
    {view === 'password' ? <PasswordSettings /> : view === 'clients' && operator.platform_admin ? <ClientSettings platformTenant={operator.tenant_id} /> : view === 'settings' ? <Settings platformAdmin={operator.platform_admin} /> : <section className="mx-auto grid max-w-screen-2xl gap-4 p-4 md:min-h-[calc(100dvh-3.75rem)] md:grid-cols-[20rem_minmax(0,1fr)]" aria-label="Caixa de entrada">
      <aside className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
        {queueError && <p role="alert" className="bg-red-50 p-4 text-sm text-red-800">{queueError}</p>}
        <header className="grid gap-2 border-b border-slate-200 p-4"><h2 className="text-lg font-semibold">Conversas</h2>
          <p className="text-xs text-slate-600">{connected ? 'Atualizações ao vivo' : 'Atualização periódica'}</p>
          <label className="grid gap-1 text-sm">Fila<select className={fieldStyle} value={queue} onChange={event => {
            const next = queues.find(item => item.id === event.target.value);
            if (next) { setQueue(next.id); setOffset(0); setRows([]); setSelected(undefined); }
          }}>{queues.filter(item => item.id !== 'assigned' || operator.role === 'admin').map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
        </header>
        <VStack className="max-h-[26rem] overflow-y-auto md:max-h-[65vh]">
          {rows.length === 0 && <p className="p-4 text-sm text-slate-600">Nenhuma conversa nesta fila.</p>}
          {rows.map(row => <button key={row.id} aria-pressed={selected === row.id} onClick={() => setSelected(row.id)} className="grid w-full gap-1 border-b border-slate-100 px-4 py-3 text-left hover:bg-slate-50 aria-pressed:bg-teal-50">
            <p className="break-all font-medium">{row.customer_name || row.chat_id.split('@')[0]}</p>
            <time className="text-xs text-slate-600" dateTime={row.last_interaction}>{time.format(new Date(row.last_interaction))}</time>
          </button>)}
        </VStack>
        {(offset > 0 || rows.length === 50) && <footer className="flex flex-wrap gap-2 p-3">
          <Button label="Página anterior" isDisabled={offset === 0} onClick={() => setOffset(value => Math.max(0, value - 50))} />
          <Button label="Próxima página" isDisabled={rows.length < 50 || offset === 100_000} onClick={() => setOffset(value => value + 50)} />
        </footer>}
      </aside>
      {active ? <Thread key={active.id} conversation={active} operator={operator} revision={revision} onChange={refresh} onClaim={() => { setOffset(0); setQueue('mine'); refresh(); }} /> :
        <section className="grid min-h-80 place-items-center rounded-2xl border border-slate-200 bg-white p-6 text-center text-slate-600">Selecione uma conversa para ver o histórico.</section>}
    </section>}
  </main>;
}
