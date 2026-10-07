import React from 'react';
import { AlertTriangle, Columns3, Database, FileSpreadsheet, Rows3, UploadCloud } from 'lucide-react';

type DataVaultProps = {
  profile: any;
  onUpload: (e: React.ChangeEvent<HTMLInputElement>) => void;
  loading?: boolean;
};

function FieldRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-[var(--border)]/70 py-3 last:border-0">
      <span className="text-[12px] text-[var(--text-muted)]">{label}</span>
      <span className="max-w-[11rem] truncate text-right font-mono text-[12px] text-[var(--text)] mono-tabular">{value}</span>
    </div>
  );
}

export function DataVault({ profile, onUpload, loading = false }: DataVaultProps) {
  const issueCount = [
    profile?.exact_duplicate_groups,
    profile?.conflicting_duplicate_groups,
    profile?.missing_date_count,
    profile?.missing_amount_count,
    profile?.ambiguous_date_count,
  ].reduce((sum: number, value: any) => sum + Number(value || 0), 0);

  return (
    <aside className="panel overflow-hidden">
      <div className="border-b border-[var(--border)] p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-[13px] font-semibold text-[var(--text)]">
              <Database className="h-4 w-4 text-[var(--info)]" strokeWidth={1.8} />
              Data Vault
            </div>
            <p className="mt-1 text-[12px] leading-5 text-[var(--text-muted)]">Local CSV tables are profiled before analysis.</p>
          </div>
          <label className="focus-ring inline-flex h-9 shrink-0 cursor-pointer items-center gap-2 rounded-[12px] border border-[var(--border-strong)] bg-[var(--surface-elevated)] px-3 text-[12px] font-medium text-[var(--text)] transition hover:bg-[var(--surface-hover)] active:translate-y-px">
            <UploadCloud className="h-3.5 w-3.5" strokeWidth={1.8} />
            Upload
            <input type="file" accept=".csv" onChange={onUpload} className="hidden" aria-label="Upload CSV dataset" />
          </label>
        </div>
      </div>

      <div className="p-4">
        <div className="rounded-[18px] border border-[var(--border)] bg-[rgba(8,10,15,0.54)] p-3">
          <div className="mb-3 flex items-center gap-2 text-[12px] text-[var(--text-muted)]">
            <FileSpreadsheet className="h-4 w-4 text-[var(--info)]" strokeWidth={1.8} />
            Active dataset
          </div>
          <div className="truncate font-mono text-sm text-[var(--text)]">{profile?.file || (loading ? 'Loading profile' : 'No profile loaded')}</div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2">
          <div className="control p-3">
            <Rows3 className="mb-3 h-4 w-4 text-[var(--text-muted)]" strokeWidth={1.8} />
            <div className="font-mono text-xl text-[var(--text)] mono-tabular">{profile?.rows ?? 'N/A'}</div>
            <div className="mt-1 text-[11px] text-[var(--text-muted)]">Rows</div>
          </div>
          <div className="control p-3">
            <Columns3 className="mb-3 h-4 w-4 text-[var(--text-muted)]" strokeWidth={1.8} />
            <div className="font-mono text-xl text-[var(--text)] mono-tabular">{profile?.columns ?? 'N/A'}</div>
            <div className="mt-1 text-[11px] text-[var(--text-muted)]">Columns</div>
          </div>
        </div>

        <div className="mt-4 rounded-[18px] border border-[var(--border)] bg-[rgba(8,10,15,0.38)] px-3">
          <FieldRow label="Exact duplicate groups" value={profile?.exact_duplicate_groups ?? 'N/A'} />
          <FieldRow label="Conflicting groups" value={profile?.conflicting_duplicate_groups ?? 'N/A'} />
          <FieldRow label="Missing dates" value={profile?.missing_date_count ?? 'N/A'} />
          <FieldRow label="Unsupported currencies" value={profile?.unsupported_currencies?.length ?? 'N/A'} />
        </div>

        <div className="mt-4 flex items-start gap-2 rounded-[16px] border border-[var(--policy)]/25 bg-[var(--policy-soft)] p-3">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[var(--policy)]" strokeWidth={1.8} />
          <div>
            <div className="text-[12px] font-medium text-[var(--text)]">{issueCount ? `${issueCount} data-quality signals` : 'Inspection ready'}</div>
            <p className="mt-1 text-[11px] leading-4 text-[var(--text-muted)]">Potential risks remain visible and are not hidden from the final trust decision.</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
