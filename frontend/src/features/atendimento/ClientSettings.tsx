'use client';

import { Button } from '@astryxdesign/core/Button';
import { useEffect, useState, type FormEvent } from 'react';
import { api, errorMessage } from './api';

type Client = { id: string; name: string; archived_at: string | null; admin_invite_pending: boolean };
type Invite = Client & { invite_error: string | null };
const field = 'rounded-lg border border-slate-300 px-3 py-2';

export function ClientSettings({ platformTenant }: { platformTenant: string }) {
  const [clients, setClients] = useState<Client[]>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    api<Client[]>('/clients', { signal: controller.signal }).then(setClients).catch(failure => {
      if (!controller.signal.aborted) setError(errorMessage(failure));
    });
    return () => controller.abort();
  }, []);

  async function run(action: () => Promise<string>) {
    if (busy) return;
    setBusy(true); setError(''); setStatus('');
    try {
      const message = await action();
      setClients(await api<Client[]>('/clients'));
      setStatus(message);
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }

  function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    void run(async () => {
      const result = await api<Invite>('/clients', { method: 'POST', body: JSON.stringify({
        name: data.get('company'), admin: { name: data.get('adminName'), email: data.get('adminEmail') },
      }) });
      form.reset();
      return result.invite_error ? `Cliente cadastrado. ${result.invite_error}` : 'Cliente cadastrado e convite enviado.';
    });
  }

  return <section className="mx-auto grid max-w-screen-lg gap-4 p-4" aria-labelledby="clients-title">
    <h2 id="clients-title" className="text-2xl font-semibold">Clientes</h2>
    {error && <p role="alert" className="text-red-800">{error}</p>}
    {status && <p role="status">{status}</p>}
    <form onSubmit={add} className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-5 sm:grid-cols-3">
      <label className="grid gap-1 text-sm">Empresa<input name="company" required maxLength={100} className={field} /></label>
      <label className="grid gap-1 text-sm">Nome do administrador<input name="adminName" required maxLength={100} className={field} /></label>
      <label className="grid gap-1 text-sm">E-mail do administrador<input name="adminEmail" type="email" required maxLength={150} className={field} /></label>
      <Button type="submit" label="Cadastrar e convidar" variant="primary" isDisabled={busy} />
    </form>
    <ul className="grid gap-3">
      {clients?.map(client => <li key={client.id} className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-5">
        {client.archived_at ? <p>{client.name} · Arquivado</p> : <>
          <form key={client.name} className="flex flex-wrap items-end gap-3" onSubmit={event => {
            event.preventDefault();
            const name = new FormData(event.currentTarget).get('name');
            void run(async () => {
              await api(`/clients/${client.id}`, { method: 'PUT', body: JSON.stringify({ name }) });
              return 'Cliente atualizado.';
            });
          }}>
            <label className="grid gap-1 text-sm">Empresa<input name="name" required maxLength={100} defaultValue={client.name} className={field} /></label>
            <Button type="submit" label="Salvar nome" isDisabled={busy} />
          </form>
          <section className="flex flex-wrap gap-3" aria-label={`Ações para ${client.name}`}>
            {client.admin_invite_pending && <Button label="Reenviar convite do administrador" isDisabled={busy} onClick={() => void run(async () => {
              const result = await api<Invite>(`/clients/${client.id}/invite`, { method: 'POST' });
              return result.invite_error ?? 'Convite enviado.';
            })} />}
            {client.id !== platformTenant && <Button label="Arquivar cliente" isDisabled={busy} onClick={() => {
              if (window.confirm(`Arquivar ${client.name}? O acesso será bloqueado e o histórico ficará preservado.`)) void run(async () => {
                await api(`/clients/${client.id}`, { method: 'DELETE' });
                return 'Cliente arquivado.';
              });
            }} />}
          </section>
        </>}
      </li>)}
    </ul>
  </section>;
}
