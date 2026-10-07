import React from 'react';
import { Ban, CheckCircle2, FileWarning, Scale, ShieldAlert } from 'lucide-react';

function decisionTone(decision: string) {
  if (decision === 'VERIFIED') return { color: 'var(--verified)', bg: 'var(--verified-soft)', Icon: CheckCircle2, label: 'Verified' };
  if (decision === 'VERIFIED_WITH_POLICY') return { color: 'var(--policy)', bg: 'var(--policy-soft)', Icon: FileWarning, label: 'Policy review' };
  if (decision === 'REFUSED') return { color: 'var(--blocked)', bg: 'var(--blocked-soft)', Icon: Ban, label: 'Refused' };
  if (decision === 'AWAITING_EVIDENCE') return { color: 'var(--text-muted)', bg: 'rgba(255,255,255,0.03)', Icon: Scale, label: 'Awaiting evidence' };
  return { color: 'var(--blocked)', bg: 'var(--blocked-soft)', Icon: ShieldAlert, label: 'Blocked' };
}

export function TrustDecisionCard({ trust, loading = false }: { trust: any; loading?: boolean }) {
  const decision = trust?.trust_decision || 'AWAITING_EVIDENCE';
  const pub = trust?.publishability || 'Run an analysis to receive a publishability recommendation.';
  const tone = decisionTone(decision);
  const Icon = tone.Icon;

  return (
    <aside className="panel sticky top-24 overflow-hidden">
      <div className="border-b border-[var(--border)] p-4">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-[13px] font-semibold text-[var(--text)]">
            <Scale className="h-4 w-4 text-[var(--info)]" strokeWidth={1.8} />
            Trust & Evidence
          </div>
          <span className="rounded-full border border-[var(--border)] px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-[var(--text-muted)]">
            Local
          </span>
        </div>
      </div>

      <div className="p-4">
        <div className="rounded-[18px] border p-4" style={{ borderColor: `${tone.color}55`, background: tone.bg }}>
          <div className="flex items-start gap-3">
            <div className="mt-0.5 rounded-full border p-2" style={{ color: tone.color, borderColor: `${tone.color}44`, background: 'rgba(0,0,0,0.16)' }}>
              <Icon className="h-4 w-4" strokeWidth={1.8} />
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-muted)]">Trust decision</div>
              <div className="mt-1 font-mono text-lg font-semibold mono-tabular" style={{ color: tone.color }}>
                {loading ? 'EVALUATING' : tone.label}
              </div>
              <div className="mt-1 break-words font-mono text-[11px] text-[var(--text-secondary)]">{decision}</div>
            </div>
          </div>
        </div>

        <div className="mt-4 rounded-[18px] border border-[var(--border)] bg-black/18 p-4">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-muted)]">Publishability</div>
          <div className="mt-2 break-words font-mono text-[12px] leading-5 text-[var(--text)]">{pub}</div>
        </div>

        <div className="mt-4 space-y-2">
          {(trust?.reasons?.length ? trust.reasons : ['No trust decision has been produced yet.']).map((reason: string, i: number) => (
            <div key={`${reason}-${i}`} className="rounded-[14px] border border-[var(--border)] bg-black/16 px-3 py-2 text-[11px] leading-4 text-[var(--text-secondary)]">
              {reason}
            </div>
          ))}
        </div>

        {trust?.recommendation && (
          <div className="mt-4 border-t border-[var(--border)] pt-4 text-[12px] leading-5 text-[var(--text-muted)]">
            {trust.recommendation}
          </div>
        )}
      </div>
    </aside>
  );
}
