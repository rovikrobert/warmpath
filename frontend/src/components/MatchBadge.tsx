import { getMatchTier, getWarmTier, getFitTier, getLikelihood } from '../utils/scores';

/**
 * Unified score badge component.
 *
 * Usage:
 *   <MatchBadge score={85} />                    — match strength (default)
 *   <MatchBadge score={72} type="warm" />         — warm score
 *   <MatchBadge score={90} type="fit" />           — job fit score
 *   <MatchBadge level="high" type="likelihood" />  — referral likelihood
 */
interface MatchBadgeProps {
  score?: number;
  level?: string;
  type?: 'match' | 'warm' | 'fit' | 'likelihood';
  showScore?: boolean;
}

export default function MatchBadge({ score, level, type = 'match', showScore = false }: MatchBadgeProps) {
  let tier: { label: string; color: string };

  if (type === 'likelihood') {
    tier = getLikelihood(level);
  } else if (type === 'warm') {
    tier = getWarmTier(score ?? 0);
  } else if (type === 'fit') {
    tier = getFitTier(score ?? 0);
  } else {
    tier = getMatchTier(score ?? 0);
  }

  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${tier.color}`}>
      {tier.label}
      {showScore && score != null && (
        <span className="ml-1 opacity-70">({score})</span>
      )}
    </span>
  );
}
