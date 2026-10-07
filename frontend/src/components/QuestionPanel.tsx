import React, { useState } from 'react';
import { ArrowRight, CircleNotch } from '@phosphor-icons/react';

export function QuestionPanel({ onAsk, loading, examples = [] }: { onAsk: (q: string) => void; loading: boolean; examples?: string[] }) {
  const [question, setQuestion] = useState('');

  function submit(value = question) {
    const trimmed = value.trim();
    if (!trimmed || loading) return;
    onAsk(trimmed);
  }

  return (
    <div className="panel p-5">
      <label htmlFor="audit-question" className="mb-2 block text-sm font-medium text-[var(--text)]">
        Type your question in plain words
      </label>
      <div className="flex flex-col gap-3 sm:flex-row">
        <input
          id="audit-question"
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') submit(); }}
          disabled={loading}
          className="focus-ring h-12 w-full rounded-[12px] border border-[var(--border-strong)] bg-[var(--control-bg)] px-4 text-[15px] text-[var(--text)] outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--accent)]"
          placeholder="Ask a question about the loaded data"
        />
        <button onClick={() => submit()} disabled={loading || !question.trim()} className="btn btn-primary focus-ring !h-12 sm:w-44">
          {loading ? <CircleNotch className="h-4 w-4 animate-spin" weight="regular" /> : <ArrowRight className="h-4 w-4" weight="regular" />}
          {loading ? 'Checking' : 'Get my answer'}
        </button>
      </div>

      <div className="mt-4">
        <div className="mb-2 text-[13px] text-[var(--text-muted)]">Not sure what to ask? Tap an example.</div>
        <div className="flex flex-wrap gap-2">
          {examples.map((example) => (
            <button
              key={example}
              onClick={() => setQuestion(example)}
              disabled={loading}
              className="focus-ring rounded-full border border-[var(--border)] bg-[var(--inset)] px-3.5 py-2 text-left text-[13px] text-[var(--text-secondary)] transition hover:border-[var(--border-strong)] hover:text-[var(--text)] active:translate-y-px"
            >
              {example}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
