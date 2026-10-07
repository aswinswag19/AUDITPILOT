import React from 'react';
import { CheckCircle, ShieldCheck, ShieldWarning, WarningCircle } from '@phosphor-icons/react';

const money = (v: any) => {
  const n = Number(v);
  return Number.isFinite(n) ? n.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '—';
};

/** Compare / rank questions: one independently verified figure per entity (backend `grouped` payload). */
export function GroupedAnswer({ grouped, policy, plan }: { grouped: any; policy?: any; plan?: any }) {
  const rows: any[] = grouped?.ranking || [];
  const all = Boolean(grouped?.all_verified);
  const tone = all ? { color: 'var(--verified)', Icon: ShieldCheck, badge: 'Every figure confirmed' }
                   : { color: 'var(--policy)', Icon: ShieldWarning, badge: 'Needs your review' };
  const top = rows.find((r) => r.verified);
  const basis = policy?.conversion_basis;

  return (
    <div className="space-y-4" aria-live="polite">
      <section className="panel overflow-hidden">
        <div className="p-6">
          <div className="inline-flex items-center gap-2 text-sm font-medium" style={{ color: tone.color }}>
            <tone.Icon className="h-5 w-5" weight="regular" />
            {tone.badge}
          </div>
          {top && (
            <h3 className="mt-3 text-xl font-semibold text-[var(--text)]">
              {plan?.intent === 'compare' ? 'Highest:' : 'Top:'} {top.entity}
              <span className="ml-3 text-[var(--text-muted)] mono-tabular">{money(top.analyst_result)} {grouped.currency}</span>
            </h3>
          )}
          <p className="mt-2 max-w-[60ch] text-[15px] leading-6 text-[var(--text-secondary)]">
            Each figure was worked out two different ways. {all ? 'Both ways agreed for every one.' : 'Figures marked "Not confirmed" are held back until the problem is fixed.'}
          </p>

          <div className="scrollbar-soft mt-5 overflow-x-auto rounded-[12px] border border-[var(--border)]">
            <table className="w-full min-w-[460px] text-left text-sm">
              <thead className="bg-[var(--inset)] text-[13px] text-[var(--text-muted)]">
                <tr>
                  <th className="px-4 py-2.5 font-medium">#</th>
                  <th className="px-4 py-2.5 font-medium">Name</th>
                  <th className="px-4 py-2.5 text-right font-medium">Total ({grouped.currency})</th>
                  <th className="px-4 py-2.5 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.entity} className="border-t border-[var(--border)] align-top">
                    <td className="px-4 py-3 text-[var(--text-muted)] mono-tabular">{r.rank}</td>
                    <td className="px-4 py-3 font-medium text-[var(--text)]">{r.entity}</td>
                    <td className="px-4 py-3 text-right font-mono text-[var(--text)] mono-tabular">{r.verified ? money(r.analyst_result) : '—'}</td>
                    <td className="px-4 py-3">
                      {r.verified
                        ? <span className="inline-flex items-center gap-1.5 text-[var(--verified)]"><CheckCircle className="h-4 w-4" weight="regular" />Confirmed</span>
                        : <span className="inline-flex items-center gap-1.5 text-[var(--policy)]"><WarningCircle className="h-4 w-4" weight="regular" />Not confirmed</span>}
                      {r.unsupported_rows > 0 && <div className="mt-1 text-[12px] text-[var(--text-muted)]">{r.unsupported_rows} row(s) left out: no exchange rate.</div>}
                      {r.conflicting_invoices?.length > 0 && <div className="mt-1 text-[12px] text-[var(--text-muted)]">Conflicting invoice(s) left out: {r.conflicting_invoices.join(', ')}.</div>}
                      {!r.verified && r.reason && <div className="mt-1 text-[12px] text-[var(--text-muted)]">{r.reason}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {basis && (
            <p className="mt-4 text-[13px] text-[var(--text-muted)]">
              Other currencies were converted at {basis === 'latest' ? 'the latest rate on file' : "the rate on each transaction's date"}.
            </p>
          )}
        </div>
        <div className="border-t border-[var(--border)] bg-[var(--inset)] px-6 py-4 text-[13px] text-[var(--text-muted)]">
          A saved proof and PDF report are made for a single figure. Ask about one name to get them.
        </div>
      </section>
    </div>
  );
}
