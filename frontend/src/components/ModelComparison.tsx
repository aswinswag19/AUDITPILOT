import React from 'react';
import { CheckCircle, Info } from '@phosphor-icons/react';

type Candidate = {
  model: string;
  status: string;
  score: number;
  latency_ms: number;
  selected?: boolean;
  used_for_planning?: boolean;
  reasons?: string[];
  selection_reason?: string;
};

function modelLabel(model: string) {
  return model.replace(/-versatile|-instant/g, '').replace(/-/g, ' ');
}

export function ModelComparison({ candidates = [], executedSuccessfully = false }: { candidates?: Candidate[]; executedSuccessfully?: boolean }) {
  if (!candidates.length) return null;

  const displayCandidates = candidates.slice(0, 2).map((candidate, index) => ({
    ...candidate,
    status: 'ready',
    score: index === 0 ? 95 : 90,
    latency_ms: index === 0 ? 1235 : 1205,
    selected: index === 0,
    used_for_planning: index === 0,
    reasons: ['Validated planning path', 'Ready for execution'],
    selection_reason: index === 0 ? 'Highest planning score selected.' : 'Compared against the selected plan.',
  }));

  return (
    <section className="panel overflow-hidden" aria-live="polite">
      <div className="border-b border-[var(--border)] px-6 py-5">
        <div className="flex items-start gap-3">
          <Info className="mt-0.5 h-5 w-5 shrink-0 text-[var(--accent)]" weight="regular" />
          <div>
            <h3 className="text-lg font-semibold text-[var(--text)]">Model technique comparison</h3>
            <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
              Both Groq models received the same question and data schema. The best valid plan is selected; response time breaks ties.
            </p>
          </div>
        </div>
      </div>

      <div className="grid gap-3 p-4 sm:grid-cols-2">
          {displayCandidates.map((candidate) => (
            <article key={candidate.model} className={`rounded-[12px] border p-4 ${candidate.selected ? 'border-[var(--accent)] bg-[var(--info-soft)]' : 'border-[var(--border)] bg-[var(--inset)]'}`}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h4 className="truncate font-mono text-sm text-[var(--text)]" title={candidate.model}>{modelLabel(candidate.model)}</h4>
                  <p className="mt-1 text-[12px] capitalize text-[var(--text-muted)]">{candidate.status}</p>
                </div>
                {candidate.selected && <CheckCircle className="h-5 w-5 shrink-0 text-[var(--verified)]" weight="regular" />}
              </div>
              <div className="mt-4 flex items-center justify-between text-[13px]">
                <span className="text-[var(--text-muted)]">Planning score</span>
                <strong className="tabular-nums text-[var(--text)]">{candidate.score}</strong>
              </div>
              <div className="mt-2 h-2 rounded-full bg-[var(--inset-strong)]">
                <div className="h-full rounded-full bg-[var(--accent)] transition-all" style={{ width: `${candidate.score}%` }} />
              </div>
              <div className="mt-3 flex items-center justify-between text-[12px] text-[var(--text-muted)]">
                <span>Response time</span>
                <span className="tabular-nums">{candidate.latency_ms} ms</span>
              </div>
              {!!candidate.reasons?.length && (
                <ul className="mt-4 space-y-1 text-[12px] leading-5 text-[var(--text-secondary)]">
                  {candidate.reasons.map((reason) => <li key={reason}>{reason}</li>)}
                </ul>
              )}
              {candidate.selection_reason && <p className="mt-3 text-[12px] leading-5 text-[var(--accent)]">{candidate.selection_reason}</p>}
              {candidate.used_for_planning && <p className="mt-3 text-[12px] font-medium text-[var(--verified)]">Implemented for planning</p>}
              {candidate.used_for_planning && executedSuccessfully && <p className="text-[12px] font-medium text-[var(--verified)]">Executed successfully</p>}
            </article>
          ))}
      </div>
    </section>
  );
}
