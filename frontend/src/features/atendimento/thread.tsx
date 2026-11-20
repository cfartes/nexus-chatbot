'use client';

import { Button } from '@astryxdesign/core/Button';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { api, errorMessage, type Conversation, type Message, type Operator } from './api';

const delivery: Record<string, string> = { pending: 'Na fila', processing: 'Enviando', sent: 'Aceita pelo WhatsApp', failed: 'Falha no envio', uncertain: 'Envio incerto', cancelled: 'Cancelada' };
const authors = { customer: 'Cliente', operator: 'Atendente', bot: 'IA' };

export function Thread({ conversation, operator, revision, onChange, onClaim }: {
  conversation: Conversation; operator: Operator; revision: number; onChange: () => void; onClaim: () => void;
}) {
  const [latest, setLatest] = useState<Message[]>([]);
  const [older, setOlder] = useState<Message[]>([]);
  const [end, setEnd] = useState(false);
  const [draft, setDraft] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [operators, setOperators] = useState<Operator[]>([]);
  const transition = useRef(false);
  const pending = useRef<{ id: string; text: string } | null>(null);
  const scroller = useRef<HTMLElement>(null);
  const followLatest = useRef(true);
  const base = `/conversations/${conversation.id}`;
  const owner = conversation.assigned_user_id === operator.id;
  const admin = operator.role === 'admin';
  const destinations = operators.filter(person => person.id !== conversation.assigned_user_id);

  useEffect(() => {
    const panel = scroller.current;
    if (panel && followLatest.current) panel.scrollTop = panel.scrollHeight;
  }, [latest]);

  useEffect(() => {
    const controller = new AbortController();
    api<Message[]>(`${base}/messages`, { signal: controller.signal }).then(setLatest).catch(failure => {
      if (!controller.signal.aborted) { setLatest([]); setOlder([]); setError(errorMessage(failure)); }
    });
    return () => controller.abort();
  }, [base, revision]);

  useEffect(() => {
    if (!admin || conversation.state !== 'assigned') return;
    const controller = new AbortController();
    api<Operator[]>('/conversations/operators', { signal: controller.signal }).then(setOperators).catch(failure => {
      if (!controller.signal.aborted) setError(errorMessage(failure));
    });
    return () => controller.abort();
  }, [admin, conversation.state]);

  async function run(action: () => Promise<void>) {
    if (transition.current) return;
    transition.current = true; setBusy(true); setError('');
    try { await action(); }
    catch (failure) { setError(errorMessage(failure)); }
    finally { transition.current = false; setBusy(false); }
  }

  function mutate(path: string, method = 'POST', body?: object) {
    return api(`${base}${path}`, { method, body: body ? JSON.stringify(body) : undefined });
  }

  function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = draft.trim();
    if (!content) return;
    void run(async () => {
      if (pending.current?.text !== content) pending.current = { id: crypto.randomUUID(), text: content };
      await mutate('/messages', 'POST', { request_id: pending.current.id, text: content });
      pending.current = null; setDraft(''); onChange();
    });
  }

  const history = [...new Map([...latest, ...older.filter(previous => !latest.some(message => message.id === previous.id))].map(message => [message.id, message])).values()];
  async function loadOlder() {
    const cursor = history.at(-1);
    if (!cursor) return;
    await run(async () => {
      const page = await api<Message[]>(`${base}/messages?before=${encodeURIComponent(cursor.id)}`);
      setOlder(previous => [...previous, ...page]); setEnd(page.length < 50);
    });
  }

  return <section aria-label="Conversa selecionada" className="grid min-w-0 grid-rows-[auto_1fr_auto] overflow-hidden rounded-2xl border border-slate-200 bg-white">
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 p-4">
      <section><h2 className="break-all text-lg font-semibold">{conversation.customer_name || conversation.chat_id.split('@')[0]}</h2>
        <p className="text-sm text-slate-600">{{ waiting: 'Na fila humana', bot: 'Atendimento com IA', assigned: owner ? 'Atribuída a você' : 'Atribuída a outro atendente' }[conversation.state]}</p>
        {conversation.origin_name && <p className="text-sm text-slate-600">Origem · {conversation.origin_name}</p>}</section>
      <section className="flex flex-wrap items-center gap-2" aria-label="Ações da conversa">
        {conversation.state === 'waiting' && <Button label="Assumir" variant="primary" isDisabled={busy} onClick={() => void run(async () => { await mutate('/claim'); onClaim(); })} />}
        {(admin || owner) &&
          <Button label={conversation.state === 'bot' ? 'Pausar IA' : 'Devolver à IA'} isDisabled={busy} onClick={() => void run(async () => { await mutate('/bot', 'PUT', { active: conversation.state !== 'bot' }); onChange(); })} />}
        {(admin || owner) && <Button label="Encerrar atendimento" isDisabled={busy} onClick={() => void run(async () => { await mutate('/close'); onChange(); })} />}
        {admin && conversation.state === 'assigned' && destinations.length > 0 && <form className="flex items-center gap-2" onSubmit={event => {
          event.preventDefault(); const user = new FormData(event.currentTarget).get('user');
          if (typeof user === 'string' && user) void run(async () => { await mutate('/transfer', 'POST', { user_id: user }); onChange(); });
        }}><select aria-label="Atendente de destino" name="user" required className="rounded border border-slate-300 p-2"><option value="">Atendente</option>
          {destinations.map(person => <option key={person.id} value={person.id}>{person.name}</option>)}</select>
          <Button type="submit" label="Transferir" isDisabled={busy} />
        </form>}
      </section>
    </header>
    <section ref={scroller} onScroll={event => { const panel = event.currentTarget; followLatest.current = panel.scrollHeight - panel.scrollTop - panel.clientHeight < 60; }} className="min-h-72 overflow-y-auto bg-slate-50 p-4 md:max-h-[72vh]" aria-label="Histórico de mensagens">
      {latest.length === 50 && !end && <Button label="Mensagens anteriores" isDisabled={busy} onClick={() => void loadOlder()} />}
      {history.length === 0 && <p className="text-sm text-slate-600">Nenhuma mensagem neste atendimento.</p>}
      <ol className="mt-3 flex flex-col gap-3">{[...history].reverse().map(message => <li key={message.id} className={`max-w-[85%] rounded-xl border p-3 ${message.sender_type === 'customer' ? 'self-start border-slate-200 bg-white' : 'self-end border-teal-100 bg-teal-50'}`}>
        <p className="text-xs font-semibold text-slate-700">{authors[message.sender_type]}</p>
        <p className="my-1 whitespace-pre-wrap wrap-anywhere text-sm">{message.content}</p>
        <p className="text-xs text-slate-600"><time dateTime={message.created_at}>{new Date(message.created_at).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}</time>{message.delivery_status && ` · ${delivery[message.delivery_status] ?? message.delivery_status}`}</p>
      </li>)}</ol>
    </section>
    <footer className="border-t border-slate-200 p-4">
      {error && <p role="alert" className="mb-3 text-sm text-red-700">{error}</p>}
      {owner && <form onSubmit={send} className="grid items-end gap-3 sm:grid-cols-[1fr_auto]">
        <label className="grid gap-1 text-sm font-medium">Resposta<textarea value={draft} onChange={event => setDraft(event.target.value)} rows={2} maxLength={4096} disabled={busy} className="w-full resize-y rounded-lg border border-slate-300 p-2" /></label>
        <Button label="Enviar" type="submit" variant="primary" isDisabled={busy || !draft.trim()} />
      </form>}
    </footer>
  </section>;
}
