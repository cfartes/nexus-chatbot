'use client';

import { Button } from '@astryxdesign/core/Button';
import Link from 'next/link';
import { useEffect, useState, type FormEvent } from 'react';
import { api, errorMessage } from './api';

const field = 'w-full rounded-lg border border-slate-300 px-3 py-2';

export function Invitation() {
  const [token, setToken] = useState<string>();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [accepted, setAccepted] = useState(false);
  const [company, setCompany] = useState('');

  useEffect(() => { setToken(window.location.hash.slice(1)); }, []);

  async function accept(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const password = data.get('password');
    if (password !== data.get('confirmation')) { setError('As senhas precisam ser iguais.'); return; }
    setBusy(true); setError('');
    try {
      await api('/operators/accept-invite', { method: 'POST', body: JSON.stringify({ password, token }) });
      setCompany(token?.slice(0, 36) ?? '');
      window.history.replaceState(null, '', '/convite');
      setAccepted(true); setToken('');
    } catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(false); }
  }

  return <main className="grid min-h-dvh place-items-center bg-slate-100 p-6 text-slate-900">
    <section className="grid w-full max-w-md gap-5 rounded-2xl border border-slate-200 bg-white p-8">
      <h1 className="text-2xl font-semibold">Definir senha do Nexus Atende</h1>
      {accepted ? <p role="status">Sua senha foi criada. <Link href={`/?empresa=${encodeURIComponent(company)}`} className="underline">Entrar no painel</Link></p> :
        token === undefined ? <p>Carregando convite…</p> : token.length !== 80 ? <p role="alert">Convite inválido. Solicite outro ao administrador.</p> :
          <form className="grid gap-4" onSubmit={accept}>
            <label className="grid gap-1 text-sm">Nova senha (mínimo de 12 caracteres)<input required type="password" name="password" autoComplete="new-password" minLength={12} maxLength={128} className={field} /></label>
            <label className="grid gap-1 text-sm">Confirmar senha<input required type="password" name="confirmation" autoComplete="new-password" minLength={12} maxLength={128} className={field} /></label>
            {error && <p role="alert" className="text-sm text-red-800">{error}</p>}
            <Button type="submit" label="Definir senha" variant="primary" isLoading={busy} />
          </form>}
    </section>
  </main>;
}
