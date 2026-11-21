'use client';

import { Button } from '@astryxdesign/core/Button';
import { useEffect, useState, type FormEvent } from 'react';
import { api, errorMessage, departmentLabels, type Department, type OperatorFunction } from './api';
import { RegistrationDialog, registrationField } from './RegistrationDialog';

type Member = { id: string; name: string; email: string; department: Department; is_active: boolean;
  function_id: string | null; invite_pending: boolean; invite_sent: boolean | null; invite_error: string | null };

export function OperatorSettings() {
  const [members, setMembers] = useState<Member[]>();
  const [functions, setFunctions] = useState<OperatorFunction[]>();
  const [editing, setEditing] = useState<Member | 'new'>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([api<Member[]>('/operators', { signal: controller.signal }),
      api<OperatorFunction[]>('/operators/functions', { signal: controller.signal })]).then(([people, profiles]) => {
      setMembers(people); setFunctions(profiles);
    }).catch(failure => {
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

  const member = editing === 'new' ? undefined : editing;
  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    void run(async () => {
      const result = await api<Member>(member ? `/operators/${member.id}` : '/operators', {
        method: member ? 'PUT' : 'POST', body: JSON.stringify(member ? { ...data, is_active: data.active === 'on', active: undefined } : data),
      });
      setMembers(current => [...(current ?? []).filter(item => item.id !== result.id), result]
        .sort((first, second) => first.name.localeCompare(second.name, 'pt-BR')));
      setEditing(undefined);
      return member ? 'Atendente atualizado.' : result.invite_sent ? 'Convite enviado.'
        : `Atendente cadastrado. ${result.invite_error ?? 'O convite não pôde ser enviado.'}`;
    });
  }

  return <section className="mx-auto grid max-w-screen-xl gap-4 p-4" aria-labelledby="operators-title">
    <header className="flex flex-wrap items-center justify-between gap-3">
      <h2 id="operators-title" className="text-2xl font-semibold">Colaboradores</h2>
      <Button label="Novo colaborador" variant="primary" isDisabled={busy || !members || !functions?.length} onClick={() => { setError(''); setEditing('new'); }} />
    </header>
    {functions?.length === 0 && <p className="text-sm text-slate-600">Cadastre uma função para incluir colaboradores.</p>}
    {status && <p role="status" className="text-sm">{status}</p>}
    {error && !editing && <p role="alert" className="text-sm text-red-800">{error}</p>}
    {members?.length === 0 && <p className="text-sm text-slate-600">Nenhum atendente cadastrado.</p>}
    <ul className="grid gap-3">{members?.map(item => <li key={item.id} className="grid gap-2 rounded-2xl border border-slate-200 bg-white p-5">
      <p className="break-all text-sm"><strong>{item.name}</strong><br />{item.email}<br />
        {functions?.find(profile => profile.id === item.function_id)?.name ?? departmentLabels[item.department]} · {item.invite_pending ? 'Convite pendente' : item.is_active ? 'Ativo' : 'Desativado'}</p>
      <section className="flex flex-wrap gap-2" aria-label={`Ações para ${item.name}`}>
        <Button label="Editar" isDisabled={busy} onClick={() => { setError(''); setEditing(item); }} />
        {item.invite_pending && <Button label="Reenviar convite" isDisabled={busy} onClick={() => void run(async () => {
          const result = await api<Member>(`/operators/${item.id}/invite`, { method: 'POST' });
          return result.invite_sent ? 'Convite enviado.' : result.invite_error ?? 'O convite não pôde ser enviado.';
        })} />}
        <Button label="Excluir" isDisabled={busy} onClick={() => {
          if (window.confirm(`Excluir ${item.name}? O acesso será encerrado e as conversas voltarão à fila.`)) void run(async () => {
            await api(`/operators/${item.id}`, { method: 'DELETE' });
            setMembers(current => current?.filter(record => record.id !== item.id));
            return 'Atendente excluído.';
          });
        }} />
      </section>
    </li>)}</ul>
    {editing && <RegistrationDialog title={member ? 'Editar colaborador' : 'Novo colaborador'}
      submitLabel={member ? 'Salvar atendente' : 'Enviar convite'} error={error} busy={busy} onClose={() => setEditing(undefined)} onSubmit={save}>
      <label className="grid gap-1 text-sm">Nome<input name="name" required maxLength={100} defaultValue={member?.name} className={registrationField} /></label>
      <label className="grid gap-1 text-sm">E-mail<input name="email" required type="email" maxLength={150} defaultValue={member?.email} className={registrationField} /></label>
      <label className="grid gap-1 text-sm">Perfil<select name="function_id" required defaultValue={member?.function_id ?? ''} className={registrationField}>
        <option value="" disabled>Selecione a função</option>
        {functions?.map(item => <option key={item.id} value={item.id}>{item.name} · {departmentLabels[item.department]}</option>)}
      </select></label>
      {member && !member.invite_pending && <label className="flex items-center gap-2 text-sm"><input name="active" type="checkbox" defaultChecked={member.is_active} /> Atendente ativo</label>}
    </RegistrationDialog>}
  </section>;
}
