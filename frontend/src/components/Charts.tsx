import React from 'react';

/** Small dependency-free SVG charts: donut, horizontal bars and a trend line. */

export const PALETTE = ['#8ee3c0', '#e4b45f', '#7aa7f0', '#ef7272', '#b79cf2', '#62d49b'];
export const OTHER_COLOR = '#5b645f';

export type Slice = { name: string; value: number; color: string; clickable?: boolean };

export const compact = (n: number) =>
  new Intl.NumberFormat('en-IN', { notation: 'compact', maximumFractionDigits: 1 }).format(n);
export const full = (n: number) =>
  new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(n);

/** Keep the biggest `max` items and fold the rest into "Other". */
export function topSlices(items: { name: string; value: number }[], max = 6): Slice[] {
  const sorted = items.filter((i) => i.value > 0).sort((a, b) => b.value - a.value);
  const head = sorted.slice(0, max).map((i, idx) => ({ ...i, color: PALETTE[idx % PALETTE.length], clickable: true }));
  const rest = sorted.slice(max).reduce((s, i) => s + i.value, 0);
  if (rest > 0) head.push({ name: 'Other', value: rest, color: OTHER_COLOR, clickable: false });
  return head;
}

type PieProps = {
  slices: Slice[];
  selected?: string | null;
  onSelect?: (name: string) => void;
  unit?: string;
  label?: string;
};

export function DonutChart({ slices, selected, onSelect, unit = '', label = 'Share' }: PieProps) {
  const [hover, setHover] = React.useState<string | null>(null);
  const total = slices.reduce((s, x) => s + x.value, 0);
  const R = 70, r = 44, C = 90;
  let angle = -Math.PI / 2;

  const arcs = slices.map((s) => {
    const frac = total ? s.value / total : 0;
    const a0 = angle;
    const a1 = angle + frac * 2 * Math.PI;
    angle = a1;
    const pt = (rad: number, a: number) => [C + rad * Math.cos(a), C + rad * Math.sin(a)];
    let d: string;
    if (frac >= 0.9999) {
      d = `M ${C - R} ${C} a ${R} ${R} 0 1 0 ${2 * R} 0 a ${R} ${R} 0 1 0 ${-2 * R} 0 M ${C - r} ${C} a ${r} ${r} 0 1 1 ${2 * r} 0 a ${r} ${r} 0 1 1 ${-2 * r} 0`;
    } else {
      const [x0, y0] = pt(R, a0), [x1, y1] = pt(R, a1), [x2, y2] = pt(r, a1), [x3, y3] = pt(r, a0);
      const large = a1 - a0 > Math.PI ? 1 : 0;
      d = `M ${x0} ${y0} A ${R} ${R} 0 ${large} 1 ${x1} ${y1} L ${x2} ${y2} A ${r} ${r} 0 ${large} 0 ${x3} ${y3} Z`;
    }
    return { ...s, d, frac };
  });

  const focus = slices.find((s) => s.name === (hover ?? selected));
  const dim = (name: string) => (selected && selected !== name ? 0.3 : 1);

  return (
    <div className="flex flex-wrap items-center gap-6">
      <svg viewBox="0 0 180 180" className="h-44 w-44 shrink-0" role="img" aria-label={`${label} chart`}>
        {arcs.map((a) => (
          <path
            key={a.name}
            d={a.d}
            fill={a.color}
            fillRule="evenodd"
            opacity={dim(a.name)}
            stroke="var(--surface-panel)"
            strokeWidth={2}
            style={{ cursor: a.clickable && onSelect ? 'pointer' : 'default', transition: 'opacity .15s' }}
            onMouseEnter={() => setHover(a.name)}
            onMouseLeave={() => setHover(null)}
            onClick={() => a.clickable && onSelect?.(a.name)}
          >
            <title>{`${a.name}: ${full(a.value)} ${unit} (${(a.frac * 100).toFixed(1)}%)`}</title>
          </path>
        ))}
        <text x={C} y={C - 4} textAnchor="middle" fontSize="11" fill="var(--text-muted)">
          {focus ? focus.name : 'Total'}
        </text>
        <text x={C} y={C + 14} textAnchor="middle" fontSize="15" fontWeight="600" fill="var(--text)">
          {compact(focus ? focus.value : total)}
        </text>
      </svg>
      <ul className="min-w-[10rem] flex-1 space-y-1.5 text-sm">
        {arcs.map((a) => (
          <li key={a.name}>
            <button
              type="button"
              disabled={!a.clickable || !onSelect}
              onClick={() => onSelect?.(a.name)}
              onMouseEnter={() => setHover(a.name)}
              onMouseLeave={() => setHover(null)}
              className="focus-ring flex w-full items-center gap-2 rounded-[8px] px-1.5 py-1 text-left hover:bg-[var(--surface-hover)] disabled:hover:bg-transparent"
              style={{ opacity: dim(a.name) }}
            >
              <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: a.color }} />
              <span className="min-w-0 flex-1 truncate text-[var(--text-secondary)]">{a.name}</span>
              <span className="tabular-nums text-[var(--text)]">{(a.frac * 100).toFixed(0)}%</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

type BarProps = {
  slices: Slice[];
  selected?: string | null;
  onSelect?: (name: string) => void;
  unit?: string;
};

export function BarChart({ slices, selected, onSelect, unit = '' }: BarProps) {
  const max = Math.max(...slices.map((s) => s.value), 1);
  return (
    <ul className="space-y-2.5" role="list">
      {slices.map((s) => {
        const canClick = s.clickable && onSelect;
        return (
          <li key={s.name}>
            <button
              type="button"
              disabled={!canClick}
              onClick={() => onSelect?.(s.name)}
              title={`${s.name}: ${full(s.value)} ${unit}`}
              className="focus-ring block w-full rounded-[8px] px-1 py-0.5 text-left"
              style={{ opacity: selected && selected !== s.name ? 0.35 : 1, transition: 'opacity .15s' }}
            >
              <div className="mb-1 flex items-baseline justify-between gap-3 text-[13px]">
                <span className="truncate text-[var(--text-secondary)]">{s.name}</span>
                <span className="tabular-nums text-[var(--text)]">{compact(s.value)}</span>
              </div>
              <div className="h-2.5 w-full rounded-full bg-[var(--inset-strong)]">
                <div className="h-full rounded-full" style={{ width: `${(s.value / max) * 100}%`, background: s.color }} />
              </div>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export const monthLabel = (m: string) => {
  const [y, mo] = m.split('-');
  return `${MONTHS[Number(mo) - 1] ?? mo} ${y.slice(2)}`;
};

export function TrendChart({ points, unit = '' }: { points: { month: string; value: number }[]; unit?: string }) {
  const [hover, setHover] = React.useState<number | null>(null);
  const W = 560, H = 190, L = 44, Rt = 12, T = 14, B = 28;
  if (points.length === 0) {
    return <p className="py-8 text-center text-sm text-[var(--text-muted)]">No dated rows to show a trend.</p>;
  }
  const max = Math.max(...points.map((p) => p.value), 1);
  const min = Math.min(0, ...points.map((p) => p.value));
  const x = (i: number) => (points.length === 1 ? (L + W - Rt) / 2 : L + (i * (W - L - Rt)) / (points.length - 1));
  const y = (v: number) => T + (1 - (v - min) / (max - min || 1)) * (H - T - B);
  const line = points.map((p, i) => `${i ? 'L' : 'M'} ${x(i)} ${y(p.value)}`).join(' ');
  const area = `${line} L ${x(points.length - 1)} ${y(0)} L ${x(0)} ${y(0)} Z`;
  const ticks = [0, 0.5, 1].map((t) => min + t * (max - min));
  const every = Math.ceil(points.length / 8);
  const h = hover !== null ? points[hover] : null;

  return (
    <div>
      <div className="mb-1 h-5 text-[13px] text-[var(--text-secondary)]" aria-live="polite">
        {h ? <><strong className="text-[var(--text)]">{monthLabel(h.month)}</strong>: {full(h.value)} {unit}</> : 'Hover a point for the exact figure.'}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Monthly trend">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={L} x2={W - Rt} y1={y(t)} y2={y(t)} stroke="var(--border)" strokeDasharray="3 4" />
            <text x={L - 6} y={y(t) + 4} textAnchor="end" fontSize="10" fill="var(--text-muted)">{compact(t)}</text>
          </g>
        ))}
        <path d={area} fill="var(--accent)" opacity={0.12} />
        <path d={line} fill="none" stroke="var(--accent)" strokeWidth={2.2} strokeLinejoin="round" />
        {points.map((p, i) => (
          <g key={p.month}>
            {i % every === 0 && (
              <text x={x(i)} y={H - 8} textAnchor="middle" fontSize="10" fill="var(--text-muted)">{monthLabel(p.month)}</text>
            )}
            <circle cx={x(i)} cy={y(p.value)} r={hover === i ? 5 : 3.2} fill="var(--accent)" />
            <rect
              x={x(i) - 14} y={T} width={28} height={H - T - B} fill="transparent"
              onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}
            >
              <title>{`${monthLabel(p.month)}: ${full(p.value)} ${unit}`}</title>
            </rect>
          </g>
        ))}
      </svg>
    </div>
  );
}
