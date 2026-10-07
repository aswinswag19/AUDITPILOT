import React, { useMemo, useState } from 'react';
import { X } from '@phosphor-icons/react';
import { BarChart, DonutChart, TrendChart, compact, full, topSlices, PALETTE } from './Charts';

type Row = { m: string; e: string; c: string; v: number; n: number };
type Props = { data: any; loading?: boolean; error?: string | null };

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="panel p-4">
      <div className="text-[13px] text-[var(--text-muted)]">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums tracking-[-0.02em] text-[var(--text)]">{value}</div>
      {hint && <div className="mt-0.5 text-[12px] text-[var(--text-muted)]">{hint}</div>}
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="panel p-5">
      <h3 className="mb-4 text-sm font-semibold text-[var(--text)]">{title}</h3>
      {children}
    </div>
  );
}

function group(rows: Row[], key: 'e' | 'c') {
  const m = new Map<string, number>();
  rows.forEach((r) => m.set(r[key], (m.get(r[key]) ?? 0) + r.v));
  return [...m].map(([name, value]) => ({ name, value }));
}

export function Dashboard({ data, loading = false, error = null }: Props) {
  const [entity, setEntity] = useState<string | null>(null);
  const [category, setCategory] = useState<string | null>(null);

  // Reset the filters whenever a different file is loaded.
  React.useEffect(() => { setEntity(null); setCategory(null); }, [data?.file]);

  const rows: Row[] = data?.cube ?? [];
  const unit: string = data?.currency ?? '';
  const hasCategory = Boolean(data?.category_label);

  // Cross-filtering: each chart ignores its own filter so you can still switch slices.
  const byEntity = useMemo(() => topSlices(group(rows.filter((r) => !category || r.c === category), 'e')), [rows, category]);
  const byCategory = useMemo(() => topSlices(group(rows.filter((r) => !entity || r.e === entity), 'c')), [rows, entity]);
  const filtered = useMemo(
    () => rows.filter((r) => (!entity || r.e === entity) && (!category || r.c === category)),
    [rows, entity, category],
  );
  const trend = useMemo(() => {
    const m = new Map<string, number>();
    filtered.forEach((r) => r.m && m.set(r.m, (m.get(r.m) ?? 0) + r.v));
    return [...m].sort(([a], [b]) => a.localeCompare(b)).map(([month, value]) => ({ month, value }));
  }, [filtered]);
  const currencyBars = useMemo(
    () => (data?.currencies ?? []).map((c: any, i: number) => ({ name: c.name, value: c.rows, color: PALETTE[i % PALETTE.length], clickable: false })),
    [data],
  );

  if (loading && !data) {
    return <div className="panel p-5" aria-busy="true"><span className="skeleton !block !h-40 !w-full" /></div>;
  }
  if (error) {
    return <div className="panel p-5 text-sm text-[var(--text-secondary)]">{error}</div>;
  }
  if (!data || rows.length === 0) {
    return <div className="panel p-5 text-sm text-[var(--text-muted)]">There is nothing to chart yet. Add a file with dates and amounts.</div>;
  }

  const total = filtered.reduce((s, r) => s + r.v, 0);
  const count = filtered.reduce((s, r) => s + r.n, 0);
  const toggle = (cur: string | null, name: string) => (cur === name ? null : name);

  return (
    <div className="space-y-4">
      {(entity || category) && (
        <div className="flex flex-wrap items-center gap-2 text-[13px]">
          <span className="text-[var(--text-muted)]">Showing only:</span>
          {entity && (
            <button onClick={() => setEntity(null)} className="focus-ring inline-flex items-center gap-1 rounded-full border border-[var(--border-strong)] bg-[var(--inset)] px-3 py-1 text-[var(--text)]">
              {entity} <X className="h-3 w-3" />
            </button>
          )}
          {category && (
            <button onClick={() => setCategory(null)} className="focus-ring inline-flex items-center gap-1 rounded-full border border-[var(--border-strong)] bg-[var(--inset)] px-3 py-1 text-[var(--text)]">
              {category} <X className="h-3 w-3" />
            </button>
          )}
          <button onClick={() => { setEntity(null); setCategory(null); }} className="text-[var(--text-muted)] underline underline-offset-4">Clear all</button>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Tile label={`Total (${unit})`} value={compact(total)} hint={full(total)} />
        <Tile label="Records charted" value={full(count)} hint={`of ${full(data.rows_total)} in the file`} />
        <Tile label="Average per record" value={count ? compact(total / count) : '-'} />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card title={`Share by ${data.entity_label}`}>
          <DonutChart slices={byEntity} selected={entity} onSelect={(n) => setEntity(toggle(entity, n))} unit={unit} label={data.entity_label} />
        </Card>
        <Card title={hasCategory ? `By ${data.category_label}` : 'Records by currency'}>
          {hasCategory
            ? <BarChart slices={byCategory} selected={category} onSelect={(n) => setCategory(toggle(category, n))} unit={unit} />
            : <BarChart slices={currencyBars} unit="rows" />}
        </Card>
      </div>

      <Card title="Month by month">
        <TrendChart points={trend} unit={unit} />
      </Card>

      {data.notes?.length > 0 && (
        <ul className="space-y-1 pl-1 text-[13px] text-[var(--text-muted)]">
          {data.notes.map((n: string) => <li key={n}>{n}</li>)}
        </ul>
      )}
    </div>
  );
}
