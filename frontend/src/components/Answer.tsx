import React from 'react';
import { CaretDown, CheckCircle, Circle, CircleNotch, DownloadSimple, FileText, Prohibit, ShieldCheck, ShieldWarning, XCircle } from '@phosphor-icons/react';

type Props = {
  result: any;
  plan: any;
  trust: any;
  proof?: any;
  proofError?: string | null;
  policy?: any;
  impact?: any;
  sensitivity?: any;
  loading?: boolean;
  onGeneratePDF: (type: string) => Promise<void> | void;
};

function formatNumber(value: any) {
  const n = typeof value === 'number' ? value : Number(String(value).replace(/,/g, ''));
  if (Number.isFinite(n)) return n.toLocaleString('en-IN', { maximumFractionDigits: 2 });
  return String(value ?? '');
}

const fmt = (v: any) => {
  const n = Number(v);
  return Number.isFinite(n) ? n.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : String(v ?? '');
};

const show = (v: any) => (v !== null && typeof v === 'object' ? JSON.stringify(v) : String(v));

function conversionNote(conversion: any, fallbackBasis?: string | null) {
  if (!conversion || !conversion.foreign_rows_in_scope) return null;
  const basis = conversion.basis || fallbackBasis || 'transaction_date';
  const cur = (conversion.foreign_currencies_in_scope || []).join(', ');
  return `${conversion.foreign_rows_in_scope} row(s) in ${cur} were converted using ${basis === 'latest' ? 'the latest exchange rate on file' : "the exchange rate on each transaction's date"}.`;
}

function shareAdvice(publishability?: string) {
  const p = String(publishability || '');
  if (!p) return null;
  if (p.includes('BLOCKED')) return 'Please do not share this outside your team yet.';
  if (p.includes('REVIEW')) return 'Have a colleague review this before you share it.';
  if (p.includes('READY') || p.includes('PUBLISH') || p.includes('OK')) return 'Safe to share.';
  return null;
}

function Steps({ plan, result, trust, proof }: { plan: any; result: any; trust: any; proof: any }) {
  const analyst = result?.analyst || {};
  const inspector = result?.inspector || {};
  const steps = [
    { label: 'Read your question', done: Boolean(plan), blocked: plan?.status === 'refused' },
    { label: 'Looked for problems in your data', done: Boolean(trust), blocked: false },
    { label: 'Worked out the answer', done: analyst.status === 'VERIFIED', blocked: Boolean(analyst.status) && analyst.status !== 'VERIFIED' },
    { label: 'Double-checked it a second way', done: inspector.status === 'VERIFIED', blocked: Boolean(inspector.status) && inspector.status !== 'VERIFIED' },
    { label: 'Saved the evidence', done: Boolean(proof?.proof_id), blocked: false },
  ];
  return (
    <ul className="space-y-2.5">
      {steps.map((s) => (
        <li key={s.label} className="flex items-center gap-3 text-sm text-[var(--text-secondary)]">
          {s.blocked ? <XCircle className="h-5 w-5 text-[var(--blocked)]" weight="regular" />
            : s.done ? <CheckCircle className="h-5 w-5 text-[var(--verified)]" weight="regular" />
            : <Circle className="h-5 w-5 text-[var(--text-muted)]" weight="regular" />}
          {s.label}
        </li>
      ))}
    </ul>
  );
}

const techTabs = [
  { id: 'checks', label: 'Checks' },
  { id: 'rows', label: 'Rows used' },
  { id: 'rules', label: 'Rules applied' },
  { id: 'impact', label: 'Cleaning impact' },
  { id: 'sensitivity', label: 'What if?' },
  { id: 'code', label: 'Code' },
];

function Technical({ plan, result, proof, proofError, policy, impact, sensitivity }: { plan: any; result: any; proof: any; proofError?: string | null; policy?: any; impact?: any; sensitivity?: any }) {
  const [tab, setTab] = React.useState('checks');
  const analyst = result?.analyst || {};
  const inspector = result?.inspector || {};
  const box = 'rounded-[12px] border border-[var(--border)] bg-[var(--inset)] p-4';
  return (
    <div className="mt-3">
      <div className="scrollbar-soft flex gap-1 overflow-x-auto" role="tablist">
        {techTabs.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={`focus-ring h-9 shrink-0 rounded-[10px] px-3 text-[13px] font-medium transition ${tab === t.id ? 'bg-[var(--surface-hover)] text-[var(--text)]' : 'text-[var(--text-muted)] hover:text-[var(--text)]'}`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="mt-3 text-[13px] leading-6 text-[var(--text-secondary)]">
        {tab === 'checks' && (
          <div className={`${box} space-y-1`}>
            <div>First calculation: <span className="font-mono text-[var(--text)]">{analyst.status || 'Pending'}</span></div>
            <div>Second calculation: <span className="font-mono text-[var(--text)]">{inspector.status || 'Pending'}</span></div>
            <div>Safety check on the code: <span className="font-mono text-[var(--text)]">{proof?.guard_passed === true ? 'Passed' : proof?.guard_passed === false ? 'Rejected' : proofError || 'Not run'}</span></div>
            <div>Proof ID: <span className="break-all font-mono text-[var(--text)]">{proof?.proof_id || 'Not issued'}</span></div>
          </div>
        )}
        {tab === 'rows' && (
          <div className={`${box} space-y-1`}>
            {Object.entries(analyst.stage_counts || {}).length
              ? Object.entries(analyst.stage_counts).map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-4"><span>{k.replace(/_/g, ' ')}</span><span className="font-mono text-[var(--text)]">{String(v)}</span></div>
                ))
              : <p>No row counts were returned.</p>}
            <div className="break-all pt-2 text-[var(--text-muted)]">Export: {analyst.source_rows_path || proof?.source_rows_path || 'none'}</div>
          </div>
        )}
        {tab === 'rules' && (
          <div className={`${box} space-y-1`}>
            {Object.entries({ ...(plan?.policy || {}), ...(policy?.conversion_basis ? { conversion_basis: policy.conversion_basis } : {}), ...(policy?.currency_map && Object.keys(policy.currency_map).length ? { currency_map: policy.currency_map } : {}) }).map(([k, v]) => (
              <div key={k} className="flex justify-between gap-4"><span>{k.replace(/_/g, ' ')}</span><span className="break-all text-right font-mono text-[var(--text)]">{show(v)}</span></div>
            ))}
          </div>
        )}
        {tab === 'impact' && (
          <div className={`${box} space-y-1`}>
            {!impact || impact.status === 'NOT_AVAILABLE' ? <p>{impact?.reason || 'Cleaning impact is not available for this answer.'}</p> : (
              <>
                {([
                  ['Total before any cleaning', impact.raw_total_before_cleaning],
                  ['Exact duplicate rows', impact.duplicate_effect],
                  ['Conflicting invoices', impact.conflict_effect],
                  ['Refunds', impact.refund_effect],
                ] as [string, any][]).map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-4"><span>{k}</span><span className="font-mono text-[var(--text)] mono-tabular">{fmt(v)}</span></div>
                ))}
                <div className="flex justify-between gap-4 border-t border-[var(--border)] pt-1"><span>Verified total ({impact.currency})</span><span className="font-mono text-[var(--text)] mono-tabular">{fmt(impact.verified_total)}</span></div>
                <div className="pt-2">Adds up to the verified total: <span className="font-mono text-[var(--text)]">{impact.reconciles ? 'Yes' : 'No'}</span></div>
                <div>Rows left out for a missing date or amount: <span className="text-[var(--text)]">{impact.missing_date_effect}</span></div>
                <div>Rows with no exchange rate: <span className="text-[var(--text)]">{impact.unsupported_currency_effect}</span></div>
                <div>Biggest risk: <span className="text-[var(--text)]">{impact.largest_monetary_risk}</span></div>
                <div>Suggested cleanup: <span className="text-[var(--text)]">{impact.minimum_cleanup_recommendation}</span></div>
              </>
            )}
          </div>
        )}
        {tab === 'sensitivity' && (
          <div className={`${box} space-y-3`}>
            {!sensitivity ? <p>No what-if analysis is available for this answer.</p> : (
              <>
                <div>Could the answer change if we read things differently? <span className="font-mono text-[var(--text)]">{sensitivity.materiality}</span> (worst case {sensitivity.worst_case_percent}).</div>
                <div className="scrollbar-soft overflow-x-auto">
                  <table className="w-full min-w-[420px] text-left">
                    <thead className="text-[var(--text-muted)]"><tr><th className="py-1 pr-3 font-medium">If…</th><th className="py-1 pr-3 text-right font-medium">Answer</th><th className="py-1 text-right font-medium">Change</th></tr></thead>
                    <tbody>
                      {(sensitivity.scenarios || []).map((sc: any) => (
                        <tr key={sc.name} className="border-t border-[var(--border)] align-top">
                          <td className="py-1.5 pr-3">{sc.description}<div className="text-[12px] text-[var(--text-muted)]">{sc.assessment}</div></td>
                          <td className="py-1.5 pr-3 text-right font-mono text-[var(--text)] mono-tabular">{sc.result !== null && sc.result !== undefined ? fmt(sc.result) : 'n/a'}</td>
                          <td className="py-1.5 text-right font-mono mono-tabular">{sc.percent_difference || 'n/a'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {sensitivity.explanation && <p>{sensitivity.explanation}</p>}
              </>
            )}
          </div>
        )}
        {tab === 'code' && (
          <pre className="scrollbar-soft max-h-[360px] overflow-auto rounded-[12px] border border-[var(--border)] bg-[var(--inset)] p-4 text-[12px] leading-5"><code>{analyst.generated_code || '# No code available for this answer.'}</code></pre>
        )}
      </div>
    </div>
  );
}

export function Answer({ result, plan, trust, proof, proofError, policy, impact, sensitivity, loading = false, onGeneratePDF }: Props) {
  const [reportLoading, setReportLoading] = React.useState(false);

  if (loading) {
    return (
      <div className="panel p-6" aria-busy="true" aria-live="polite">
        <div className="flex items-center gap-3 text-sm text-[var(--text-secondary)]">
          <CircleNotch className="h-5 w-5 animate-spin text-[var(--accent)]" weight="regular" />
          Working on it. This usually takes a few seconds.
        </div>
        <div className="mt-5 space-y-3">
          <span className="skeleton !block !h-10 !w-56" />
          <span className="skeleton !block !w-full max-w-md" />
        </div>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="panel-flat border-dashed p-8 text-center">
        <p className="text-sm text-[var(--text-muted)]">Your answer will appear here once you ask a question.</p>
      </div>
    );
  }

  const analyst = result.analyst || {};
  const inspector = result.inspector || {};
  const verified = analyst.status === 'VERIFIED' && inspector.status === 'VERIFIED';
  const refused = plan?.status === 'refused' || analyst.status === 'REFUSED';
  const canDownloadVerified = verified && trust?.trust_decision !== 'REFUSED' && trust?.trust_decision !== 'BLOCKED';
  const withNote = trust?.trust_decision === 'VERIFIED_WITH_POLICY';
  const reasons: string[] = (trust?.reasons || []).filter(Boolean);
  const advice = shareAdvice(trust?.publishability);

  const tone = verified
    ? { color: 'var(--verified)', Icon: ShieldCheck, badge: withNote ? 'Confirmed, with a note' : 'Confirmed' }
    : refused
      ? { color: 'var(--blocked)', Icon: Prohibit, badge: 'We can not answer this' }
      : { color: 'var(--policy)', Icon: ShieldWarning, badge: 'Needs your review' };

  async function download() {
    const type = verified ? 'verified' : refused ? 'refusal' : 'review';
    setReportLoading(true);
    try { await onGeneratePDF(type); } finally { setReportLoading(false); }
  }

  return (
    <div className="space-y-4" aria-live="polite">
      <section className="panel overflow-hidden">
        <div className="p-6">
          <div className="inline-flex items-center gap-2 text-sm font-medium" style={{ color: tone.color }}>
            <tone.Icon className="h-5 w-5" weight="regular" />
            {tone.badge}
          </div>

          {verified ? (
            <>
              <div className="mt-3 flex flex-wrap items-baseline gap-3">
                <span className="text-5xl font-semibold tracking-[-0.04em] text-[var(--text)] mono-tabular">{formatNumber(analyst.result)}</span>
                <span className="text-sm text-[var(--text-muted)]">{analyst.currency || 'INR'}</span>
              </div>
              <p className="mt-3 max-w-[60ch] text-[15px] leading-6 text-[var(--text-secondary)]">
                We worked this out two different ways and both gave the same number.
              </p>
              {conversionNote(analyst.conversion, policy?.conversion_basis) && (
                <p className="mt-2 max-w-[60ch] text-[13px] leading-5 text-[var(--text-muted)]">{conversionNote(analyst.conversion, policy?.conversion_basis)}</p>
              )}
            </>
          ) : refused ? (
            <>
              <h3 className="mt-3 text-xl font-semibold text-[var(--text)]">Sorry, we can not answer that question.</h3>
              <p className="mt-2 max-w-[60ch] text-[15px] leading-6 text-[var(--text-secondary)]">
                {plan?.refusal?.reason || 'It is outside what we can check reliably. Try asking it a different way.'}
              </p>
            </>
          ) : (
            <>
              <h3 className="mt-3 text-xl font-semibold text-[var(--text)]">We are not sure enough to show a number.</h3>
              <p className="mt-2 max-w-[60ch] text-[15px] leading-6 text-[var(--text-secondary)]">
                {analyst.reason || inspector.reason || 'The two ways of calculating did not agree, so we are holding the number back instead of risking a wrong one.'}
              </p>
            </>
          )}

          {reasons.length > 0 && (
            <div className="mt-5">
              <div className="text-sm font-medium text-[var(--text)]">Good to know</div>
              <ul className="mt-2 space-y-1.5 pl-5 text-sm leading-6 text-[var(--text-secondary)]">
                {reasons.map((r, i) => <li key={`${r}-${i}`} className="list-disc">{r}</li>)}
              </ul>
            </div>
          )}

          {trust?.contradiction?.status === 'CONTRADICTION_DETECTED' && (
            <div className="mt-5 rounded-[12px] border border-[var(--policy)] bg-[var(--policy-soft)] p-4 text-sm leading-6 text-[var(--text-secondary)]">
              <div className="font-medium text-[var(--text)]">This does not match your summary sheet</div>
              Your summary reports {fmt(trust.contradiction.summary_reported_result)}, but your sales rows add up to {fmt(trust.contradiction.compared_verified_result ?? trust.contradiction.raw_verified_result)} ({trust.contradiction.percentage_difference} apart, {trust.contradiction.compared_scope || 'as provided'}).
            </div>
          )}

          {advice && <p className="mt-4 text-sm font-medium text-[var(--text)]">{advice}</p>}

          {verified && proofError && (
            <p className="mt-3 text-[13px] text-[var(--policy)]">The evidence file could not be created, so the verified report may not be available.</p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-3 border-t border-[var(--border)] bg-[var(--inset)] px-6 py-4">
          <button onClick={download} disabled={reportLoading || (verified && !canDownloadVerified)} className="btn btn-primary focus-ring">
            {reportLoading ? <CircleNotch className="h-4 w-4 animate-spin" weight="regular" /> : verified ? <DownloadSimple className="h-4 w-4" weight="regular" /> : <FileText className="h-4 w-4" weight="regular" />}
            {reportLoading ? 'Preparing' : verified ? 'Download report' : refused ? 'Download explanation' : 'Download review report'}
          </button>
          <span className="text-[13px] text-[var(--text-muted)]">Saves a PDF you can keep or share.</span>
        </div>
      </section>

      <details className="panel-flat p-5">
        <summary className="focus-ring flex items-center justify-between gap-3 rounded-[8px] text-sm font-medium text-[var(--text)]">
          How did we get this?
          <CaretDown className="caret h-4 w-4 text-[var(--text-muted)]" weight="regular" />
        </summary>
        <div className="mt-4">
          <Steps plan={plan} result={result} trust={trust} proof={proof} />
          <details className="mt-5 border-t border-[var(--border)] pt-4">
            <summary className="focus-ring flex items-center justify-between gap-3 rounded-[8px] text-[13px] text-[var(--text-muted)]">
              Technical details, for auditors
              <CaretDown className="caret h-4 w-4" weight="regular" />
            </summary>
            <Technical plan={plan} result={result} proof={proof} proofError={proofError} policy={policy} impact={impact ?? proof?.impact} sensitivity={sensitivity ?? proof?.sensitivity} />
          </details>
        </div>
      </details>
    </div>
  );
}
