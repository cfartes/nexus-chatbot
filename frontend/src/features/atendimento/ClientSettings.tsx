'use client';

import { Button } from '@astryxdesign/core/Button';
import { useEffect, useState, type FormEvent } from 'react';
import { api, errorMessage } from './api';
import { RegistrationDialog, registrationField } from './RegistrationDialog';

type PostalAddress = { postal_code: string; street: string; neighborhood: string; city: string; state: string };
type ClientDetails = PostalAddress & { address: string; number: string; document: string; contact_phone: string; contact_email: string };
type Client = { id: string; name: string; archived_at: string | null; admin_invite_pending: boolean; details: ClientDetails };
type Invite = Client & { invite_error: string | null };
const states = 'AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split(' ');

function formatDocument(value: string): string {
  const text = value.replace(/[^0-9a-z]/gi, '').toUpperCase().slice(0, 14);
  if (text.length <= 11 && !/[A-Z]/.test(text)) {
    return text.replace(/^(\d{3})(?=\d)/, '$1.')
      .replace(/^(\d{3}\.\d{3})(?=\d)/, '$1.').replace(/^(\d{3}\.\d{3}\.\d{3})(?=\d)/, '$1-');
  }
  return text.replace(/^(.{2})(?=.)/, '$1.')
    .replace(/^(.{6})(?=.)/, '$1.').replace(/^(.{10})(?=.)/, '$1/').replace(/^(.{15})(?=.)/, '$1-');
}

function TaxDocument({ initial }: { initial?: string }) {
  const [value, setValue] = useState(() => formatDocument(initial ?? ''));
  return <label className="grid gap-1 text-sm">CPF ou CNPJ<input name="document" value={value} required maxLength={18}
    onChange={event => setValue(formatDocument(event.target.value))} className={registrationField} /></label>;
}

function AddressFields({ details, onLookup }: { details?: ClientDetails; onLookup: (loading: boolean) => void }) {
  const [address, setAddress] = useState<PostalAddress>(() => ({
    postal_code: details?.postal_code ?? '', street: details?.street ?? '', neighborhood: details?.neighborhood ?? '',
    city: details?.city ?? '', state: details?.state ?? '',
  }));
  const [looking, setLooking] = useState(false);
  const [postalEdited, setPostalEdited] = useState(false);
  const [message, setMessage] = useState('');
  const digits = address.postal_code.replace(/\D/g, '');

  function edit(field: keyof PostalAddress, value: string) {
    setAddress(current => ({ ...current, [field]: value }));
  }

  useEffect(() => {
    if (!postalEdited || digits.length !== 8) {
      setLooking(false);
      return;
    }
    const controller = new AbortController();
    setLooking(true); onLookup(true); setMessage('');
    const timer = window.setTimeout(() => {
      void api<PostalAddress>(`/clients/cep/${digits}`, { signal: controller.signal }).then(found => {
        if (controller.signal.aborted) return;
        setAddress(current => ({ ...current, street: found.street, neighborhood: found.neighborhood, city: found.city, state: found.state }));
        setMessage(found.street && found.neighborhood ? 'Endereço encontrado. Confira os dados e informe o número.'
          : 'O CEP retornou parte do endereço. Complete os dados manualmente.');
      }).catch(failure => {
        if (!controller.signal.aborted) setMessage(errorMessage(failure));
      }).finally(() => {
        if (!controller.signal.aborted) { setLooking(false); onLookup(false); }
      });
    }, 250);
    return () => { window.clearTimeout(timer); controller.abort(); onLookup(false); };
  }, [digits, onLookup, postalEdited]);

  return <fieldset className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3">
    <legend className="text-sm font-medium">Endereço</legend>
    {details?.address && <p className="break-words text-sm text-slate-600 col-span-full">Endereço anterior · {details.address}</p>}
    <label className="grid gap-1 text-sm">CEP<input name="postalCode" autoComplete="postal-code" inputMode="numeric" required
      pattern="[0-9]{5}-?[0-9]{3}" maxLength={9} value={address.postal_code}
      onChange={event => { edit('postal_code', event.target.value.replace(/\D/g, '').slice(0, 8)); setPostalEdited(true); setMessage(''); }} className={registrationField} /></label>
    <label className="grid gap-1 text-sm md:col-span-2">Rua<input name="street" autoComplete="address-line1" required maxLength={180} disabled={looking}
      value={address.street} onChange={event => edit('street', event.target.value)} className={registrationField} /></label>
    <label className="grid gap-1 text-sm">Número<input name="number" required maxLength={24}
      defaultValue={details?.number} className={registrationField} /></label>
    <label className="grid gap-1 text-sm">Bairro<input name="neighborhood" required maxLength={120} disabled={looking}
      value={address.neighborhood} onChange={event => edit('neighborhood', event.target.value)} className={registrationField} /></label>
    <label className="grid gap-1 text-sm">Cidade<input name="city" autoComplete="address-level2" required maxLength={120} disabled={looking}
      value={address.city} onChange={event => edit('city', event.target.value)} className={registrationField} /></label>
    <label className="grid gap-1 text-sm">UF<select name="state" autoComplete="address-level1" required disabled={looking}
      value={address.state} onChange={event => edit('state', event.target.value)} className={registrationField}>
      <option value="">Selecione</option>{states.map(state => <option key={state} value={state}>{state}</option>)}
    </select></label>
    {(looking || message) && <p role="status" className="col-span-full text-sm text-slate-700">{looking ? 'Consultando CEP…' : message}</p>}
  </fieldset>;
}

export function ClientSettings({ platformTenant }: { platformTenant: string }) {
  const [clients, setClients] = useState<Client[]>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const [editing, setEditing] = useState<Client | 'new'>();
  const [lookingUpAddress, setLookingUpAddress] = useState(false);

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
    if (lookingUpAddress) return;
    const data = new FormData(event.currentTarget);
    void run(async () => {
      const company = {
        name: data.get('company'), details: {
          postal_code: data.get('postalCode'), street: data.get('street'), number: data.get('number'),
          neighborhood: data.get('neighborhood'), city: data.get('city'), state: data.get('state'),
          document: data.get('document'),
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

  return <section className="mx-auto grid max-w-screen-xl gap-4 p-4" aria-labelledby="clients-title">
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
      submitLabel={client ? 'Salvar cliente' : 'Cadastrar e convidar'} error={error} busy={busy} width="56rem"
      submitDisabled={lookingUpAddress} onClose={() => setEditing(undefined)} onSubmit={save}>
      <section className="grid gap-3 sm:grid-cols-2">
        <label className="grid gap-1 text-sm">Nome do cliente<input name="company" defaultValue={client?.name} required maxLength={100} className={registrationField} /></label>
        <TaxDocument initial={client?.details.document} />
      </section>
      <AddressFields details={client?.details} onLookup={setLookingUpAddress} />
      <section className="grid gap-3 sm:grid-cols-2">
        <label className="grid gap-1 text-sm">Telefone de contato<input name="contactPhone" type="tel" defaultValue={client?.details.contact_phone} required maxLength={32} className={registrationField} /></label>
        <label className="grid gap-1 text-sm">E-mail de contato<input name="contactEmail" type="email" defaultValue={client?.details.contact_email} required maxLength={150} className={registrationField} /></label>
      </section>
      {!client && <fieldset className="grid gap-2 border-t border-slate-200 pt-2 sm:grid-cols-2">
        <legend className="text-sm font-medium">Administrador inicial</legend>
        <label className="grid gap-1 text-sm">Nome do administrador<input name="adminName" required maxLength={100} className={registrationField} /></label>
        <label className="grid gap-1 text-sm">E-mail do administrador<input name="adminEmail" type="email" required maxLength={150} className={registrationField} /></label>
      </fieldset>}
    </RegistrationDialog>}
  </section>;
}
