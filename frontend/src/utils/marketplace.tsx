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
  mid:      { label: 'Mid-Level', color: 'bg-primary/10 text-primary' },
  junior:   { label: 'Junior',    color: 'bg-muted/50 text-muted-foreground' },
};

export function getRoleLevelDisplay(raw: string) {
  return ROLE_LEVEL_MAP[raw] || { label: raw || 'Unknown', color: 'bg-muted/50 text-muted-foreground' };
}

// -- Connection Strength (warm_score_range) ------------------------------------

export const WARM_RANGE_MAP = {
  high:   { label: 'Strong',   color: 'bg-emerald-500/10 text-emerald-400' },
  medium: { label: 'Moderate', color: 'bg-primary/10 text-primary' },
  low:    { label: 'Weak',     color: 'bg-muted/50 text-muted-foreground' },
};

export function getWarmRangeDisplay(raw: string) {
  return WARM_RANGE_MAP[raw] || { label: raw || 'Unknown', color: 'bg-muted/50 text-muted-foreground' };
}

// -- Department ---------------------------------------------------------------

export const DEPARTMENT_MAP = {
  Engineering: { label: 'Engineering', color: 'bg-blue-500/10 text-blue-400' },
  Product: { label: 'Product', color: 'bg-purple-500/10 text-purple-400' },
  Design: { label: 'Design', color: 'bg-pink-500/10 text-pink-400' },
  Marketing: { label: 'Marketing', color: 'bg-primary/10 text-primary' },
  Sales: { label: 'Sales', color: 'bg-emerald-500/10 text-emerald-400' },
  Finance: { label: 'Finance', color: 'bg-muted/50 text-muted-foreground' },
  Operations: { label: 'Operations', color: 'bg-muted/50 text-muted-foreground' },
  'HR / People': { label: 'HR', color: 'bg-muted/50 text-muted-foreground' },
  Legal: { label: 'Legal', color: 'bg-muted/50 text-muted-foreground' },
  'Data / Analytics': { label: 'Data', color: 'bg-cyan-500/10 text-cyan-400' },
  'Customer Success': { label: 'CS', color: 'bg-muted/50 text-muted-foreground' },
  Executive: { label: 'Executive', color: 'bg-purple-500/10 text-purple-400' },
  Other: { label: 'Other', color: 'bg-muted/50 text-muted-foreground' },
};

export function getDepartmentDisplay(raw: string) {
  return DEPARTMENT_MAP[raw] || { label: raw || 'Unknown', color: 'bg-muted/50 text-muted-foreground' };
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
export function MarketplaceBadge({ value, type }: { value: string; type: string }) {
  const display = type === 'role' ? getRoleLevelDisplay(value)
    : type === 'department' ? getDepartmentDisplay(value)
    : getWarmRangeDisplay(value);
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${display.color}`}>
      {display.label}
    </span>
  );
}
