'use client';

import { Button } from '@astryxdesign/core/Button';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api, errorMessage } from './api';

type Notice = { id: string; conversation_id: string };

export function TransferNotices({ revision, openConversation, activeConversation }: {
  revision: number;
  openConversation: (id: string) => void;
  activeConversation?: string;
}) {
  const [items, setItems] = useState<Notice[]>([]);
  const [permission, setPermission] = useState<NotificationPermission>();
  const [error, setError] = useState('');
  const system = useRef(new Map<string, Notification>());
  const acknowledging = useRef(new Set<string>());

  useEffect(() => {
    if ('Notification' in window) setPermission(Notification.permission);
    const notifications = system.current;
    return () => { notifications.forEach(notification => notification.close()); notifications.clear(); };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    api<Notice[]>('/conversations/transfer-notices', { signal: controller.signal }).then(notices => {
      if (!controller.signal.aborted) { setItems(notices); setError(''); }
    }).catch(failure => {
      if (!controller.signal.aborted) setError(errorMessage(failure));
    });
    return () => controller.abort();
  }, [revision]);

  const dismiss = useCallback(async (id: string) => {
    if (acknowledging.current.has(id)) return;
    acknowledging.current.add(id);
    try {
      await api(`/conversations/transfer-notices/${id}`, { method: 'DELETE' });
      setItems(current => current.filter(item => item.id !== id));
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      acknowledging.current.delete(id);
    }
  }, []);

  useEffect(() => {
    for (const item of items) {
      if (item.conversation_id === activeConversation) void dismiss(item.id);
    }
  }, [activeConversation, dismiss, items]);

  useEffect(() => {
    for (const [id, notification] of system.current) {
      if (!items.some(item => item.id === id)) {
        notification.close();
        system.current.delete(id);
      }
    }
    if (permission !== 'granted') return;
    for (const item of items) {
      if (item.conversation_id === activeConversation || system.current.has(item.id)) continue;
      try {
        const notification = new Notification('Nexus Atende', {
          body: 'Uma conversa foi transferida para você.',
          tag: `nexus-transfer-${item.id}`,
          requireInteraction: true,
        });
        notification.onclick = () => { window.focus(); openConversation(item.conversation_id); };
        system.current.set(item.id, notification);
      } catch (failure) {
        if (!(failure instanceof TypeError || failure instanceof DOMException)) throw failure;
      }
    }
  }, [activeConversation, items, openConversation, permission]);

  return <>
    {permission === 'default' && <Button label="Ativar notificações do sistema" onClick={() => {
      void Notification.requestPermission().then(setPermission).catch(() => setPermission('denied'));
    }} />}
    {(items.length > 0 || error) && <aside aria-label="Conversas transferidas" className="fixed inset-x-4 bottom-4 z-20 grid max-h-[60vh] gap-2 overflow-auto text-slate-900 sm:left-auto sm:w-96">
      {error && <p role="alert" className="rounded-xl border border-red-200 bg-white p-3 text-sm text-red-800">Avisos de transferência · {error}</p>}
      {items.map(item => <section key={item.id} className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-slate-300 bg-white p-4 shadow-md">
        <p role="status" className="self-center text-sm font-medium">Uma conversa foi transferida para você.</p>
        <Button label="×" aria-label="Fechar aviso" onClick={() => void dismiss(item.id)} />
        <Button label="Abrir conversa" variant="primary" onClick={() => openConversation(item.conversation_id)} />
      </section>)}
    </aside>}
  </>;
}
