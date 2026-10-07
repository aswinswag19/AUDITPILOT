import React from 'react';
import { AlertOctagon, CheckCircle2, Code2, Download, FileCode2, FileText, GitBranch, Loader2, Rows3, Scale, ShieldCheck, SlidersHorizontal, Table2 } from 'lucide-react';

type ProofTabsProps = {
  result: any;
  plan: any;
  trust: any;
  proof?: any;
  proofError?: string | null;
  onGeneratePDF: (type: string) => Promise<void> | void;
};

const tabs = [
  { id: 'proof', label: 'Proof', Icon: ShieldCheck },
  { id: 'code', label: 'Code', Icon: Code2 },
  { id: 'source', label: 'Source Rows', Icon: Rows3 },
  { id: 'policy', label: 'Policy', Icon: Scale },
  { id: 'impact', label: 'Impact', Icon: Table2 },
  { id: 'sensitivity', label: 'Sensitivity', Icon: SlidersHorizontal },
  { id: 'contradictions', label: 'Contradictions', Icon: AlertOctagon },
];

function statusColor(status: string) {
  if (status === 'VERIFIED') return 'var(--verified)';
  if (status === 'REFUSED' || status?.includes('BLOCK')) return 'var(--blocked)';
  return 'var(--policy)';
}

function EvidencePipeline({ plan, result, trust, proof }: { plan: any; result: any; trust: any; proof: any }) {
  const analyst = result?.analyst || {};
  const inspector = result?.inspector || {};
  const steps = [
    { label: 'Inspect', done: Boolean(result), blocked: false },
    { label: 'Detect Risks', done: Boolean(trust), blocked: false },
    { label: 'Apply Policy', done: Boolean(plan), blocked: plan?.status === 'refused' },
    { label: 'Calculate', done: analyst.status === 'VERIFIED', blocked: analyst.status && analyst.status !== 'VERIFIED' },
    { label: 'Verify', done: inspector.status === 'VERIFIED', blocked: inspector.status && inspector.status !== 'VERIFIED' },
    { label: 'Prove', done: Boolean(proof?.proof_id), blocked: Boolean(proof?.error) },
  ];

  return (
    <div className="panel-flat p-4">
      <div className="mb-3 flex items-center gap-2 text-[13px] font-semibold text-[var(--text)]">
        <GitBranch className="h-4 w-4 text-[var(--info)]" strokeWidth={1.8} />
        Evidence pipeline
      </div>
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-6">
        {steps.map((step) => (
          <div key={step.label} className="rounded-[14px] border border-[var(--border)] bg-black/18 p-3">
            <div className="mb-3 h-1.5 overflow-hidden rounded-full bg-black/30">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{ width: step.done || step.blocked ? '100%' : '18%', background: step.blocked ? 'var(--blocked)' : step.done ? 'var(--verified)' : 'var(--border-strong)' }}
              />
            </div>
            <div className="text-[11px] font-medium text-[var(--text-secondary)]">{step.label}</div>
            <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.12em]" style={{ color: step.blocked ? 'var(--blocked)' : step.done ? 'var(--verified)' : 'var(--text-muted)' }}>
              {step.blocked ? 'Stopped' : step.done ? 'Complete' : 'Pending'}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function EmptyEvidence() {
  return (
    <section className="panel p-8 text-center">
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border border-[var(--border)] bg-black/20">
        <FileText className="h-5 w-5 text-[var(--info)]" strokeWidth={1.8} />
      </div>
      <h2 className="mt-4 text-xl font-semibold tracking-[-0.02em] text-[var(--text)]">No evidence bundle yet</h2>
      <p className="mx-auto mt-2 max-w-[52ch] text-sm leading-6 text-[var(--text-muted)]">
        Ask an audit question to create a plan, run both engines, and display only evidence-backed output.
      </p>
    </section>
  );
}

export function ProofTabs({ result, plan, trust, proof, proofError, onGeneratePDF }: ProofTabsProps) {
  const [activeTab, setActiveTab] = React.useState('proof');
  const [reportLoading, setReportLoading] = React.useState<string | null>(null);

  if (!result) return <EmptyEvidence />;

  const analyst = result.analyst || {};
  const inspector = result.inspector || {};
  const isVerified = analyst.status === 'VERIFIED' && inspector.status === 'VERIFIED';
  const isRefused = plan?.status === 'refused' || analyst.status === 'REFUSED';
  const isBlocked = !isVerified && !isRefused;
  const canDownloadVerified = isVerified && trust?.trust_decision !== 'REFUSED' && trust?.trust_decision !== 'BLOCKED';

  async function generate(type: string) {
    setReportLoading(type);
    try {
      await onGeneratePDF(type);
    } finally {
      setReportLoading(null);
    }
  }

  return (
    <div className="space-y-5">
      <section className="panel overflow-hidden">
        <div className="border-b border-[var(--border)] p-5 md:p-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-muted)]">Verified answer</div>
              {isRefused ? (
                <div className="mt-2 text-xl font-semibold text-[var(--blocked)]">Question refused</div>
              ) : isVerified ? (
                <div className="mt-2 flex flex-wrap items-baseline gap-3">
                  <span className="font-mono text-4xl font-semibold tracking-[-0.04em] text-[var(--verified)] mono-tabular md:text-5xl">{analyst.result}</span>
                  <span className="font-mono text-sm text-[var(--text-muted)]">{analyst.currency || 'INR'}</span>
                </div>
              ) : (
                <div className="mt-2 text-xl font-semibold text-[var(--policy)]">Final number withheld</div>
              )}
              <p className="mt-3 max-w-[64ch] text-sm leading-6 text-[var(--text-secondary)]">
                {isRefused
                  ? plan?.refusal?.reason || 'The planner refused this request under the current policy.'
                  : isBlocked
                    ? 'The interface does not present blocked or mismatched calculations as verified results.'
                    : 'Displayed only after Pandas Analyst and DuckDB Inspector both returned verified status.'}
              </p>
            </div>

            <div className="grid min-w-[260px] gap-2 text-[12px]">
              {[
                ['Pandas Analyst', analyst.status || 'PENDING'],
                ['DuckDB Inspector', inspector.status || 'PENDING'],
                ['Trust Engine', trust?.trust_decision || 'PENDING'],
              ].map(([label, value]) => (
                <div key={label} className="flex items-center justify-between gap-4 rounded-[14px] border border-[var(--border)] bg-black/18 px-3 py-2">
                  <span className="text-[var(--text-muted)]">{label}</span>
                  <span className="font-mono mono-tabular" style={{ color: statusColor(String(value)) }}>{value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 divide-y divide-[var(--border)] lg:grid-cols-3 lg:divide-x lg:divide-y-0">
          <div className="p-5">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-muted)]">Plan intent</div>
            <div className="mt-2 font-mono text-sm text-[var(--text)]">{plan?.intent || 'N/A'}</div>
          </div>
          <div className="p-5">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-muted)]">Scoped rows</div>
            <div className="mt-2 font-mono text-sm text-[var(--text)] mono-tabular">{analyst.stage_counts?.final_query_rows ?? 'N/A'}</div>
          </div>
          <div className="p-5">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-muted)]">Proof ID</div>
            <div className="mt-2 font-mono text-sm text-[var(--text)]">{proof?.proof_id || 'Pending guard pass'}</div>
          </div>
        </div>
      </section>

      <EvidencePipeline plan={plan} result={result} trust={trust} proof={proof} />

      <section className="panel overflow-hidden">
        <div className="scrollbar-soft flex gap-1 overflow-x-auto border-b border-[var(--border)] p-2">
          {tabs.map(({ id, label, Icon }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={`focus-ring inline-flex h-10 shrink-0 items-center gap-2 rounded-[12px] px-3 text-[12px] font-medium transition active:translate-y-px ${
                activeTab === id ? 'bg-[var(--surface-hover)] text-[var(--text)]' : 'text-[var(--text-muted)] hover:bg-[var(--surface-panel)] hover:text-[var(--text-secondary)]'
              }`}
            >
              <Icon className="h-3.5 w-3.5" strokeWidth={1.8} />
              {label}
            </button>
          ))}
        </div>

        <div className="p-5 md:p-6">
          {activeTab === 'proof' && (
            <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
              <div className="rounded-[18px] border border-[var(--border)] bg-black/18 p-4">
                <div className="flex items-center gap-2 text-sm font-semibold text-[var(--text)]">
                  <ShieldCheck className="h-4 w-4 text-[var(--verified)]" strokeWidth={1.8} />
                  Proof bundle status
                </div>
                <div className="mt-4 grid gap-3 text-[12px] text-[var(--text-secondary)]">
                  <div>AST guard: <span className="font-mono text-[var(--text)]">{proof?.guard_passed === false ? 'Rejected' : proof?.guard_passed === true ? 'Passed' : proofError || 'Awaiting proof endpoint'}</span></div>
                  <div>Proof script path: <span className="font-mono text-[var(--text)]">{proof?.proof_script_path || 'N/A'}</span></div>
                  <div>Source rows path: <span className="font-mono text-[var(--text)]">{proof?.source_rows_path || analyst.source_rows_path || 'N/A'}</span></div>
                </div>
              </div>
              <div className="rounded-[18px] border border-[var(--border)] bg-black/18 p-4">
                <div className="text-sm font-semibold text-[var(--text)]">Official report</div>
                <p className="mt-2 text-[12px] leading-5 text-[var(--text-muted)]">PDFs are generated by the FastAPI backend. Blocked and refused states are labeled accordingly.</p>
                <div className="mt-4 grid gap-2">
                  <button
                    onClick={() => generate('verified')}
                    disabled={!canDownloadVerified || Boolean(reportLoading)}
                    className="focus-ring inline-flex h-10 items-center justify-center gap-2 rounded-[12px] bg-[var(--info)] px-3 text-[12px] font-semibold text-[#071016] transition hover:brightness-110 disabled:bg-[var(--surface-hover)] disabled:text-[var(--text-muted)] active:translate-y-px"
                  >
                    {reportLoading === 'verified' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
                    {reportLoading === 'verified' ? 'Generating report' : 'Verified PDF'}
                  </button>
                  <button
                    onClick={() => generate(isRefused ? 'refusal' : 'review')}
                    disabled={Boolean(reportLoading)}
                    className="focus-ring inline-flex h-10 items-center justify-center gap-2 rounded-[12px] border border-[var(--border-strong)] bg-[var(--surface-panel)] px-3 text-[12px] font-medium text-[var(--text)] transition hover:bg-[var(--surface-hover)] active:translate-y-px"
                  >
                    {reportLoading && reportLoading !== 'verified' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileText className="h-3.5 w-3.5" />}
                    {reportLoading && reportLoading !== 'verified' ? 'Generating report' : isRefused ? 'Refusal PDF' : 'Review PDF'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'code' && (
            <div className="overflow-hidden rounded-[18px] border border-[var(--border)] bg-[#06080c]">
              <div className="flex items-center gap-2 border-b border-[var(--border)] px-4 py-3 text-[12px] text-[var(--text-muted)]">
                <FileCode2 className="h-4 w-4 text-[var(--info)]" strokeWidth={1.8} />
                Generated proof script
              </div>
              <pre className="scrollbar-soft max-h-[420px] overflow-auto p-4 text-[12px] leading-5 text-[var(--text-secondary)]"><code>{analyst.generated_code || '# No generated code available for this response.'}</code></pre>
            </div>
          )}

          {activeTab === 'source' && (
            <div className="grid gap-4 md:grid-cols-2">
              <div className="rounded-[18px] border border-[var(--border)] bg-black/18 p-4">
                <div className="text-sm font-semibold text-[var(--text)]">Source row export</div>
                <div className="mt-3 break-words font-mono text-[12px] leading-5 text-[var(--text-secondary)]">{analyst.source_rows_path || 'No source row export returned.'}</div>
              </div>
              <div className="rounded-[18px] border border-[var(--border)] bg-black/18 p-4">
                <div className="text-sm font-semibold text-[var(--text)]">Stage counts</div>
                <div className="mt-3 space-y-2">
                  {Object.entries(analyst.stage_counts || {}).length ? Object.entries(analyst.stage_counts).map(([key, value]) => (
                    <div key={key} className="flex justify-between gap-4 text-[12px]">
                      <span className="text-[var(--text-muted)]">{key}</span>
                      <span className="font-mono text-[var(--text)] mono-tabular">{String(value)}</span>
                    </div>
                  )) : <p className="text-[12px] text-[var(--text-muted)]">No stage count details were returned.</p>}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'policy' && (
            <div className="grid gap-3 md:grid-cols-2">
              {Object.entries(plan?.policy || {}).length ? Object.entries(plan.policy).map(([key, value]) => (
                <div key={key} className="rounded-[16px] border border-[var(--border)] bg-black/18 p-3">
                  <div className="text-[11px] text-[var(--text-muted)]">{key}</div>
                  <div className="mt-1 font-mono text-[12px] text-[var(--text)]">{String(value)}</div>
                </div>
              )) : <p className="text-sm text-[var(--text-muted)]">No explicit policy override was returned by the planner.</p>}
            </div>
          )}

          {activeTab === 'impact' && (
            <div className="rounded-[18px] border border-[var(--border)] bg-black/18 p-4 text-sm leading-6 text-[var(--text-secondary)]">
              Impact analysis is not included in the current frontend API payload. The verified result, cleaning log, and source row export remain visible for review.
            </div>
          )}

          {activeTab === 'sensitivity' && (
            <div className="rounded-[18px] border border-[var(--border)] bg-black/18 p-4 text-sm leading-6 text-[var(--text-secondary)]">
              Sensitivity output is not exposed by the current API response. No alternate scenario is displayed as verified without backend evidence.
            </div>
          )}

          {activeTab === 'contradictions' && (
            <div className="space-y-3">
              {(trust?.remaining_risks?.length ? trust.remaining_risks : trust?.reasons || ['No contradiction details were returned.']).map((item: string, index: number) => (
                <div key={`${item}-${index}`} className="rounded-[16px] border border-[var(--policy)]/25 bg-[var(--policy-soft)] p-3 text-[12px] leading-5 text-[var(--text-secondary)]">
                  {item}
                </div>
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
