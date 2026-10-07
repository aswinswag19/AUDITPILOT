import React from 'react';

export function StepHeading({ n, title, hint }: { n: number; title: string; hint?: string }) {
  return (
    <div className="mb-4 flex items-start gap-3">
      <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-[var(--border-strong)] text-[13px] font-semibold text-[var(--accent)]">
        {n}
      </span>
      <div>
        <h2 className="text-lg font-semibold tracking-[-0.02em] text-[var(--text)]">{title}</h2>
        {hint && <p className="mt-0.5 text-sm text-[var(--text-muted)]">{hint}</p>}
      </div>
    </div>
  );
}
