import { useEffect, useState } from 'react';
import { contacts as contactsApi } from '../api/client';

// Milestone thresholds → credits awarded (matches backend MILESTONES)
const MILESTONES = [
  { pct: 10, credits: 10 },
  { pct: 25, credits: 25 },
  { pct: 50, credits: 50 },
  { pct: 75, credits: 75 },
  { pct: 100, credits: 100 },
];

interface EnrichmentData {
  total_contacts: number;
  enriched_contacts: number;
  percentage: number;
  next_milestone: number | null;
  credits_at_next_milestone: number | null;
  milestones_claimed: Array<{ milestone_value: number }>;
}

interface EnrichmentProgressProps {
  compact?: boolean;
}

export default function EnrichmentProgress({ compact = false }: EnrichmentProgressProps) {
  const [data, setData] = useState<EnrichmentData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    contactsApi.enrichmentProgress()
      .then((res) => setData(res.data))
      .catch((err) => { console.error('EnrichmentProgress: failed to load enrichment progress', err); })
      .finally(() => setLoading(false));
  }, []);

  if (loading || !data || data.total_contacts === 0) return null;

  const { total_contacts, enriched_contacts, percentage, next_milestone, credits_at_next_milestone, milestones_claimed } = data;
  const claimedValues = new Set((milestones_claimed || []).map((m) => m.milestone_value));
  const remaining = next_milestone
    ? Math.ceil((next_milestone / 100) * total_contacts) - enriched_contacts
    : 0;

  if (compact) {
    return (
      <div className="flex items-center gap-3">
        <div className="h-1.5 flex-1 rounded-full bg-muted/50 overflow-hidden">
          <div
            className="h-full rounded-full bg-primary transition-all duration-500"
            style={{ width: `${Math.min(percentage, 100)}%` }}
          />
        </div>
        <span className="shrink-0 text-xs text-muted-foreground">
          {Math.round(percentage)}% enriched
          {next_milestone && ` \u00b7 ${remaining} more for ${credits_at_next_milestone} credits`}
        </span>
      </div>
    );
  }

  return (
    <div className="mb-4 rounded-lg border border-primary/20 bg-card/80 p-4">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-medium text-foreground">
          Enrichment Progress
        </h3>
        <span className="text-xs text-muted-foreground">
          {enriched_contacts} of {total_contacts} contacts ({Math.round(percentage)}%)
        </span>
      </div>

      {/* Progress bar with milestone markers */}
      <div className="relative mb-3">
        <div className="h-2.5 rounded-full bg-muted/50 overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-primary to-primary/80 transition-all duration-500"
            style={{ width: `${Math.min(percentage, 100)}%` }}
            role="progressbar"
            aria-valuenow={Math.round(percentage)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`${Math.round(percentage)}% of contacts enriched`}
          />
        </div>
        {/* Milestone markers */}
        <div className="absolute inset-0 flex">
          {MILESTONES.filter((m) => m.pct < 100).map((m) => (
            <div
              key={m.pct}
              className="absolute top-0 h-2.5"
              style={{ left: `${m.pct}%` }}
            >
              <div className={`h-full w-0.5 ${claimedValues.has(m.pct) ? 'bg-primary/60' : 'bg-muted-foreground'}`} />
            </div>
          ))}
        </div>
      </div>

      {/* Milestone reward badges */}
      <div className="mb-2">
        <p className="mb-1 text-xs text-muted-foreground">Milestone rewards</p>
        <div className="flex gap-1.5">
          {MILESTONES.map((m) => (
            <span
              key={m.pct}
              title={claimedValues.has(m.pct) ? `${m.credits} credits claimed` : `Earn ${m.credits} credits at ${m.pct}%`}
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                claimedValues.has(m.pct)
                  ? 'bg-primary/20 text-primary'
                  : percentage >= m.pct
                    ? 'bg-emerald-500/20 text-emerald-400'
                    : 'bg-muted/50 text-muted-foreground'
              }`}
            >
              {m.pct}%{claimedValues.has(m.pct) ? ' \u2713' : ` \u2192 ${m.credits}cr`}
            </span>
          ))}
        </div>
      </div>

      {/* Motivational text */}
      {next_milestone && remaining > 0 && (
        <p className="text-xs text-muted-foreground">
          Tag {remaining} more {remaining === 1 ? 'contact' : 'contacts'} to earn{' '}
          <span className="font-medium text-primary">{credits_at_next_milestone} credits</span>
        </p>
      )}
      {percentage >= 100 && (
        <p className="text-xs text-emerald-400">
          All contacts enriched! Your referral matches are at maximum accuracy.
        </p>
      )}
    </div>
  );
}
