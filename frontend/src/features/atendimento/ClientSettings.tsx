'use client';

import { Button } from '@astryxdesign/core/Button';
import { useEffect, useState, type FormEvent } from 'react';
import { api, errorMessage } from './api';
import { RegistrationDialog, registrationField } from './RegistrationDialog';

type ClientDetails = { address: string; document: string; contact_phone: string; contact_email: string };
type Client = { id: string; name: string; archived_at: string | null; admin_invite_pending: boolean; details: ClientDetails };
type Invite = Client & { invite_error: string | null };

export function ClientSettings({ platformTenant }: { platformTenant: string }) {
  const [clients, setClients] = useState<Client[]>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const [editing, setEditing] = useState<Client | 'new'>();

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
      setStatus(message);
      setClients(await api<Client[]>('/clients'));
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }

  const client = editing === 'new' ? undefined : editing;

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void run(async () => {
      const company = {
        name: data.get('company'), details: {
          address: data.get('address'), document: data.get('document'),
          contact_phone: data.get('contactPhone'), contact_email: data.get('contactEmail'),
        },
      };
      if (client) {
        await api(`/clients/${client.id}`, { method: 'PUT', body: JSON.stringify(company) });
        setEditing(undefined);
        return 'Cliente atualizado.';
      }
      const result = await api<Invite>('/clients', { method: 'POST', body: JSON.stringify({
        ...company, admin: { name: data.get('adminName'), email: data.get('adminEmail') },
      }) });
      setEditing(undefined);
      return result.invite_error ? `Cliente cadastrado. ${result.invite_error}` : 'Cliente cadastrado e convite enviado.';
    });
  }

  return <section className="mx-auto grid max-w-screen-lg gap-4 p-4" aria-labelledby="clients-title">
    <header className="flex flex-wrap items-center justify-between gap-3">
      <h2 id="clients-title" className="text-2xl font-semibold">Clientes</h2>
      <Button label="Novo cliente" variant="primary" isDisabled={busy} onClick={() => { setError(''); setEditing('new'); }} />
    </header>
    {error && !editing && <p role="alert" className="text-red-800">{error}</p>}
    {status && <p role="status">{status}</p>}
    {clients?.length === 0 && <p className="text-sm text-slate-600">Nenhum cliente cadastrado.</p>}
    <ul className="grid gap-3">
      {clients?.map(client => <li key={client.id} className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-5">
        <p className="break-all font-medium">{client.name}{client.archived_at ? ' · Arquivado' : ''}</p>
        {!client.archived_at && <>
          {client.details.contact_email && <p className="break-all text-sm text-slate-600">{client.details.contact_email} · {client.details.contact_phone}</p>}
          <section className="flex flex-wrap gap-3" aria-label={`Ações para ${client.name}`}>
            <Button label="Editar" isDisabled={busy} onClick={() => { setError(''); setEditing(client); }} />
            {client.admin_invite_pending && <Button label="Reenviar convite do administrador" isDisabled={busy} onClick={() => void run(async () => {
              const result = await api<Invite>(`/clients/${client.id}/invite`, { method: 'POST' });
              return result.invite_error ?? 'Convite enviado.';
            })} />}
            {client.id !== platformTenant && <Button label="Excluir" isDisabled={busy} onClick={() => {
              if (window.confirm(`Excluir ${client.name}? O acesso será bloqueado e o histórico ficará preservado.`)) void run(async () => {
                await api(`/clients/${client.id}`, { method: 'DELETE' });
                return 'Cliente arquivado.';
              });
            }} />}
          </section>
        </>}
      </li>)}
    </ul>
    {editing && <RegistrationDialog title={client ? 'Editar cliente' : 'Novo cliente'}
      submitLabel={client ? 'Salvar cliente' : 'Cadastrar e convidar'} error={error} busy={busy} onClose={() => setEditing(undefined)} onSubmit={save}>
      <label className="grid gap-1 text-sm">Nome do cliente<input name="company" defaultValue={client?.name} required maxLength={100} className={registrationField} /></label>
      <label className="grid gap-1 text-sm">CPF ou CNPJ<input name="document" defaultValue={client?.details.document} required maxLength={24} className={registrationField} /></label>
      <label className="grid gap-1 text-sm">Endereço completo<textarea name="address" autoComplete="street-address" defaultValue={client?.details.address} required maxLength={400} rows={2} className={registrationField} /></label>
      <label className="grid gap-1 text-sm">Telefone de contato<input name="contactPhone" type="tel" defaultValue={client?.details.contact_phone} required maxLength={32} className={registrationField} /></label>
      <label className="grid gap-1 text-sm">E-mail de contato<input name="contactEmail" type="email" defaultValue={client?.details.contact_email} required maxLength={150} className={registrationField} /></label>
      {!client && <fieldset className="grid gap-2 border-t border-slate-200 pt-2">
        <legend className="text-sm font-medium">Administrador inicial</legend>
        <label className="grid gap-1 text-sm">Nome do administrador<input name="adminName" required maxLength={100} className={registrationField} /></label>
        <label className="grid gap-1 text-sm">E-mail do administrador<input name="adminEmail" type="email" required maxLength={150} className={registrationField} /></label>
      </fieldset>}
    </RegistrationDialog>}
  </section>;
}
