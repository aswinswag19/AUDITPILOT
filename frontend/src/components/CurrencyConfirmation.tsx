import React, { useMemo, useState } from 'react';
import { ArrowRight, CircleNotch, Coins } from '@phosphor-icons/react';
import type { CurrencyAnswers } from '../lib/api';

type Props = {
  check: any;                                   // body of /currency/check (or the 409 detail)
  loading?: boolean;
  onSubmit: (answers: CurrencyAnswers) => void;
  onCancel: () => void;
};

const money = (v: any) => {
  const n = Number(v);
  return Number.isFinite(n) ? n.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : String(v ?? '');
};

function Option({ checked, onChange, children, name }: { checked: boolean; onChange: () => void; children: React.ReactNode; name: string }) {
  return (
    <label className={`flex cursor-pointer items-start gap-3 rounded-[12px] border px-4 py-3 text-sm transition ${checked ? 'border-[var(--accent)] bg-[var(--info-soft)] text-[var(--text)]' : 'border-[var(--border)] bg-[var(--inset)] text-[var(--text-secondary)] hover:border-[var(--border-strong)]'}`}>
      <input type="radio" name={name} checked={checked} onChange={onChange} className="mt-1 accent-[var(--accent)]" />
      <span className="min-w-0 flex-1">{children}</span>
    </label>
  );
}

export function CurrencyConfirmation({ check, loading = false, onSubmit, onCancel }: Props) {
  const questions: any[] = check?.questions || [];
  const target: string = check?.target_currency || 'INR';
  const current: CurrencyAnswers = {
    currency_map: { ...(check?.current_answers?.currency_map || {}) },
    conversion_basis: check?.current_answers?.conversion_basis ?? null,
  };

  const [picked, setPicked] = useState<Record<string, number>>({});
  const [codes, setCodes] = useState<Record<string, string>>({});

  const codeOk = (id: string) => /^[A-Za-z]{3}$/.test((codes[id] || '').trim());

  const answered = (q: any) => {
    const i = picked[q.id];
    if (i === undefined) return false;
    return q.options[i]?.free_text ? codeOk(q.id) : true;
  };
  const ready = questions.length > 0 && questions.every(answered);

  const currencies: any[] = useMemo(() => check?.currencies || [], [check]);

  function submit() {
    if (!ready || loading) return;
    const out: CurrencyAnswers = { currency_map: { ...current.currency_map }, conversion_basis: current.conversion_basis };
    for (const q of questions) {
      const opt = q.options[picked[q.id]];
      if (!opt) continue;
      if (q.type === 'conversion_basis') {
        out.conversion_basis = opt.answer.conversion_basis;
      } else {
        const code = q.currency as string;
        out.currency_map[code] = opt.free_text ? codes[q.id].trim().toUpperCase() : opt.answer.currency_map[code];
      }
    }
    onSubmit(out);
  }

  return (
    <section className="panel overflow-hidden" aria-live="polite">
      <div className="p-6">
        <div className="inline-flex items-center gap-2 text-sm font-medium" style={{ color: 'var(--policy)' }}>
          <Coins className="h-5 w-5" weight="regular" />
          Quick check before we calculate
        </div>
        <h3 className="mt-3 text-xl font-semibold text-[var(--text)]">Please confirm the currencies in your data.</h3>
        <p className="mt-2 max-w-[62ch] text-[15px] leading-6 text-[var(--text-secondary)]">
          Some rows in this question are not in {target}. We will not guess: tell us what they are and how to convert them, then we will work out the answer.
        </p>

        {currencies.length > 0 && (
          <div className="scrollbar-soft mt-5 overflow-x-auto rounded-[12px] border border-[var(--border)]">
            <table className="w-full min-w-[420px] text-left text-[13px]">
              <thead className="bg-[var(--inset)] text-[var(--text-muted)]">
                <tr>
                  <th className="px-3 py-2 font-medium">Currency in file</th>
                  <th className="px-3 py-2 font-medium">Rows</th>
                  <th className="px-3 py-2 text-right font-medium">Total in that currency</th>
                </tr>
              </thead>
              <tbody className="text-[var(--text-secondary)]">
                {currencies.map((c) => (
                  <tr key={c.code} className="border-t border-[var(--border)]">
                    <td className="px-3 py-2 font-mono text-[var(--text)]">{c.code === '(BLANK)' ? 'Blank' : c.code}</td>
                    <td className="px-3 py-2 mono-tabular">{c.rows}</td>
                    <td className="px-3 py-2 text-right mono-tabular">{money(c.native_amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="mt-6 space-y-7">
          {questions.map((q, qi) => (
            <fieldset key={q.id}>
              <legend className="text-[15px] font-medium leading-6 text-[var(--text)]">
                <span className="mr-2 text-[var(--text-muted)]">{qi + 1}.</span>{q.question}
              </legend>

              {q.type === 'conversion_basis' && q.details && Object.keys(q.details).length > 0 && (
                <div className="mt-3 space-y-1 rounded-[12px] border border-[var(--border)] bg-[var(--inset)] p-3 text-[13px] leading-5 text-[var(--text-secondary)]">
                  {Object.entries(q.details).map(([code, d]: [string, any]) => (
                    <div key={code}>
                      <span className="font-mono text-[var(--text)]">{code}</span>
                      {d.rate_on_file
                        ? <>: rates on file from {d.first_rate_effective || 'n/a'}; latest rate {d.latest_rate} (effective {d.latest_rate_effective}).
                            {d.rows_without_rate_on_transaction_date > 0 && <> {d.rows_without_rate_on_transaction_date} row(s) have no rate on their own date.</>}</>
                        : <>: no exchange rate on file.</>}
                    </div>
                  ))}
                </div>
              )}

              <div className="mt-3 space-y-2" role="radiogroup">
                {q.options.map((opt: any, oi: number) => (
                  <Option key={oi} name={q.id} checked={picked[q.id] === oi} onChange={() => setPicked((p) => ({ ...p, [q.id]: oi }))}>
                    {opt.label}
                    {opt.free_text && picked[q.id] === oi && (
                      <input
                        autoFocus
                        maxLength={3}
                        value={codes[q.id] || ''}
                        onChange={(e) => setCodes((c) => ({ ...c, [q.id]: e.target.value.toUpperCase() }))}
                        placeholder="e.g. GBP"
                        aria-label="Three-letter currency code"
                        className="focus-ring ml-3 h-9 w-24 rounded-[8px] border border-[var(--border-strong)] bg-[var(--control-bg)] px-3 font-mono text-sm uppercase text-[var(--text)] outline-none focus:border-[var(--accent)]"
                      />
                    )}
                  </Option>
                ))}
              </div>
            </fieldset>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 border-t border-[var(--border)] bg-[var(--inset)] px-6 py-4">
        <button onClick={submit} disabled={!ready || loading} className="btn btn-primary focus-ring">
          {loading ? <CircleNotch className="h-4 w-4 animate-spin" weight="regular" /> : <ArrowRight className="h-4 w-4" weight="regular" />}
          {loading ? 'Checking' : 'Confirm and get my answer'}
        </button>
        <button onClick={onCancel} disabled={loading} className="btn btn-secondary focus-ring">Cancel</button>
        <span className="text-[13px] text-[var(--text-muted)]">Your answers are used for this question only.</span>
      </div>
    </section>
  );
}
