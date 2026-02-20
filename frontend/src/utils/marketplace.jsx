/**
 * Display utilities for marketplace listing fields.
 *
 * Maps backend enum strings (role_level, warm_sco[RESEND_KEY_REDACTED]) to
 * human-readable labels with Tailwind color classes that match
 * the existing MatchBadge / ScoreExplainer visual language.
 */

// -- Role Level ---------------------------------------------------------------

export const ROLE_LEVEL_MAP = {
  c_suite:  { label: 'C-Suite',   color: 'bg-purple-500/10 text-purple-400' },
  vp:       { label: 'VP',        color: 'bg-purple-500/10 text-purple-400' },
  director: { label: 'Director',  color: 'bg-blue-500/10 text-blue-400' },
  lead:     { label: 'Lead',      color: 'bg-blue-500/10 text-blue-400' },
  senior:   { label: 'Senior',    color: 'bg-emerald-500/10 text-emerald-400' },
  mid:      { label: 'Mid-Level', color: 'bg-amber-500/10 text-amber-400' },
  junior:   { label: 'Junior',    color: 'bg-slate-700/50 text-slate-400' },
};

export function getRoleLevelDisplay(raw) {
  return ROLE_LEVEL_MAP[raw] || { label: raw || 'Unknown', color: 'bg-slate-700/50 text-slate-400' };
}

// -- Connection Strength (warm_sco[RESEND_KEY_REDACTED]) ------------------------------------

export const WARM_RANGE_MAP = {
  high:   { label: 'Strong',   color: 'bg-emerald-500/10 text-emerald-400' },
  medium: { label: 'Moderate', color: 'bg-amber-500/10 text-amber-400' },
  low:    { label: 'Weak',     color: 'bg-slate-700/50 text-slate-400' },
};

export function getWarmRangeDisplay(raw) {
  return WARM_RANGE_MAP[raw] || { label: raw || 'Unknown', color: 'bg-slate-700/50 text-slate-400' };
}

// -- Department ---------------------------------------------------------------

export const DEPARTMENT_MAP = {
  Engineering: { label: 'Engineering', color: 'bg-blue-500/10 text-blue-400' },
  Product: { label: 'Product', color: 'bg-purple-500/10 text-purple-400' },
  Design: { label: 'Design', color: 'bg-pink-500/10 text-pink-400' },
  Marketing: { label: 'Marketing', color: 'bg-amber-500/10 text-amber-400' },
  Sales: { label: 'Sales', color: 'bg-emerald-500/10 text-emerald-400' },
  Finance: { label: 'Finance', color: 'bg-slate-700/50 text-slate-400' },
  Operations: { label: 'Operations', color: 'bg-slate-700/50 text-slate-400' },
  'HR / People': { label: 'HR', color: 'bg-slate-700/50 text-slate-400' },
  Legal: { label: 'Legal', color: 'bg-slate-700/50 text-slate-400' },
  'Data / Analytics': { label: 'Data', color: 'bg-cyan-500/10 text-cyan-400' },
  'Customer Success': { label: 'CS', color: 'bg-slate-700/50 text-slate-400' },
  Executive: { label: 'Executive', color: 'bg-purple-500/10 text-purple-400' },
  Other: { label: 'Other', color: 'bg-slate-700/50 text-slate-400' },
};

export function getDepartmentDisplay(raw) {
  return DEPARTMENT_MAP[raw] || { label: raw || 'Unknown', color: 'bg-slate-700/50 text-slate-400' };
}

// -- Reusable pill component --------------------------------------------------

/**
 * Renders a colored pill badge for marketplace fields.
 *
 * Usage:
 *   <MarketplaceBadge value="senior" type="role" />
 *   <MarketplaceBadge value="Engineering" type="department" />
 *   <MarketplaceBadge value="high" type="strength" />
 */
export function MarketplaceBadge({ value, type }) {
  const display = type === 'role' ? getRoleLevelDisplay(value)
    : type === 'department' ? getDepartmentDisplay(value)
    : getWarmRangeDisplay(value);
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${display.color}`}>
      {display.label}
    </span>
  );
}
