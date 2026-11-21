'use client';

import { Button } from '@astryxdesign/core/Button';
import { useEffect, useState, type FormEvent } from 'react';
import { api, departmentLabels, errorMessage, type OperatorFunction } from './api';
import { RegistrationDialog, registrationField } from './RegistrationDialog';

const endpoint = '/operators/functions';

export function FunctionSettings() {
  const [items, setItems] = useState<OperatorFunction[]>();
  const [editing, setEditing] = useState<OperatorFunction | 'new'>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const current = editing === 'new' ? undefined : editing;

  useEffect(() => {
    const controller = new AbortController();
    api<OperatorFunction[]>(endpoint, { signal: controller.signal }).then(setItems).catch(failure => {
      if (!controller.signal.aborted) setError(errorMessage(failure));
    });
    return () => controller.abort();
  }, []);

  async function run(action: () => Promise<string>) {
    if (busy) return;
    setBusy(true); setError(''); setStatus('');
    try { setStatus(await action()); }
    catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(false); }
  }

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    void run(async () => {
      const saved = await api<OperatorFunction>(current ? `${endpoint}/${current.id}` : endpoint, {
        method: current ? 'PUT' : 'POST', body: JSON.stringify(data),
      });
      setItems(previous => [...(previous ?? []).filter(item => item.id !== saved.id), saved]
        .sort((a, b) => a.name.localeCompare(b.name, 'pt-BR')));
      setEditing(undefined);
      return 'Função salva.';
    });
  }

  return <section className="mx-auto grid max-w-screen-xl gap-4 p-4" aria-labelledby="functions-title">
    <header className="flex flex-wrap items-center justify-between gap-3">
      <h2 id="functions-title" className="text-2xl font-semibold">Funções</h2>
      <Button label="Nova função" variant="primary" isDisabled={busy || !items} onClick={() => { setError(''); setEditing('new'); }} />
    </header>
    {status && <p role="status">{status}</p>}
    {error && !editing && <p role="alert" className="text-red-800">{error}</p>}
    {items?.length === 0 && <p className="text-sm text-slate-600">Nenhuma função cadastrada.</p>}
    <ul className="grid gap-3">{items?.map(item => <li key={item.id} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-5">
      <section className="min-w-0"><h3 className="wrap-anywhere font-medium">{item.name}</h3><p className="text-sm text-slate-600">{departmentLabels[item.department]}</p></section>
      <section className="flex flex-wrap gap-2" aria-label={`Ações para ${item.name}`}>
        <Button label="Editar" isDisabled={busy} onClick={() => { setError(''); setEditing(item); }} />
        <Button label="Excluir" isDisabled={busy} onClick={() => {
          if (window.confirm(`Excluir a função ${item.name}?`)) void run(async () => {
            await api(`${endpoint}/${item.id}`, { method: 'DELETE' });
            setItems(previous => previous?.filter(record => record.id !== item.id));
            return 'Função excluída.';
          });
        }} />
      </section>
    </li>)}</ul>
    {editing && <RegistrationDialog title={current ? 'Editar função' : 'Nova função'} submitLabel="Salvar função"
      error={error} busy={busy} onClose={() => setEditing(undefined)} onSubmit={save}>
      <label className="grid gap-1 text-sm">Nome<input name="name" required maxLength={80} defaultValue={current?.name} className={registrationField} /></label>
      <label className="grid gap-1 text-sm">Setor de atendimento<select name="department" required defaultValue={current?.department ?? ''} className={registrationField}>
        <option value="" disabled>Selecione</option>
        {Object.entries(departmentLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
    </RegistrationDialog>}
  </section>;
}
