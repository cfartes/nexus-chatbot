'use client';

import { Button } from '@astryxdesign/core/Button';
import { useEffect, useState, type FormEvent } from 'react';
import { api, errorMessage } from './api';
import { SettingsCard, settingsGrid } from './settings-card';

const models = { openai: 'gpt-4o-mini', gemini: 'gemini-2.5-flash', anthropic: 'claude-sonnet-4-6', ollama: 'qwen3:4b' };
type Provider = keyof typeof models;
interface IntegrationView {
  provider: Provider; model: string; embedding_model: string; ai_has_key: boolean; embedding_has_key: boolean;
  ollama_url: string | null; resend_sender: string; resend_recipient: string; resend_has_key: boolean;
  openwa_url: string | null; openwa_webhook_status: 'not_configured' | 'pending' | 'active' | 'error'; openwa_has_key: boolean;
}

const receptionLabel = { not_configured: 'Aguardando configuração', pending: 'Cadastro automático pendente',
  active: 'Cadastro confirmado no OpenWA', error: 'Falha no cadastro automático' };

const field = 'w-full rounded-lg border border-slate-300 bg-white px-3 py-2';

export function Integrations({ refreshConnection }: { refreshConnection: () => Promise<void> }) {
  const [config, setConfig] = useState<IntegrationView>();
  const [provider, setProvider] = useState<Provider>('openai');
  const [model, setModel] = useState(models.openai);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [failed, setFailed] = useState<'ai' | 'resend' | 'openwa'>();

  useEffect(() => {
    const controller = new AbortController();
    api<IntegrationView>('/integrations', { signal: controller.signal }).then(result => {
      setConfig(result); setProvider(result.provider); setModel(result.model);
    }).catch(failure => { if (!controller.signal.aborted) setError(errorMessage(failure)); });
    const timer = window.setInterval(() => {
      void api<IntegrationView>('/integrations', { signal: controller.signal }).then(setConfig).catch(() => undefined);
    }, 15_000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, []);

  async function save(event: FormEvent<HTMLFormElement>, integration: 'ai' | 'resend' | 'openwa') {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    const body = Object.fromEntries(Object.entries(data).filter(([key, value]) => !key.endsWith('_key') || value !== ''));
    setBusy(true); setStatus(''); setError(''); setFailed(undefined);
    try {
      setConfig(await api<IntegrationView>(`/integrations/${integration}`, { method: 'PUT', body: JSON.stringify(body) }));
      for (const input of form.querySelectorAll<HTMLInputElement>('input[type=password]')) input.value = '';
      setStatus('Configuração salva.');
      if (integration === 'openwa') void refreshConnection().catch(failure => { setFailed('openwa'); setError(errorMessage(failure)); });
    } catch (failure) { setFailed(integration); setError(errorMessage(failure)); }
    finally { setBusy(false); }
  }

  const aiReady = config?.provider === 'ollama' ? Boolean(config.ollama_url && config.embedding_model)
    : Boolean(config?.ai_has_key && (config.provider !== 'anthropic' || config.embedding_has_key));
  const aiPartial = Boolean(config && (config.provider === 'ollama' || config.ai_has_key || (config.provider === 'anthropic' && config.embedding_has_key)));
  const resendReady = Boolean(config?.resend_has_key && config.resend_sender && config.resend_recipient);
  const resendPartial = Boolean(config?.resend_has_key || config?.resend_sender || config?.resend_recipient);
  const openwaReady = config?.openwa_webhook_status === 'active';
  const openwaPartial = Boolean(config?.openwa_url || config?.openwa_has_key);

  return <section className="grid gap-3" aria-label="Integrações">
    <h3 className="text-xl font-semibold">Integrações</h3>
    {status && <p role="status" className="text-sm text-teal-800">{status}</p>}
    {error && <p role="alert" className="text-sm text-red-800">{error}</p>}
    {config ? <section className={settingsGrid}>
      <SettingsCard title="Inteligência artificial" state={failed === 'ai' ? 'warning' : aiReady ? 'ready' : aiPartial ? 'warning' : 'missing'} detail={failed === 'ai' ? 'Falha ao atualizar a configuração' : aiReady ? 'Provedor e modelo definidos' : 'Confira o provedor, a chave e os embeddings'} action={<Button type="submit" form="settings-ai" label="Salvar IA" variant="primary" isDisabled={busy} />}>
      <form id="settings-ai" className="grid gap-3" onSubmit={event => void save(event, 'ai')}>
        <label className="grid gap-1 text-sm">Provedor<select className={field} name="provider" value={provider} onChange={event => {
          const selected = event.target.value as Provider;
          setProvider(selected); setModel(selected === config.provider ? config.model : models[selected]);
        }}><option value="openai">OpenAI</option><option value="gemini">Google Gemini</option><option value="anthropic">Anthropic Claude</option><option value="ollama">Ollama local</option></select></label>
        <label className="grid gap-1 text-sm">Modelo<input className={field} name="model" required maxLength={120} value={model} onChange={event => setModel(event.target.value)} /></label>
        {provider !== 'ollama' && <label className="grid gap-1 text-sm">Chave de IA<input className={field} name="api_key" type="password" maxLength={1000} autoComplete="new-password" placeholder={config.ai_has_key && provider === config.provider ? 'Chave salva' : 'Informe a chave'} /></label>}
        {provider === 'anthropic' && <label className="grid gap-1 text-sm">Chave OpenAI para embeddings<input className={field} name="embedding_key" type="password" autoComplete="new-password" maxLength={1000} placeholder={config.embedding_has_key ? 'Chave disponível' : 'Informe a chave'} /></label>}
        {provider === 'ollama' && <><p className="wrap-anywhere text-sm">Servidor local: {config.ollama_url ?? 'Ainda não configurado'}</p><label className="grid gap-1 text-sm">Modelo de embeddings<input className={field} name="embedding_model" defaultValue={config.embedding_model} required maxLength={120} /></label></>}
        <p className="text-sm text-slate-600">Se o modelo de embeddings mudar, reimporte as fontes para usar a nova indexação.</p>
      </form>
      </SettingsCard>
      <SettingsCard title="Resend" state={failed === 'resend' ? 'warning' : resendReady ? 'ready' : resendPartial ? 'warning' : 'missing'} detail={failed === 'resend' ? 'Falha ao atualizar a configuração' : resendReady ? 'Chave, remetente e destinatário definidos' : 'Confira os dados de convites e alertas'} action={<Button type="submit" form="settings-resend" label="Salvar Resend" variant="primary" isDisabled={busy} />}>
      <form id="settings-resend" className="grid gap-3" onSubmit={event => void save(event, 'resend')}>
        <label className="grid gap-1 text-sm">Chave Resend<input className={field} name="api_key" type="password" autoComplete="new-password" maxLength={1000} placeholder={config.resend_has_key ? 'Chave salva' : 'Informe a chave'} /></label>
        <label className="grid gap-1 text-sm">Remetente verificado<input className={field} name="sender" defaultValue={config.resend_sender} required maxLength={200} /></label>
        <label className="grid gap-1 text-sm">E-mail da equipe para alertas<input className={field} name="recipient" type="email" defaultValue={config.resend_recipient} maxLength={150} /></label>
        <p className="text-sm text-slate-600">O remetente envia convites. O e-mail da equipe recebe alertas de transbordo.</p>
      </form>
      </SettingsCard>
      <SettingsCard title="OpenWA" state={failed === 'openwa' || config.openwa_webhook_status === 'error' ? 'warning' : openwaReady ? 'ready' : openwaPartial ? 'warning' : 'missing'} detail={failed === 'openwa' ? 'Falha ao atualizar ou consultar o OpenWA' : receptionLabel[config.openwa_webhook_status]} action={<Button type="submit" form="settings-openwa" label="Salvar OpenWA" variant="primary" isDisabled={busy} />}>
      <form id="settings-openwa" className="grid gap-3" onSubmit={event => void save(event, 'openwa')}>
        <label className="grid gap-1 text-sm">Endereço do servidor<input key={config.openwa_url ?? ''} className={field} name="base_url" type="url" required maxLength={300} defaultValue={config.openwa_url ?? ''} placeholder="https://openwa.exemplo.com/api" /></label>
        <p className="wrap-anywhere text-sm">Recebimento: {receptionLabel[config.openwa_webhook_status]}</p>
        <label className="grid gap-1 text-sm">Chave OpenWA<input className={field} name="api_key" type="password" autoComplete="new-password" maxLength={1000} placeholder={config.openwa_has_key ? 'Chave salva' : 'Informe a chave'} /></label>
        <p className="text-sm text-slate-600">Use um endereço HTTPS autorizado terminado em /api. Ao trocar de servidor, informe a chave dele. Consulte o status e o QR Code em WhatsApp.</p>
      </form>
      </SettingsCard>
    </section> : <section className={settingsGrid}>{['Inteligência artificial', 'Resend', 'OpenWA'].map(title =>
      <SettingsCard key={title} title={title} state={error ? 'warning' : 'loading'} action={null}>
        <p className="text-sm text-slate-600">{error ? 'Não foi possível consultar esta integração.' : 'Consultando configuração…'}</p>
      </SettingsCard>
    )}</section>}
  </section>;
}
