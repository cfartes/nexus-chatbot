'use client';

import { Button } from '@astryxdesign/core/Button';
import { Dialog, DialogHeader } from '@astryxdesign/core/Dialog';
import type { FormEvent, ReactNode } from 'react';

export const registrationField = 'w-full rounded-lg border border-slate-300 px-3 py-2';

export function RegistrationDialog({ title, submitLabel, busy, error, onClose, onSubmit, children, width = '36rem', submitDisabled }: {
  title: string; submitLabel: string; busy: boolean; error: string; onClose: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void; children: ReactNode; width?: string; submitDisabled?: boolean;
}) {
  function close(open: boolean) { if (!open && !busy) onClose(); }
  return <Dialog isOpen onOpenChange={close} purpose="form" width={width} maxHeight="90dvh" padding={0}>
    <section className="flex max-h-[90dvh] min-h-0 flex-col">
      <header className="shrink-0 px-5 pt-4 sm:px-6"><DialogHeader title={title} onOpenChange={close} /></header>
      <form className="flex min-h-0 flex-col" onSubmit={onSubmit}>
        <section className="grid min-h-0 gap-3 overflow-y-auto px-5 py-3 sm:px-6">{children}</section>
        <footer className="grid shrink-0 gap-2 border-t border-slate-200 px-5 py-3 sm:px-6">
          {error && <p role="alert" className="text-sm text-red-800">{error}</p>}
          <section className="flex flex-wrap justify-end gap-2">
            <Button label="Cancelar" type="button" isDisabled={busy} onClick={onClose} />
            <Button label={submitLabel} type="submit" variant="primary" isLoading={busy} isDisabled={submitDisabled} />
          </section>
        </footer>
      </form>
    </section>
  </Dialog>;
}
