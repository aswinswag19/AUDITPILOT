import React from 'react';
import { Gauge, ShieldCheck } from 'lucide-react';

export function QualityScore({ profile }: { profile: any }) {
  const score = Number(profile?.quality_score ?? 0);
  const hasProfile = Boolean(profile);
  const tone = score >= 90 ? 'verified' : score >= 75 ? 'policy' : 'blocked';
  const toneColor = tone === 'verified' ? 'var(--verified)' : tone === 'policy' ? 'var(--policy)' : 'var(--blocked)';
  const deductions = profile?.deductions || [];

  return (
    <section className="panel-flat p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-[13px] font-semibold text-[var(--text)]">
            <Gauge className="h-4 w-4 text-[var(--info)]" strokeWidth={1.8} />
            Inspection Instrument
          </div>
          <p className="mt-1 text-[12px] text-[var(--text-muted)]">Quality score from profiler deductions.</p>
        </div>
        <div className="text-right">
          <div className="font-mono text-3xl leading-none mono-tabular" style={{ color: toneColor }}>
            {hasProfile ? score.toFixed(1) : '—'}
          </div>
          <div className="mt-1 text-[10px] uppercase tracking-[0.18em] text-[var(--text-muted)]">Score</div>
        </div>
      </div>

      <div className="mt-5 h-2 overflow-hidden rounded-full border border-[var(--border)] bg-black/30" aria-hidden="true">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${hasProfile ? Math.max(0, Math.min(100, score)) : 0}%`, background: toneColor }}
        />
      </div>

      <div className="mt-4 space-y-2">
        {deductions.length > 0 ? (
          deductions.slice(0, 4).map((deduction: string, idx: number) => (
            <div key={`${deduction}-${idx}`} className="rounded-[14px] border border-[var(--border)] bg-black/18 px-3 py-2 text-[11px] leading-4 text-[var(--text-secondary)]">
              {deduction}
            </div>
          ))
        ) : (
          <div className="flex items-start gap-2 rounded-[14px] border border-[var(--verified)]/22 bg-[var(--verified-soft)] px-3 py-2">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-[var(--verified)]" strokeWidth={1.8} />
            <span className="text-[11px] leading-4 text-[var(--text-secondary)]">
              {hasProfile ? 'No profiler deductions were returned.' : 'Upload or load a dataset to run inspection.'}
            </span>
          </div>
        )}
      </div>
    </section>
  );
}
