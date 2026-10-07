import React, { useState, useEffect } from 'react';
import { ArrowCounterClockwise, ShieldCheck, WarningCircle } from '@phosphor-icons/react';
import { LogoMark, Wordmark } from './components/Logo';
import { StepHeading } from './components/Step';
import { YourData } from './components/YourData';
import { QuestionPanel } from './components/QuestionPanel';
import { Answer } from './components/Answer';
import { GroupedAnswer } from './components/GroupedAnswer';
import { CurrencyConfirmation } from './components/CurrencyConfirmation';
import {
  ApiError, CurrencyAnswers, uploadDataset, getProfile, createPlan, executePlan, verifyPlan, getTrust,
  getProof, getImpact, getSensitivity, generateReport, API_BASE_URL,
} from './lib/api';

const EMPTY_ANSWERS: CurrencyAnswers = { currency_map: {}, conversion_basis: null };
const DEFAULT_FILE = 'sales.csv';

export function App() {
  const [filename, setFilename] = useState<string>(DEFAULT_FILE);
  const [profile, setProfile] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [profileLoading, setProfileLoading] = useState<boolean>(false);
  const [question, setQuestion] = useState<string>('');
  const [plan, setPlan] = useState<any>(null);
  const [answers, setAnswers] = useState<CurrencyAnswers>(EMPTY_ANSWERS);   // the user's currency answers
  const [currencyCheck, setCurrencyCheck] = useState<any>(null);            // set while we wait for confirmation
  const [executionResult, setExecutionResult] = useState<any>(null);
  const [grouped, setGrouped] = useState<any>(null);                        // compare / rank result
  const [trust, setTrust] = useState<any>(null);
  const [proof, setProof] = useState<any>(null);
  const [impact, setImpact] = useState<any>(null);
  const [sensitivity, setSensitivity] = useState<any>(null);
  const [proofError, setProofError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadProfile(DEFAULT_FILE);
  }, []);

  async function loadProfile(name: string = filename) {
    setProfileLoading(true);
    try {
      const res = await getProfile(name);
      setProfile(res.profile);
      if (res.profile?.file) setFilename(res.profile.file);
      setError(null);
    } catch (e) {
      console.error(e);
      setError(e instanceof ApiError
        ? `We could not open this file: ${e.readable}`
        : 'We could not open your data. Check that the app server is running, or upload a file.');
    } finally {
      setProfileLoading(false);
    }
  }

  function clearOutcome() {
    setExecutionResult(null);
    setGrouped(null);
    setTrust(null);
    setProof(null);
    setImpact(null);
    setSensitivity(null);
    setProofError(null);
    setCurrencyCheck(null);
  }

  function resetAnalysis() {
    clearOutcome();
    setPlan(null);
    setAnswers(EMPTY_ANSWERS);
    setError(null);
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const input = e.target;
    const file = input.files?.[0];
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      let res;
      try {
        res = await uploadDataset(file);
      } catch (err) {
        // The server refuses to silently replace an existing file.
        if (err instanceof ApiError && err.status === 409 && window.confirm(`${file.name} already exists. Replace it with this file?`)) {
          res = await uploadDataset(file, true);
        } else {
          throw err;
        }
      }
      resetAnalysis();
      const name = res?.filename || file.name;
      setFilename(name);
      await loadProfile(name);
    } catch (err) {
      console.error(err);
      setError(err instanceof ApiError && err.status === 409
        ? 'That file was not replaced. Rename it and upload again, or choose to replace it.'
        : 'That file did not upload. Please choose a CSV file and try again.');
    } finally {
      setLoading(false);
      input.value = '';
    }
  }

  /** Turn a failed API call into UI state. Returns true when it was handled. */
  function handleApiFailure(err: unknown): boolean {
    if (err instanceof ApiError) {
      if (err.isCurrencyConfirmation) {
        setCurrencyCheck(err.detail);           // ask the user, then send the same request again
        return true;
      }
      if (err.isInvalidPlan) {
        setError(`We could not run that question: ${err.readable}`);
        return true;
      }
      if (err.status === 422 || err.status === 409) {
        setError(err.readable);
        return true;
      }
    }
    return false;
  }

  /** Run both calculations (and the trust / proof steps) for a ready plan with the given currency answers. */
  async function runAnalysis(p: any, ans: CurrencyAnswers) {
    clearOutcome();
    const policy = { currency_map: ans.currency_map, conversion_basis: ans.conversion_basis };

    // Compare / rank questions: one verified figure per entity (trust and proof are single-figure only).
    if (p.group_by?.length && (p.intent === 'compare' || p.intent === 'rank')) {
      const v = await verifyPlan(p, filename, policy);
      setGrouped(v.grouped);
      return;
    }

    const exec = await executePlan(p, filename, policy);
    setExecutionResult(exec);
    const t = await getTrust(p, filename, policy);
    setTrust(t);

    if (exec?.inspector?.status === 'VERIFIED' && exec?.analyst?.status === 'VERIFIED') {
      try {
        const bundle = await getProof(p, filename, policy);   // also carries impact + sensitivity
        setProof(bundle);
        setImpact(bundle.impact ?? null);
        setSensitivity(bundle.sensitivity ?? null);
      } catch (err) {
        setProofError(err instanceof ApiError ? err.readable : 'Proof bundle was not issued by the backend.');
        if (exec.analyst.status === 'VERIFIED') {
          // Still show what each cleaning rule did, even without a proof.
          getImpact(p, filename, policy).then(setImpact).catch(() => {});
          getSensitivity(p, filename, policy).then(setSensitivity).catch(() => {});
        }
      }
    } else {
      setProofError('Evidence not created because the second check did not pass.');
    }
  }

  async function handleAsk(q: string) {
    setLoading(true);
    setError(null);
    clearOutcome();
    setAnswers(EMPTY_ANSWERS);
    setQuestion(q);
    try {
      const p = await createPlan(q, filename, {});
      setPlan(p);

      if (p.status === 'refused') {
        setExecutionResult({ analyst: { status: 'REFUSED', result: null }, inspector: { status: 'REFUSED', result: null } });
        setTrust({ trust_decision: 'REFUSED', publishability: 'EXTERNAL_REPORTING_BLOCKED', reasons: [p.refusal?.reason || 'Refused'] });
        setProofError('Refused questions do not receive a verified proof bundle.');
        return;
      }
      if (p.status === 'needs_clarification') return;   // the clarification card is shown below

      // Ask about foreign / blank / unknown currencies BEFORE computing anything.
      if (p.currency_confirmation?.needs_confirmation) {
        setCurrencyCheck(p.currency_confirmation);
        return;
      }
      await runAnalysis(p, EMPTY_ANSWERS);
    } catch (err) {
      console.error(err);
      if (!handleApiFailure(err)) setError('Something went wrong while checking your question. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  async function handleConfirmCurrencies(ans: CurrencyAnswers) {
    if (!plan) return;
    setLoading(true);
    setError(null);
    setAnswers(ans);
    try {
      await runAnalysis(plan, ans);
    } catch (err) {
      console.error(err);
      if (!handleApiFailure(err)) setError('Something went wrong while checking your question. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  async function handleGeneratePDF(reportType: string) {
    try {
      const isVerifiedReport = reportType === 'verified';
      const policy = { currency_map: answers.currency_map, conversion_basis: answers.conversion_basis };
      let proofBundle = proof;
      if (isVerifiedReport && !proofBundle && plan?.status === 'ready') {
        try {
          proofBundle = await getProof(plan, filename, policy);
          setProof(proofBundle);
        } catch (err) {
          setError(err instanceof ApiError ? err.readable : 'We could not create the verified report.');
          return;
        }
      }
      if (isVerifiedReport && !proofBundle?.proof_id) {
        setError('We could not create the verified report because the evidence file is missing.');
        return;
      }
      if (!isVerifiedReport) {
        proofBundle = proofBundle || {
          proof_id: 'not-issued',
          answer: executionResult?.analyst?.result || null,
          currency: executionResult?.analyst?.currency || 'INR',
          trust_decision: trust?.trust_decision || 'REVIEW_REQUIRED',
          publishability: trust?.publishability || 'MANAGEMENT_REVIEW_REQUIRED',
          analyst_status: executionResult?.analyst?.status || 'UNKNOWN',
          inspector_status: executionResult?.inspector?.status || 'UNKNOWN',
          reasons: trust?.reasons || [],
          conversion: executionResult?.analyst?.conversion || null,
        };
      }
      const res = await generateReport(proofBundle, reportType);
      if (res.download_url) window.open(`${API_BASE_URL}${res.download_url}`, '_blank');
    } catch (err) {
      console.error(err);
      setError('The report could not be created. Please try again.');
    }
  }

  const clarification = plan?.status === 'needs_clarification' ? plan.clarification : null;
  const asked = Boolean(plan) || loading;
  const policyForView = { currency_map: answers.currency_map, conversion_basis: answers.conversion_basis };

  return (
    <div className="min-h-[100dvh] text-[var(--text)]">
      <header className="sticky top-0 z-40 border-b border-[var(--border)] bg-[var(--header-bg)] backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-3xl items-center justify-between gap-4 px-4">
          <div className="flex items-center gap-3">
            <LogoMark className="h-7 w-7" />
            <Wordmark />
          </div>
          {asked && (
            <button onClick={resetAnalysis} className="btn btn-secondary focus-ring !h-10 !px-3.5 !text-[13px]">
              <ArrowCounterClockwise className="h-4 w-4" weight="regular" />
              Ask something new
            </button>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 pb-16 pt-10">
        <h1 className="display text-4xl leading-[1.1] md:text-5xl">
          Get answers from your sales data. <span>Checked, not guessed.</span>
        </h1>
        <p className="mt-4 max-w-[52ch] text-base leading-7 text-[var(--text-secondary)]">
          Add your file, ask a question, and get a number you can rely on.
        </p>

        {error && (
          <div className="mt-8 flex flex-wrap items-center justify-between gap-3 rounded-[12px] border border-[var(--blocked)] bg-[var(--blocked-soft)] px-4 py-3 text-sm text-[var(--text)]" role="alert">
            <span>{error}</span>
            <button onClick={() => { setError(null); if (!profile) loadProfile(); }} className="text-sm font-medium underline underline-offset-4">Dismiss</button>
          </div>
        )}

        <section className="mt-10">
          <StepHeading n={1} title="Your file" hint="This is the data we will use to answer you." />
          <YourData profile={profile} onUpload={handleUpload} onRetry={() => loadProfile()} loading={loading || profileLoading} />
        </section>

        <section className="mt-10">
          <StepHeading n={2} title="Ask your question" />
          <QuestionPanel onAsk={handleAsk} loading={loading} examples={profile?.examples} />
        </section>

        <section className="mt-10">
          <StepHeading n={3} title="Your answer" />
          {clarification ? (
            <div className="panel p-6" aria-live="polite">
              <div className="inline-flex items-center gap-2 text-sm font-medium" style={{ color: 'var(--policy)' }}>
                <WarningCircle className="h-5 w-5" weight="regular" />
                We need a little more detail
              </div>
              <h3 className="mt-3 text-xl font-semibold text-[var(--text)]">{clarification.question || 'Could you be more specific?'}</h3>
              {clarification.options?.length > 0 && (
                <div className="mt-4 flex flex-wrap gap-2">
                  {clarification.options.map((o: string) => (
                    <button key={o} onClick={() => handleAsk(`${question} ${o}`)} className="focus-ring rounded-full border border-[var(--border)] bg-[var(--inset)] px-3.5 py-2 text-[13px] text-[var(--text-secondary)] hover:border-[var(--border-strong)] hover:text-[var(--text)]">{o}</button>
                  ))}
                </div>
              )}
            </div>
          ) : currencyCheck?.needs_confirmation ? (
            <CurrencyConfirmation
              check={currencyCheck}
              loading={loading}
              onSubmit={handleConfirmCurrencies}
              onCancel={resetAnalysis}
            />
          ) : grouped ? (
            <GroupedAnswer grouped={grouped} policy={policyForView} plan={plan} />
          ) : (
            <Answer
              result={executionResult}
              plan={plan}
              trust={trust}
              proof={proof}
              proofError={proofError}
              policy={policyForView}
              impact={impact}
              sensitivity={sensitivity}
              loading={loading}
              onGeneratePDF={handleGeneratePDF}
            />
          )}
        </section>
      </main>

      <footer className="mx-auto flex max-w-3xl items-center gap-2 px-4 pb-10 text-[13px] text-[var(--text-muted)]">
        <ShieldCheck className="h-4 w-4 text-[var(--accent)]" weight="regular" />
        Every answer is checked twice before you see it.
      </footer>
    </div>
  );
}

export default App;
