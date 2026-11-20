import type { ReactNode } from 'react';

export const settingsGrid = 'grid gap-4 md:grid-cols-2 lg:grid-cols-3';

export type CardState = 'missing' | 'warning' | 'ready' | 'loading';

const indicators = {
  missing: { symbol: '×', label: 'Não configurado', color: 'border-red-200 bg-red-50 text-red-800' },
  warning: { symbol: '!', label: 'Atenção', color: 'border-orange-200 bg-orange-50 text-orange-900' },
  ready: { symbol: '✓', label: 'Configurado', color: 'border-green-200 bg-green-50 text-green-800' },
  loading: { symbol: '·', label: 'Consultando', color: 'border-slate-200 bg-slate-50 text-slate-600' },
};

export function SettingsCard({ title, state, detail, children, action }: {
  title: string; state: CardState; detail?: string; children: ReactNode; action: ReactNode;
}) {
  const indicator = indicators[state];
  const status = detail ? `${indicator.label} · ${detail}` : indicator.label;
  return <section aria-label={title} className="grid min-w-0 grid-rows-[auto_minmax(0,1fr)_auto] gap-4 rounded-2xl border border-slate-200 bg-white p-5 md:h-[32rem]">
    <header className="flex items-start justify-between gap-3">
      <h3 className="min-w-0 text-lg font-semibold">{title}</h3>
      <output aria-label={status} title={status} className={`inline-grid size-7 shrink-0 place-items-center rounded-full border text-lg leading-none font-semibold ${indicator.color}`}>
        <i aria-hidden="true" className="not-italic">{indicator.symbol}</i>
      </output>
    </header>
    <section className="grid min-h-0 min-w-0 content-start gap-4 md:overflow-y-auto md:pr-1">{children}</section>
    <footer className="grid gap-2">{action}</footer>
  </section>;
}
