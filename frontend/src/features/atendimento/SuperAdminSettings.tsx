'use client';

import { Button } from '@astryxdesign/core/Button';
import { TextInput } from '@astryxdesign/core/TextInput';
import { useEffect, useState, type FormEvent } from 'react';
import { api, errorMessage } from './api';

type SuperAdmin = {
  id: string;
  name: string;
  email: string;
  invite_pending: boolean;
  invite_sent: boolean | null;
  invite_error: string | null;
};

const endpoint = '/operators/superadmins';

export function SuperAdminSettings() {
  const [admins, setAdmins] = useState<SuperAdmin[]>();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    api<SuperAdmin[]>(endpoint, { signal: controller.signal }).then(setAdmins).catch(failure => {
      if (!controller.signal.aborted) setError(errorMessage(failure));
    });
    return () => controller.abort();
  }, []);

  async function invite(event?: FormEvent<HTMLFormElement>, id?: string) {
    event?.preventDefault();
    if (busy || !admins) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const member = await api<SuperAdmin>(id ? `${endpoint}/${id}/invite` : endpoint, {
        method: 'POST', ...(id ? {} : { body: JSON.stringify({ name: name.trim(), email: email.trim() }) }),
      });
      setAdmins(id ? admins.map(admin => admin.id === id ? member : admin) : [...admins, member]);
      if (!id) { setName(''); setEmail(''); }
      if (member.invite_sent) setNotice('Convite enviado por e-mail.');
      else setError(member.invite_error || 'O convite ficou pendente. Você pode reenviá-lo na lista.');
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }

  return <section className="mx-auto grid max-w-3xl gap-5 p-4" aria-labelledby="superadmins-title">
    <h2 id="superadmins-title" className="text-xl font-semibold">SuperAdmins</h2>
    <form onSubmit={event => void invite(event)} className="grid gap-4 rounded-2xl border border-slate-200 bg-white p-5">
      <h3 className="font-semibold">Cadastrar SuperAdmin</h3>
      <TextInput label="Nome" value={name} onChange={setName} isRequired isDisabled={busy} />
      <TextInput label="E-mail" type="email" value={email} onChange={setEmail} isRequired isDisabled={busy} />
      <Button type="submit" label="Enviar convite" variant="primary" isLoading={busy} isDisabled={!admins || !name.trim() || !email.trim()} />
    </form>
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    {notice && <p role="status" className="text-sm text-teal-900">{notice}</p>}
    {admins && <ul className="divide-y divide-slate-200 rounded-2xl border border-slate-200 bg-white">
      {admins.map(admin => <li key={admin.id} className="flex flex-wrap items-center justify-between gap-3 p-4">
        <section className="min-w-0 break-words">
          <p className="font-medium">{admin.name}</p>
          <p className="text-sm text-slate-600">{admin.email}</p>
          {admin.invite_pending && <p className="text-sm text-slate-600">Convite pendente</p>}
        </section>
        {admin.invite_pending && <Button label="Reenviar convite" isDisabled={busy} onClick={() => void invite(undefined, admin.id)} />}
      </li>)}
    </ul>}
  </section>;
}
