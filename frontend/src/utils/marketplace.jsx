/**
 * Display utilities for marketplace listing fields.
 *
 * Maps backend enum strings (role_level, warm_score_range) to
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

// -- Connection Strength (warm_score_range) ------------------------------------

export const WARM_RANGE_MAP = {
  high:   { label: 'Strong',   color: 'bg-emerald-500/10 text-emerald-400' },
  medium: { label: 'Moderate', color: 'bg-amber-500/10 text-amber-400' },
  low:    { label: 'Weak',     color: 'bg-slate-700/50 text-slate-400' },
};

export function getWarmRangeDisplay(raw) {
  return WARM_RANGE_MAP[raw] || { label: raw || 'Unknown', color: 'bg-slate-700/50 text-slate-400' };
}

// -- Reusable pill component --------------------------------------------------

/**
 * Renders a colored pill badge for marketplace fields.
 *
 * Usage:
 *   <MarketplaceBadge value="senior" type="role" />
 *   <MarketplaceBadge value="high" type="strength" />
 */
export function MarketplaceBadge({ value, type }) {
  const display = type === 'role' ? getRoleLevelDisplay(value) : getWarmRangeDisplay(value);
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${display.color}`}>
      {display.label}
    </span>
  );
}
