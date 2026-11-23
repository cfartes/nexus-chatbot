'use client';

import { Button } from '@astryxdesign/core/Button';
import { ProgressBar } from '@astryxdesign/core/ProgressBar';
import { TextArea } from '@astryxdesign/core/TextArea';
import { TextInput } from '@astryxdesign/core/TextInput';
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { api, ApiError, errorMessage, upload } from './api';
import { Integrations } from './integrations';
import { SettingsCard, settingsGrid } from './settings-card';

type Source = { source: string; chunks: number };
type AssistantSettings = { message: string; assistant_name?: string | null };
type Origin = { slug: string; name: string };
type Connection = { status: string; phone_number: string | null; session_id: string | null; error?: string | null; retry_after?: number | null };
type Preview = { status: 'answered' | 'clarify' | 'handoff' | 'unavailable'; message: string; sources: string[];
  reason?: string | null; excerpts?: { source: string; content: string }[] };
const previewLabel = { answered: 'Resposta automática', clarify: 'Pediria um esclarecimento',
  handoff: 'Encaminharia para um atendente', unavailable: 'IA indisponível' };
const connectionLabels: Record<string, string> = {
  READY: 'Conectado', CONNECTED: 'Conectado', QR_READY: 'Escaneie o QR Code', STARTING: 'Iniciando',
  INITIALIZING: 'Iniciando', AUTHENTICATING: 'Autenticando', NOT_CONFIGURED: 'Sessão não configurada',
  CREATED: 'Sessão criada', DISCONNECTED: 'Desconectado', STOPPED: 'Sessão parada', FAILED: 'Falha na sessão',
  VERIFYING_NUMBER: 'Aguardando confirmação do telefone', WRONG_NUMBER: 'O número pareado difere do telefone salvo',
  UNAVAILABLE: 'Status da sessão indisponível',
  RATE_LIMITED: 'Aguardando o limite do OpenWA',
  ACTION_REQUIRED: 'Verifique a sessão no OpenWA', UNKNOWN: 'Estado da sessão desconhecido',
};
const field = 'w-full rounded-lg border border-slate-300 bg-white px-3 py-2';

export function Settings({ platformAdmin }: { platformAdmin: boolean }) {
  const [sources, setSources] = useState<Source[]>();
  const [origins, setOrigins] = useState<Origin[]>();
  const [originsFailed, setOriginsFailed] = useState(false);
  const [originName, setOriginName] = useState('');
  const [originSlug, setOriginSlug] = useState('');
  const [connection, setConnection] = useState<Connection>();
  const [connectionError, setConnectionError] = useState('');
  const [sourcesError, setSourcesError] = useState('');
  const [importError, setImportError] = useState('');
  const [fileProgress, setFileProgress] = useState<number | 'sending' | 'processing'>();
  const [alertEmail, setAlertEmail] = useState<string>();
  const [savedAlertEmail, setSavedAlertEmail] = useState<string>();
  const [alertError, setAlertError] = useState('');
  const [welcomeFailed, setWelcomeFailed] = useState(false);
  const [phone, setPhone] = useState('');
  const [qr, setQr] = useState<string | null>(null);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [importKind, setImportKind] = useState('texto');
  const [welcome, setWelcome] = useState<string>();
  const [savedWelcome, setSavedWelcome] = useState<string>();
  const [assistantName, setAssistantName] = useState('');
  const [savedAssistantName, setSavedAssistantName] = useState('');
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
      setConnectionError(current.error ?? '');
    } catch (failure) {
      setConnectionError(`WhatsApp · ${errorMessage(failure)}`);
      setQr(null);
    }
  }, []);

  const loadSources = useCallback(async () => {
    setSourcesError('');
    try { setSources(await api<Source[]>('/knowledge')); }
    catch (failure) { setSourcesError(errorMessage(failure)); }
  }, []);

  useEffect(() => {
    void loadSources();
    void api<{ email: string }>('/integrations/handoff-email').then(({ email }) => {
      setAlertEmail(email); setSavedAlertEmail(email);
    }).catch(failure => setAlertError(errorMessage(failure)));
    void api<Origin[]>('/knowledge/origins').then(setOrigins).catch(failure => { setOriginsFailed(true); setError(errorMessage(failure)); });
    void api<AssistantSettings>('/knowledge/welcome').then(value => {
      setWelcome(value.message); setSavedWelcome(value.message);
      setAssistantName(value.assistant_name ?? ''); setSavedAssistantName(value.assistant_name ?? '');
    }).catch(failure => { setWelcomeFailed(true); setError(errorMessage(failure)); });
    void loadConnection();
  }, [loadConnection, loadSources]);

  useEffect(() => {
    if (!connection || !['CREATED', 'STARTING', 'INITIALIZING', 'AUTHENTICATING', 'QR_READY', 'VERIFYING_NUMBER', 'RATE_LIMITED'].includes(connection.status)) return;
    const delay = connection.status === 'RATE_LIMITED' ? (connection.retry_after ?? 60) * 1000 : 20_000;
    const timer = window.setInterval(() => { void loadConnection(); }, delay);
    return () => window.clearInterval(timer);
  }, [connection, loadConnection]);

  async function run(action: () => Promise<void>, success: string, onError = setError) {
    setBusy(true); setError(''); setStatus('');
    try { await action(); setStatus(success); }
    catch (failure) { onError(errorMessage(failure)); }
    finally { setBusy(false); }
  }

  function importSource(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !sources || sourcesError) return;
    setImportError('');
    const form = event.currentTarget;
    const data = new FormData(form);
    const source = String(data.get('source'));
    void run(async () => {
      const document = data.get('file');
      let saved: Source;
      if (importKind === 'arquivo') {
        if (!(document instanceof File) || !document.size) throw new ApiError(422, 'Selecione um arquivo com conteúdo.');
        if (document.size > 4 * 1024 ** 2) throw new ApiError(413, 'O arquivo excede o limite de 4 MiB.');
        const kind = document.name.split('.').at(-1)?.toLowerCase();
        if (!kind || !['txt', 'md', 'pdf', 'docx'].includes(kind)) throw new ApiError(422, 'Selecione um arquivo TXT, Markdown (.md), PDF ou DOCX.');
        setFileProgress(0);
        try {
          saved = await upload<Source>(`/knowledge/file?${new URLSearchParams({ kind, source })}`, document,
            percent => setFileProgress(percent ?? 'sending'), () => setFileProgress('processing'));
        } finally {
          setFileProgress(undefined);
        }
      } else if (importKind === 'url') {
        saved = await api<Source>('/knowledge/url', { method: 'PUT', body: JSON.stringify({ source, url: data.get('url') }) });
      } else {
        saved = await api<Source>('/knowledge', { method: 'PUT', body: JSON.stringify({ source, text: data.get('text') }) });
      }
      setSources(current => [...(current ?? []).filter(item => item.source !== saved.source), saved]
        .sort((first, second) => first.source.localeCompare(second.source, 'pt-BR')));
      form.reset();
    }, 'Fonte salva.', setImportError);
  }

  const connected = connection?.status === 'READY' || connection?.status === 'CONNECTED';
  const hasConnection = Boolean(connection?.phone_number || connection?.session_id || (connection && connection.status !== 'NOT_CONFIGURED'));
  const phoneDetail = connectionError || (connected ? 'Telefone cadastrado e sessão conectada'
    : connection?.phone_number && !connection.session_id ? 'Telefone salvo. Inicie o pareamento.' : connectionLabels[connection?.status ?? ''] ?? 'Salve o telefone da empresa');
  const originPhone = connection?.phone_number?.replace(/\D/g, '');

  return <section className="mx-auto grid max-w-screen-xl gap-4 p-4" aria-label="Configurações">
    <h2 className="text-2xl font-semibold">Configurações</h2>
    {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-red-800">{error}</p>}
    {status && <p role="status" className="rounded-lg bg-teal-50 p-3 text-teal-900">{status}</p>}
    {platformAdmin && <Integrations refreshConnection={loadConnection} />}
    <section className={settingsGrid}>
      <SettingsCard title="WhatsApp" state={connectionError ? 'warning' : !connection ? 'loading' : connected && connection.phone_number ? 'ready' : hasConnection ? 'warning' : 'missing'} detail={phoneDetail} action={<Button label="Salvar telefone" type="submit" form="settings-phone" variant="primary" isDisabled={busy || !phone.trim()} />}>
        <p aria-live="polite">{connectionError || (connection?.phone_number && !connection.session_id ? phoneDetail : connectionLabels[connection?.status ?? ''] ?? 'Consultando…')}</p>
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
        <Button label="Atualizar conexão" isDisabled={busy} onClick={() => void loadConnection()} />
      </SettingsCard>
      <SettingsCard title="Base de conhecimento" state={sourcesError ? 'warning' : !sources ? 'loading' : sources.length ? 'ready' : 'missing'} detail={sourcesError ? 'Falha ao consultar as fontes' : sources?.length ? 'Há fontes adicionadas' : 'Adicione a primeira fonte'} action={<Button type="submit" form="settings-source" label="Salvar fonte" variant="primary" isDisabled={busy || !sources || Boolean(sourcesError)} />}>
        <p className="text-sm text-slate-600">Adicione fontes sobre a Nexus, seus serviços, aplicativos e funcionalidades.</p>
        {fileProgress !== undefined && <ProgressBar label={fileProgress === 'processing' ? 'Processando e indexando o arquivo…' : 'Enviando arquivo…'}
          value={typeof fileProgress === 'number' ? fileProgress : 0} isIndeterminate={typeof fileProgress !== 'number'} hasValueLabel />}
        {importError && <p role="alert" className="text-sm text-red-800">{importError}</p>}
        {sourcesError ? <section className="grid gap-2">
          <p role="alert" className="text-sm text-red-800">Falha ao consultar as fontes. {sourcesError}</p>
          <Button label="Atualizar fontes" isDisabled={busy} onClick={() => void loadSources()} />
        </section> : <p role="status" className="text-sm font-medium">{sources ? `${sources.length} ${sources.length === 1 ? 'fonte cadastrada' : 'fontes cadastradas'}` : 'Consultando fontes…'}</p>}
        <ul className="grid gap-2">{(sources ?? []).map(source => <li className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 pb-2" key={source.source}>
          <p className="wrap-anywhere text-sm">{source.source} · {source.chunks} trecho(s)</p>
          <a className="text-sm font-medium text-nexus-petroleo underline"
            href={`/api/v1/knowledge/download?source=${encodeURIComponent(source.source)}`}
            aria-label={`Baixar ${source.source}`}>Baixar</a>
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
          <label className="grid gap-1 text-sm">Origem<select value={importKind} disabled={busy} onChange={event => { setImportKind(event.target.value); setImportError(''); }} className={field}><option value="texto">Texto</option><option value="arquivo">Arquivo</option><option value="url">Página web</option></select></label>
          {importKind === 'texto' && <label className="grid gap-1 text-sm">Conteúdo<textarea name="text" required maxLength={40_000} rows={4} className={field} /></label>}
          {importKind === 'url' && <label className="grid gap-1 text-sm">URL autorizada<input name="url" required type="url" maxLength={2000} className={field} /></label>}
          {importKind === 'arquivo' && <label className="grid gap-1 text-sm">Arquivo TXT, Markdown (.md), PDF ou DOCX<input name="file" required type="file" accept=".txt,.md,.pdf,.docx" disabled={busy} onChange={() => setImportError('')} className={field} /></label>}
        </form>
      </SettingsCard>
    <SettingsCard title="Avisos de atendimento humano" state={alertError ? 'warning' : savedAlertEmail === undefined ? 'loading' : savedAlertEmail ? 'ready' : 'missing'} action={<Button type="submit" form="settings-handoff-email" label="Salvar e-mail" variant="primary" isDisabled={busy || alertEmail === undefined} />}>
      {alertError && <p role="alert" className="text-sm text-red-800">{alertError}</p>}
      <form id="settings-handoff-email" onSubmit={event => {
        event.preventDefault();
        if (alertEmail === undefined) return;
        void run(async () => {
          const saved = await api<{ email: string }>('/integrations/handoff-email', {
            method: 'PUT', body: JSON.stringify({ email: alertEmail.trim() }),
          });
          setSavedAlertEmail(saved.email); setAlertEmail(saved.email);
        }, 'E-mail de atendimento humano salvo.');
      }}>
        <TextInput label="E-mail da equipe" type="email" value={alertEmail ?? ''} onChange={value => setAlertEmail(value.slice(0, 150))}
          isDisabled={busy || alertEmail === undefined} description="Recebe o aviso quando uma conversa entra na fila humana. Deixe vazio para desativar o e-mail." />
      </form>
    </SettingsCard>
    <SettingsCard title="Origens de contato" state={originsFailed ? 'warning' : !origins ? 'loading' : !origins.length ? 'missing' : originPhone ? 'ready' : 'warning'} detail={originsFailed ? 'Falha ao consultar origens' : !origins?.length ? 'Cadastre uma origem por produto' : originPhone ? 'Links de WhatsApp disponíveis' : 'Salve o telefone para gerar os links'} action={<Button type="submit" form="settings-origin" label="Salvar origem" variant="primary" isDisabled={busy || !origins || !originName.trim() || !/^[a-z0-9]+(-[a-z0-9]+)*$/.test(originSlug)} />}>
      <form id="settings-origin" className="grid gap-3" onSubmit={event => {
        event.preventDefault();
        void run(async () => {
          await api<Origin>('/knowledge/origins', { method: 'PUT', body: JSON.stringify({ name: originName, slug: originSlug }) });
          setOrigins(await api<Origin[]>('/knowledge/origins'));
          setOriginName(''); setOriginSlug('');
        }, 'Origem salva.');
      }}>
        <TextInput label="Nome do produto" value={originName} onChange={value => setOriginName(value.slice(0, 100))} isRequired isDisabled={busy} />
        <TextInput label="Código da origem" description="Use letras minúsculas, números e hífens. Exemplo rotafy." value={originSlug} onChange={value => setOriginSlug(value.toLowerCase().slice(0, 50))} isRequired isDisabled={busy} />
      </form>
      {!!origins?.length && <ul className="grid gap-2">
        {origins.map(origin => <li key={origin.slug} className="flex flex-wrap items-center justify-between gap-2">
          <p className="break-all">{origin.name} <small>({origin.slug})</small></p>
          {originPhone && <Button label={`Copiar link de ${origin.name}`} isDisabled={busy} onClick={() => void run(async () => {
            const message = `Olá, vim pelo ${origin.name}. [Nexus:${origin.slug}]`;
            await navigator.clipboard.writeText(`https://wa.me/${originPhone}?text=${encodeURIComponent(message)}`);
          }, 'Link copiado.')} />}
        </li>)}
      </ul>}
    </SettingsCard>

    <SettingsCard title="Assistente e boas-vindas" state={welcomeFailed ? 'warning' : savedWelcome === undefined ? 'loading' : savedWelcome || savedAssistantName ? 'ready' : 'missing'} detail={welcomeFailed ? 'Falha ao consultar o assistente' : savedWelcome || savedAssistantName ? 'Configuração salva' : 'Usando as boas-vindas padrão'} action={<Button type="submit" form="settings-welcome" label="Salvar assistente" variant="primary" isDisabled={busy || welcome === undefined} />}>
      <form id="settings-welcome" className="grid gap-3" onSubmit={event => {
        event.preventDefault();
        if (welcome === undefined) return;
        void run(async () => {
          const saved = await api<AssistantSettings>('/knowledge/welcome', {
            method: 'PUT', body: JSON.stringify({ message: welcome, assistant_name: assistantName.trim() }),
          });
          setWelcome(saved.message);
          setSavedWelcome(saved.message);
          setAssistantName(saved.assistant_name ?? '');
          setSavedAssistantName(saved.assistant_name ?? '');
        }, 'Configuração do assistente salva.');
      }}>
        <TextInput label="Nome do assistente" description="Opcional, até 80 caracteres. O assistente se apresenta com este nome no início do contato direto." value={assistantName} onChange={setAssistantName} isDisabled={busy || welcome === undefined} />
        <TextArea label="Mensagem padrão" description="Aparece no início de atendimentos de contato direto. Quando o campo está vazio, o bot usa “Olá!”." value={welcome ?? ''} onChange={setWelcome} maxLength={500} isDisabled={busy || welcome === undefined} />
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
        {preview.reason && <p className="text-sm text-slate-700">{preview.reason}</p>}
        {preview.sources.length > 0 && <p className="wrap-anywhere text-sm text-slate-700">Fontes recuperadas: {preview.sources.join(', ')}</p>}
        {preview.excerpts && preview.excerpts.length > 0 && <details>
          <summary className="cursor-pointer text-sm font-medium">Trechos consultados</summary>
          <ul className="mt-2 grid max-h-80 gap-3 overflow-auto">
            {preview.excerpts.map((excerpt, index) => <li key={index} className="grid gap-1 text-sm">
              <strong>{excerpt.source}</strong>
              <p className="whitespace-pre-wrap wrap-anywhere">{excerpt.content}</p>
            </li>)}
          </ul>
        </details>}
      </section>}
    </SettingsCard>
    </section>
  </section>;
}
