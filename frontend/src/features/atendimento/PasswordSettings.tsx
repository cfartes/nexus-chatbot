'use client';

import { Button } from '@astryxdesign/core/Button';
import { TextInput } from '@astryxdesign/core/TextInput';
import { useState, type FormEvent } from 'react';
import { api, errorMessage } from './api';

export function PasswordSettings() {
  const [current, setCurrent] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setError(''); setSaved(false);
    if (password !== confirmation) {
      setError('A confirmação precisa ser igual à nova senha.');
      return;
    }
    setBusy(true);
    try {
      await api('/auth/password', {
        method: 'PUT', body: JSON.stringify({ current_password: current, new_password: password }),
      });
      setCurrent(''); setPassword(''); setConfirmation(''); setSaved(true);
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }

  return <section className="mx-auto max-w-md p-4" aria-labelledby="password-title">
    <form onSubmit={submit} className="grid gap-4 rounded-2xl border border-slate-200 bg-white p-6">
      <h2 id="password-title" className="text-xl font-semibold">Alterar senha</h2>
      <TextInput label="Senha atual" type="password" autoComplete="current-password" value={current} onChange={setCurrent} isRequired isDisabled={busy} />
      <TextInput label="Nova senha" type="password" autoComplete="new-password" description="Use de 12 a 128 caracteres." value={password} onChange={setPassword} isRequired isDisabled={busy} />
      <TextInput label="Confirme a nova senha" type="password" autoComplete="new-password" value={confirmation} onChange={setConfirmation} isRequired isDisabled={busy} />
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      {saved && <p role="status" className="text-sm text-teal-900">Senha alterada. As outras sessões da sua conta foram encerradas.</p>}
      <Button type="submit" label="Salvar nova senha" variant="primary" isLoading={busy}
        isDisabled={!current || current.length > 128 || password.length < 12 || password.length > 128 || !confirmation} />
    </form>
  </section>;
}
