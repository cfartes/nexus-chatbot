'use client';

import { Button } from '@astryxdesign/core/Button';
import { TextArea } from '@astryxdesign/core/TextArea';
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { api, ApiError, errorMessage } from './api';
import { Integrations } from './integrations';
import { SettingsCard, settingsGrid } from './settings-card';

type Member = { id: string; name: string; email: string; is_active: boolean; invite_pending: boolean; invite_sent: boolean | null };
type Source = { source: string; chunks: number };
type Connection = { status: string; phone_number: string | null; session_id: string | null };
type Preview = { status: 'answered' | 'handoff' | 'unavailable'; message: string; sources: string[] };
const previewLabel = { answered: 'Resposta automática', handoff: 'Encaminharia para um atendente', unavailable: 'IA indisponível' };
const connectionLabels: Record<string, string> = {
  READY: 'Conectado', CONNECTED: 'Conectado', QR_READY: 'Escaneie o QR Code', STARTING: 'Iniciando',
  INITIALIZING: 'Iniciando', AUTHENTICATING: 'Autenticando', NOT_CONFIGURED: 'Sessão não configurada',
  CREATED: 'Sessão criada', DISCONNECTED: 'Desconectado', STOPPED: 'Sessão parada', FAILED: 'Falha na sessão',
  VERIFYING_NUMBER: 'Aguardando confirmação do telefone', WRONG_NUMBER: 'O número pareado difere do telefone salvo',
  ACTION_REQUIRED: 'Verifique a sessão no OpenWA', UNKNOWN: 'Estado da sessão desconhecido',
};
const field = 'w-full rounded-lg border border-slate-300 bg-white px-3 py-2';

export function Settings() {
  const [members, setMembers] = useState<Member[]>();
  const [sources, setSources] = useState<Source[]>();
  const [connection, setConnection] = useState<Connection>();
  const [connectionFailed, setConnectionFailed] = useState(false);
  const [membersFailed, setMembersFailed] = useState(false);
  const [sourcesFailed, setSourcesFailed] = useState(false);
  const [welcomeFailed, setWelcomeFailed] = useState(false);
  const [phone, setPhone] = useState('');
  const [qr, setQr] = useState<string | null>(null);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [importKind, setImportKind] = useState('texto');
  const [welcome, setWelcome] = useState<string>();
  const [savedWelcome, setSavedWelcome] = useState<string>();
  const [question, setQuestion] = useState('');
  const [preview, setPreview] = useState<Preview>();
  const [previewFailed, setPreviewFailed] = useState(false);
  const loadConnection = useCallback(async () => {
    try {
      const current = await api<Connection>('/whatsapp/connection');
      setConnection(current);
      setPhone(current.phone_number ?? '');
      if (current.status === 'QR_READY' || current.status === 'STARTING') {
        setQr((await api<{ qr_code: string | null }>('/whatsapp/connection/qr')).qr_code);
      } else setQr(null);
      setConnectionFailed(false);
    } catch (failure) { setConnectionFailed(true); setQr(null); throw failure; }
  }, []);

  useEffect(() => {
    void api<Member[]>('/operators').then(setMembers).catch(failure => { setMembersFailed(true); setError(errorMessage(failure)); });
    void api<Source[]>('/knowledge').then(setSources).catch(failure => { setSourcesFailed(true); setError(errorMessage(failure)); });
    void api<{ message: string }>('/knowledge/welcome').then(value => {
      setWelcome(value.message); setSavedWelcome(value.message);
    }).catch(failure => { setWelcomeFailed(true); setError(errorMessage(failure)); });
    void loadConnection().catch(failure => setError(errorMessage(failure)));
  }, [loadConnection]);

  useEffect(() => {
    if (!connection || !['CREATED', 'STARTING', 'INITIALIZING', 'AUTHENTICATING', 'QR_READY', 'VERIFYING_NUMBER'].includes(connection.status)) return;
    const timer = window.setInterval(() => { void loadConnection().catch(failure => setError(errorMessage(failure))); }, 5_000);
    return () => window.clearInterval(timer);
  }, [connection, loadConnection]);

  async function run(action: () => Promise<void>, success: string) {
    setBusy(true); setError(''); setStatus('');
    try { await action(); setStatus(success); }
    catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(false); }
  }

  function addMember(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    void run(async () => {
      const member = await api<Member>('/operators', { method: 'POST', body: JSON.stringify(values) });
      setMembers(current => [...(current ?? []), member]); form.reset();
      if (!member.invite_sent) throw new ApiError(502, 'Operador cadastrado. O e-mail falhou. Use Reenviar convite.');
    }, 'Convite enviado.');
  }

  function importSource(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const source = String(data.get('source'));
    void run(async () => {
      const document = data.get('file');
      if (importKind === 'arquivo' && document instanceof File) {
        const kind = document.name.split('.').at(-1)?.toLowerCase();
        if (!kind || !['txt', 'pdf', 'docx'].includes(kind)) throw new ApiError(422, 'Selecione um arquivo TXT, PDF ou DOCX.');
        await api(`/knowledge/file?${new URLSearchParams({ kind, source })}`, { method: 'PUT', body: document });
      } else if (importKind === 'url') {
        await api('/knowledge/url', { method: 'PUT', body: JSON.stringify({ source, url: data.get('url') }) });
      } else {
        await api('/knowledge', { method: 'PUT', body: JSON.stringify({ source, text: data.get('text') }) });
      }
      setSources(await api<Source[]>('/knowledge')); setSourcesFailed(false); form.reset();
    }, 'Fonte salva.');
  }

  const connected = connection?.status === 'READY' || connection?.status === 'CONNECTED';
  const hasConnection = Boolean(connection?.phone_number || connection?.session_id || (connection && connection.status !== 'NOT_CONFIGURED'));
  const phoneDetail = connectionFailed ? 'Falha ao consultar a conexão' : connected ? 'Telefone cadastrado e sessão conectada'
    : connection?.phone_number && !connection.session_id ? 'Telefone salvo. Inicie o pareamento.' : connectionLabels[connection?.status ?? ''] ?? 'Salve o telefone da empresa';
  const pendingInvites = members?.some(member => member.invite_pending);
  const activeMember = members?.some(member => member.is_active);

  return <section className="mx-auto grid max-w-screen-xl gap-4 p-4" aria-label="Configurações">
    <h2 className="text-2xl font-semibold">Configurações</h2>
    {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-red-800">{error}</p>}
    {status && <p role="status" className="rounded-lg bg-teal-50 p-3 text-teal-900">{status}</p>}
    <Integrations refreshConnection={loadConnection} />
    <section className={settingsGrid}>
      <SettingsCard title="WhatsApp" state={connectionFailed ? 'warning' : !connection ? 'loading' : connected && connection.phone_number ? 'ready' : hasConnection ? 'warning' : 'missing'} detail={phoneDetail} action={<Button label="Salvar telefone" type="submit" form="settings-phone" variant="primary" isDisabled={busy || !phone.trim()} />}>
        <p>{connection?.phone_number && !connection.session_id ? phoneDetail : connectionLabels[connection?.status ?? ''] ?? 'Consultando…'}</p>
        <form id="settings-phone" onSubmit={event => {
          event.preventDefault();
          void run(async () => {
            const saved = await api<{ phone_number: string }>('/whatsapp/connection/phone', { method: 'PUT', body: JSON.stringify({ phone_number: phone }) });
            setPhone(saved.phone_number);
            setConnection(current => ({ ...current, status: current?.session_id && current.phone_number !== saved.phone_number ? 'VERIFYING_NUMBER' : current?.status ?? 'NOT_CONFIGURED', session_id: current?.session_id ?? null, phone_number: saved.phone_number }));
          }, 'Telefone do WhatsApp salvo.');
        }}>
          <label className="grid gap-1 text-sm">Número do WhatsApp<input name="phone_number" type="tel" autoComplete="tel" required maxLength={32} className={field} placeholder="+55 11 99999-9999" value={phone} onChange={event => setPhone(event.target.value)} /></label>
          <p className="mt-2 text-sm text-slate-600">Informe o número da empresa com DDI e DDD.</p>
        </form>
        {connection?.session_id && <p className="wrap-anywhere text-sm text-slate-600">Sessão: {connection.session_id}</p>}
        {qr?.startsWith('data:image/png;base64,') && <><p className="text-sm">Abra os aparelhos conectados no WhatsApp e escaneie o código.</p><img src={qr} alt="QR Code para parear o WhatsApp da empresa" width={192} height={192} /></>}
        {connection?.phone_number && (!connection.session_id || ['CREATED', 'DISCONNECTED', 'STOPPED', 'FAILED'].includes(connection.status)) &&
          <Button label="Iniciar pareamento" isDisabled={busy} onClick={() => void run(async () => {
            await api('/whatsapp/connection/pair', { method: 'POST' });
            await loadConnection();
          }, 'Sessão iniciada. Aguarde o QR Code.')} />}
        <Button label="Atualizar conexão" isDisabled={busy} onClick={() => void run(loadConnection, 'Status atualizado.')} />
      </SettingsCard>
      <SettingsCard title="Operadores" state={membersFailed ? 'warning' : !members ? 'loading' : pendingInvites ? 'warning' : activeMember ? 'ready' : 'missing'} detail={membersFailed ? 'Falha ao consultar os operadores' : pendingInvites ? 'Há convites pendentes' : activeMember ? 'Há operadores ativos' : 'Convide ou ative um operador'} action={<Button type="submit" form="settings-operator" label="Enviar convite" variant="primary" isDisabled={busy} />}>
        <ul className="grid gap-2">{(members ?? []).map(member => <li className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 pb-2" key={member.id}>
          <p className="break-all text-sm">{member.name}<br />{member.email}<br />{member.invite_pending ? 'Convite pendente' : member.is_active ? 'Ativo' : 'Desativado'}</p>
          {member.invite_pending ? <Button label="Reenviar convite" isDisabled={busy} onClick={() => void run(async () => {
            const result = await api<Member>(`/operators/${member.id}/invite`, { method: 'POST' });
            if (!result.invite_sent) throw new ApiError(502, 'Não foi possível enviar o convite.');
          }, 'Convite reenviado.')} /> : <Button label={member.is_active ? 'Desativar' : 'Reativar'} isDisabled={busy} onClick={() => {
            if (member.is_active && !window.confirm(`Desativar ${member.name}? As conversas voltarão à fila.`)) return;
            void run(async () => {
              const updated = await api<Member>(`/operators/${member.id}`, { method: 'PUT', body: JSON.stringify({ name: member.name, is_active: !member.is_active }) });
              setMembers(current => current?.map(item => item.id === updated.id ? updated : item));
            }, 'Lista de operadores atualizada.');
          }} />}
          <details className="w-full text-sm"><summary className="cursor-pointer underline">Editar operador</summary>
            <form className="mt-2 grid gap-2" onSubmit={event => {
              event.preventDefault(); const form = event.currentTarget;
              const values = new FormData(form);
              void run(async () => {
                const updated = await api<Member>(`/operators/${member.id}`, { method: 'PUT', body: JSON.stringify({
                  name: values.get('name'), is_active: member.is_active,
                }) });
                setMembers(current => current?.map(item => item.id === updated.id ? updated : item));
                form.reset();
              }, 'Operador atualizado.');
            }}>
              <label className="grid gap-1">Nome<input name="name" defaultValue={member.name} required maxLength={100} className={field} /></label>
              <Button label="Aplicar edição" type="submit" isDisabled={busy} />
            </form>
          </details>
        </li>)}</ul>
        <form id="settings-operator" className="grid gap-2" onSubmit={addMember}>
          <label className="grid gap-1 text-sm">Nome<input name="name" required maxLength={100} className={field} /></label>
          <label className="grid gap-1 text-sm">E-mail<input name="email" required type="email" maxLength={150} className={field} /></label>
        </form>
      </SettingsCard>
      <SettingsCard title="Base de conhecimento" state={sourcesFailed ? 'warning' : !sources ? 'loading' : sources.length ? 'ready' : 'missing'} detail={sourcesFailed ? 'Falha ao consultar as fontes' : sources?.length ? 'Há fontes adicionadas' : 'Adicione a primeira fonte'} action={<Button type="submit" form="settings-source" label="Salvar fonte" variant="primary" isDisabled={busy} />}>
        <p className="text-sm text-slate-600">Adicione fontes sobre a Nexus, seus serviços, aplicativos e funcionalidades.</p>
        <ul className="grid gap-2">{(sources ?? []).map(source => <li className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 pb-2" key={source.source}>
          <p className="wrap-anywhere text-sm">{source.source} · {source.chunks} trecho(s)</p>
          <Button label="Remover" isDisabled={busy} onClick={() => {
            if (!window.confirm(`Remover a fonte ${source.source}?`)) return;
            void run(async () => {
              await api(`/knowledge?source=${encodeURIComponent(source.source)}`, { method: 'DELETE' });
              setSources(current => current?.filter(item => item.source !== source.source));
            }, 'Fonte removida.');
          }} />
        </li>)}</ul>
        <form id="settings-source" className="grid gap-2" onSubmit={importSource}>
          <label className="grid gap-1 text-sm">Nome da fonte<input name="source" required maxLength={200} className={field} /></label>
          <label className="grid gap-1 text-sm">Origem<select value={importKind} onChange={event => setImportKind(event.target.value)} className={field}><option value="texto">Texto</option><option value="arquivo">Arquivo</option><option value="url">Página web</option></select></label>
          {importKind === 'texto' && <label className="grid gap-1 text-sm">Conteúdo<textarea name="text" required maxLength={40_000} rows={4} className={field} /></label>}
          {importKind === 'url' && <label className="grid gap-1 text-sm">URL autorizada<input name="url" required type="url" maxLength={2000} className={field} /></label>}
          {importKind === 'arquivo' && <label className="grid gap-1 text-sm">Arquivo TXT, PDF ou DOCX<input name="file" required type="file" accept=".txt,.pdf,.docx" className={field} /></label>}
        </form>
      </SettingsCard>
    <SettingsCard title="Boas-vindas" state={welcomeFailed ? 'warning' : savedWelcome === undefined ? 'loading' : savedWelcome ? 'ready' : 'missing'} detail={welcomeFailed ? 'Falha ao consultar a mensagem padrão' : savedWelcome ? 'Mensagem padrão salva' : 'Sem mensagem padrão'} action={<Button type="submit" form="settings-welcome" label="Salvar boas-vindas" variant="primary" isDisabled={busy || welcome === undefined} />}>
      <form id="settings-welcome" className="grid gap-3" onSubmit={event => {
        event.preventDefault();
        if (welcome === undefined) return;
        void run(async () => {
          const saved = await api<{ message: string }>('/knowledge/welcome', { method: 'PUT', body: JSON.stringify({ message: welcome }) });
          setWelcome(saved.message);
          setSavedWelcome(saved.message);
        }, 'Mensagem de boas-vindas salva.');
      }}>
        <TextArea label="Mensagem padrão" description="Aparece na primeira resposta automática e depois de 15 minutos sem interação. Deixe em branco para desativar o texto fixo." value={welcome ?? ''} onChange={setWelcome} maxLength={500} isDisabled={busy || welcome === undefined} />
      </form>
    </SettingsCard>
    <SettingsCard title="Testar a IA" state={previewFailed || preview?.status === 'unavailable' ? 'warning' : preview ? 'ready' : 'missing'} detail={previewFailed ? 'Falha ao executar o teste' : preview ? previewLabel[preview.status] : 'Ainda sem teste nesta tela'} action={<Button type="submit" form="settings-preview" label="Testar resposta" variant="primary" isDisabled={busy || !question.trim()} />}>
      <form id="settings-preview" className="grid gap-3" onSubmit={event => {
        event.preventDefault();
        setPreview(undefined);
        setPreviewFailed(false);
        void run(async () => {
          try { setPreview(await api<Preview>('/knowledge/preview', { method: 'POST', body: JSON.stringify({ question }) })); }
          catch (failure) { setPreviewFailed(true); throw failure; }
        }, '');
      }}>
        <TextArea label="Pergunta de teste" description="Simula o início de uma conversa. Use uma pergunta sem dados pessoais." value={question} onChange={setQuestion} maxLength={4000} isDisabled={busy} />
      </form>
      {preview && <section role="status" className="grid gap-2 rounded-lg border border-slate-200 bg-slate-50 p-4">
        <h4 className="font-semibold">{previewLabel[preview.status]}</h4>
        <p className="whitespace-pre-wrap wrap-anywhere text-sm">{preview.message}</p>
        {preview.sources.length > 0 && <p className="wrap-anywhere text-sm text-slate-700">Fontes recuperadas: {preview.sources.join(', ')}</p>}
      </section>}
    </SettingsCard>
    </section>
  </section>;
}
