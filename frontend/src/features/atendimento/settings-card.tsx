import type { ReactNode } from 'react';

export const settingsGrid = 'grid gap-4 md:grid-cols-2 lg:grid-cols-3';

export function SettingsCard({ title, children, action }: { title: string; children: ReactNode; action: ReactNode }) {
  return <section aria-label={title} className="grid min-w-0 grid-rows-[auto_minmax(0,1fr)_auto] gap-4 rounded-2xl border border-slate-200 bg-white p-5 md:h-[32rem]">
    <h3 className="text-lg font-semibold">{title}</h3>
    <section className="grid min-h-0 min-w-0 content-start gap-4 md:overflow-y-auto md:pr-1">{children}</section>
    <footer className="grid gap-2">{action}</footer>
  </section>;
}
