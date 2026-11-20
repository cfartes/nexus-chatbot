'use client';

import { Button } from '@astryxdesign/core/Button';
import { Dialog, DialogHeader } from '@astryxdesign/core/Dialog';
import type { FormEvent, ReactNode } from 'react';

export const registrationField = 'w-full rounded-lg border border-slate-300 px-3 py-2';

export function RegistrationDialog({ title, submitLabel, busy, error, onClose, onSubmit, children }: {
  title: string; submitLabel: string; busy: boolean; error: string; onClose: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void; children: ReactNode;
}) {
  function close(open: boolean) { if (!open && !busy) onClose(); }
  return <Dialog isOpen onOpenChange={close} purpose="form" width="36rem">
    <DialogHeader title={title} onOpenChange={close} />
    <form className="grid gap-3" onSubmit={onSubmit}>
      {children}
      {error && <p role="alert" className="text-sm text-red-800">{error}</p>}
      <footer className="flex flex-wrap justify-end gap-2">
        <Button label="Cancelar" type="button" isDisabled={busy} onClick={onClose} />
        <Button label={submitLabel} type="submit" variant="primary" isLoading={busy} />
      </footer>
    </form>
  </Dialog>;
}
