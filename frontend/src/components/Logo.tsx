import React from 'react';

/** AuditPilot mark: a pilot's chevron (direction) with a verification tick as its crossbar. */
export function LogoMark({ className = 'h-6 w-6' }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" className={className} fill="none" aria-hidden="true">
      <path d="M24 8 39 39H9Z" stroke="var(--accent)" strokeWidth="3.2" strokeLinejoin="round" />
      <path d="m17 29.5 4.8 4.8 9.2-10.3" stroke="var(--text)" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Wordmark() {
  return (
    <span className="text-[17px] leading-none tracking-[-0.03em] text-[var(--text)]">
      <span className="font-semibold">Audit</span>
      <span className="font-normal text-[var(--accent)]">Pilot</span>
    </span>
  );
}
