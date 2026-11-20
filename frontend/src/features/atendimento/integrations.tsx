'use client';

import { Button } from '@astryxdesign/core/Button';
import { useEffect, useState, type FormEvent } from 'react';
import { api, errorMessage } from './api';

const models = { openai: 'gpt-4o-mini', gemini: 'gemini-2.5-flash', anthropic: 'claude-sonnet-4-6', ollama: 'qwen3:4b' };
type Provider = keyof typeof models;
interface IntegrationView {
  provider: Provider; model: string; embedding_model: string; ai_has_key: boolean; embedding_has_key: boolean;
  ollama_url: string | null; resend_sender: string; resend_recipient: string; resend_has_key: boolean;
  openwa_url: string | null; openwa_webhook_url: string | null; openwa_has_key: boolean;
}

const field = 'w-full rounded-lg border border-slate-300 bg-white px-3 py-2';
const card = 'grid content-start gap-3 rounded-2xl border border-slate-200 bg-white p-5';

export function Integrations({ refreshConnection }: { refreshConnection: () => Promise<void> }) {
  const [config, setConfig] = useState<IntegrationView>();
  const [provider, setProvider] = useState<Provider>('openai');
  const [model, setModel] = useState(models.openai);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    api<IntegrationView>('/integrations', { signal: controller.signal }).then(result => {
      setConfig(result); setProvider(result.provider); setModel(result.model);
    }).catch(failure => { if (!controller.signal.aborted) setError(errorMessage(failure)); });
    return () => controller.abort();
  }, []);

  async function save(event: FormEvent<HTMLFormElement>, integration: 'ai' | 'resend' | 'openwa') {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    const body = Object.fromEntries(Object.entries(data).filter(([key, value]) => !key.endsWith('_key') || value !== ''));
    setBusy(true); setStatus(''); setError('');
    try {
      setConfig(await api<IntegrationView>(`/integrations/${integration}`, { method: 'PUT', body: JSON.stringify(body) }));
      for (const input of form.querySelectorAll<HTMLInputElement>('input[type=password]')) input.value = '';
      setStatus('Configuração salva.');
      if (integration === 'openwa') void refreshConnection().catch(failure => setError(errorMessage(failure)));
    } catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(false); }
  }

  return <section className="grid gap-3" aria-label="Integrações">
    <h3 className="text-xl font-semibold">Integrações</h3>
    {status && <p role="status" className="text-sm text-teal-800">{status}</p>}
    {error && <p role="alert" className="text-sm text-red-800">{error}</p>}
    {config ? <section className="grid gap-4 lg:grid-cols-3">
      <form className={card} onSubmit={event => void save(event, 'ai')}>
        <h4 className="text-lg font-semibold">Inteligência artificial</h4>
        <label className="grid gap-1 text-sm">Provedor<select className={field} name="provider" value={provider} onChange={event => {
          const selected = event.target.value as Provider;
          setProvider(selected); setModel(selected === config.provider ? config.model : models[selected]);
        }}><option value="openai">OpenAI</option><option value="gemini">Google Gemini</option><option value="anthropic">Anthropic Claude</option><option value="ollama">Ollama local</option></select></label>
        <label className="grid gap-1 text-sm">Modelo<input className={field} name="model" required maxLength={120} value={model} onChange={event => setModel(event.target.value)} /></label>
        {provider !== 'ollama' && <label className="grid gap-1 text-sm">Chave de IA<input className={field} name="api_key" type="password" maxLength={1000} autoComplete="new-password" placeholder={config.ai_has_key && provider === config.provider ? 'Chave salva' : 'Informe a chave'} /></label>}
        {provider === 'anthropic' && <label className="grid gap-1 text-sm">Chave OpenAI para embeddings<input className={field} name="embedding_key" type="password" autoComplete="new-password" maxLength={1000} placeholder={config.embedding_has_key ? 'Chave disponível' : 'Informe a chave'} /></label>}
        {provider === 'ollama' && <><p className="wrap-anywhere text-sm">Servidor local: {config.ollama_url ?? 'Ainda não configurado'}</p><label className="grid gap-1 text-sm">Modelo de embeddings<input className={field} name="embedding_model" defaultValue={config.embedding_model} required maxLength={120} /></label></>}
        <p className="text-sm text-slate-600">Se o modelo de embeddings mudar, reimporte as fontes para usar a nova indexação.</p>
        <Button type="submit" label="Salvar IA" variant="primary" isDisabled={busy} />
      </form>
      <form className={card} onSubmit={event => void save(event, 'resend')}>
        <h4 className="text-lg font-semibold">Resend</h4>
        <label className="grid gap-1 text-sm">Chave Resend<input className={field} name="api_key" type="password" autoComplete="new-password" maxLength={1000} placeholder={config.resend_has_key ? 'Chave salva' : 'Informe a chave'} /></label>
        <label className="grid gap-1 text-sm">Remetente verificado<input className={field} name="sender" defaultValue={config.resend_sender} required maxLength={200} /></label>
        <label className="grid gap-1 text-sm">E-mail da equipe para alertas<input className={field} name="recipient" type="email" defaultValue={config.resend_recipient} maxLength={150} /></label>
        <p className="text-sm text-slate-600">O remetente envia convites. O e-mail da equipe recebe alertas de transbordo.</p>
        <Button type="submit" label="Salvar Resend" variant="primary" isDisabled={busy} />
      </form>
      <form className={card} onSubmit={event => void save(event, 'openwa')}>
        <h4 className="text-lg font-semibold">OpenWA</h4>
        <p className="wrap-anywhere text-sm">Servidor: {config.openwa_url ?? 'Ainda não configurado'}</p>
        <p className="wrap-anywhere text-sm">Webhook: {config.openwa_webhook_url ?? 'Ainda não configurado'}</p>
        <label className="grid gap-1 text-sm">Chave OpenWA<input className={field} name="api_key" type="password" required autoComplete="new-password" maxLength={1000} placeholder={config.openwa_has_key ? 'Chave salva' : 'Informe a chave'} /></label>
        <p className="text-sm text-slate-600">A sessão e o servidor são vinculados na implantação. Consulte o status e o QR Code em WhatsApp.</p>
        <Button type="submit" label="Salvar OpenWA" variant="primary" isDisabled={busy} />
      </form>
    </section> : !error && <p>Carregando integrações…</p>}
  </section>;
}
