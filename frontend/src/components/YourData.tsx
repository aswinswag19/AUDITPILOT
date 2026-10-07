import React from 'react';
import { CaretDown, CheckCircle, CloudArrowUp, FileCsv, Warning } from '@phosphor-icons/react';

type Props = {
  profile: any;
  onUpload: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onRetry: () => void;
  loading?: boolean;
};

function findings(profile: any): string[] {
  const out: string[] = [];
  const add = (n: any, one: string, many: string) => {
    const v = Number(n || 0);
    if (v > 0) out.push(`${v.toLocaleString()} ${v === 1 ? one : many}`);
  };
  add(profile?.exact_duplicate_groups, 'row appears more than once', 'rows appear more than once');
  add(profile?.conflicting_duplicate_groups, 'record disagrees with a copy of itself', 'records disagree with copies of themselves');
  add(profile?.missing_date_count, 'row has no date', 'rows have no date');
  add(profile?.missing_amount_count, 'row has no amount', 'rows have no amount');
  add(profile?.ambiguous_date_count, 'date is hard to read', 'dates are hard to read');
  add(profile?.unsupported_currencies?.length, 'currency we do not support', 'currencies we do not support');
  return out;
}

function health(score: number) {
  if (score >= 90) return { label: 'Looks great', color: 'var(--verified)' };
  if (score >= 75) return { label: 'Mostly fine', color: 'var(--policy)' };
  return { label: 'Needs attention', color: 'var(--blocked)' };
}

export function YourData({ profile, onUpload, onRetry, loading = false }: Props) {
  const upload = (
    <input type="file" accept=".csv" onChange={onUpload} className="sr-only" aria-label="Choose a CSV file" />
  );

  if (loading && !profile) {
    return (
      <div className="panel flex items-center gap-4 p-5" aria-busy="true">
        <span className="skeleton !h-10 !w-10 !rounded-[12px]" />
        <div className="space-y-2">
          <span className="skeleton !block !w-40" />
          <span className="skeleton !block !w-28" />
        </div>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="panel p-6 text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border border-[var(--border)] bg-[var(--inset)]">
          <FileCsv className="h-6 w-6 text-[var(--accent)]" weight="regular" />
        </div>
        <h3 className="mt-4 text-base font-semibold text-[var(--text)]">No file loaded yet</h3>
        <p className="mx-auto mt-1 max-w-[44ch] text-sm leading-6 text-[var(--text-muted)]">
          Upload a spreadsheet saved as CSV and we will take a look at it first.
        </p>
        <div className="mt-5 flex flex-wrap justify-center gap-2">
          <label className="btn btn-primary focus-ring cursor-pointer">
            <CloudArrowUp className="h-4 w-4" weight="regular" />
            Upload a file
            {upload}
          </label>
          <button onClick={onRetry} className="btn btn-secondary focus-ring">Try again</button>
        </div>
      </div>
    );
  }

  const score = Number(profile.quality_score ?? 0);
  const h = health(score);
  const items = findings(profile);

  return (
    <div className="panel p-5">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-[12px] border border-[var(--border)] bg-[var(--inset)]">
            <FileCsv className="h-6 w-6 text-[var(--accent)]" weight="regular" />
          </div>
          <div className="min-w-0">
            <div className="truncate text-base font-semibold text-[var(--text)]">{profile.file}</div>
            <div className="text-sm text-[var(--text-muted)]">
              {Number(profile.rows ?? 0).toLocaleString()} records, {Number(profile.columns ?? 0).toLocaleString()} columns
            </div>
          </div>
        </div>
        <label className="btn btn-secondary focus-ring cursor-pointer">
          <CloudArrowUp className="h-4 w-4" weight="regular" />
          Change file
          {upload}
        </label>
      </div>

      <div className="mt-5 border-t border-[var(--border)] pt-4">
        {items.length === 0 ? (
          <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
            <CheckCircle className="h-5 w-5" style={{ color: h.color }} weight="regular" />
            <span><strong className="font-semibold text-[var(--text)]">Data health: {h.label}.</strong> We did not find any problems.</span>
          </div>
        ) : (
          <details>
            <summary className="focus-ring flex items-center justify-between gap-3 rounded-[8px] text-sm text-[var(--text-secondary)]">
              <span className="flex items-center gap-2">
                <Warning className="h-5 w-5 shrink-0" style={{ color: h.color }} weight="regular" />
                <span><strong className="font-semibold text-[var(--text)]">Data health: {h.label}.</strong> We found {items.length} {items.length === 1 ? 'thing' : 'things'} worth knowing.</span>
              </span>
              <CaretDown className="caret h-4 w-4 shrink-0 text-[var(--text-muted)]" weight="regular" />
            </summary>
            <ul className="mt-3 space-y-1.5 pl-7 text-sm text-[var(--text-secondary)]">
              {items.map((t) => <li key={t} className="list-disc">{t}</li>)}
              <li className="list-none pt-1 text-[13px] text-[var(--text-muted)]">We take these into account, so your answer stays honest.</li>
            </ul>
          </details>
        )}
      </div>
    </div>
  );
}
