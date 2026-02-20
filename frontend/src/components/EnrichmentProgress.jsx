import { useEffect, useState } from 'react';
import { contacts as contactsApi } from '../api/client';

const MILESTONES = [10, 25, 50, 75, 100];

export default function EnrichmentProgress({ compact = false }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    contactsApi.enrichmentProgress()
      .then((res) => setData(res.data))
      .catch(() => {})
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
        <div className="h-1.5 flex-1 rounded-full bg-slate-700/50 overflow-hidden">
          <div
            className="h-full rounded-full bg-amber-500 transition-all duration-500"
            style={{ width: `${Math.min(percentage, 100)}%` }}
          />
        </div>
        <span className="shrink-0 text-xs text-slate-400">
          {Math.round(percentage)}% enriched
          {next_milestone && ` \u00b7 ${remaining} more for ${credits_at_next_milestone} credits`}
        </span>
      </div>
    );
  }

  return (
    <div className="mb-4 rounded-lg border border-amber-500/20 bg-slate-900/80 p-4">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-50">
          Enrichment Progress
        </h3>
        <span className="text-xs text-slate-400">
          {enriched_contacts} of {total_contacts} contacts ({Math.round(percentage)}%)
        </span>
      </div>

      {/* Progress bar with milestone markers */}
      <div className="relative mb-3">
        <div className="h-2.5 rounded-full bg-slate-700/50 overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-amber-500 to-amber-400 transition-all duration-500"
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
          {MILESTONES.filter((m) => m < 100).map((m) => (
            <div
              key={m}
              className="absolute top-0 h-2.5"
              style={{ left: `${m}%` }}
            >
              <div className={`h-full w-0.5 ${claimedValues.has(m) ? 'bg-amber-300' : 'bg-slate-600'}`} />
            </div>
          ))}
        </div>
      </div>

      {/* Milestone badges */}
      <div className="mb-2 flex gap-1.5">
        {MILESTONES.map((m) => (
          <span
            key={m}
            className={`rounded-full px-2 py-0.5 text-xs font-medium ${
              claimedValues.has(m)
                ? 'bg-amber-500/20 text-amber-400'
                : percentage >= m
                  ? 'bg-emerald-500/20 text-emerald-400'
                  : 'bg-slate-700/50 text-slate-500'
            }`}
          >
            {m}%{claimedValues.has(m) ? ' \u2713' : ''}
          </span>
        ))}
      </div>

      {/* Motivational text */}
      {next_milestone && remaining > 0 && (
        <p className="text-xs text-slate-400">
          Tag {remaining} more {remaining === 1 ? 'contact' : 'contacts'} to earn{' '}
          <span className="font-medium text-amber-400">{credits_at_next_milestone} credits</span>
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
