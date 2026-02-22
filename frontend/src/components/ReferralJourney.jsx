import { useEffect, useState, useCallback } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  contacts as contactsApi,
  preferences as prefsApi,
  search as searchApi,
  marketplace as mpApi,
} from '../api/client';
import KeevsAvatar from './KeevsAvatar';

const CACHE_KEY = 'warmpath_referral_journey';
const DISMISSED_KEY = 'warmpath_referral_journey_dismissed';

const STAGES = [
  {
    key: 'upload',
    label: 'Upload',
    keevs:
      "Let's start by importing your LinkedIn connections. This gives me your network map — I'll use it to find warm paths to your target companies.",
    cta: 'Upload CSV',
    href: '/contacts',
  },
  {
    key: 'preferences',
    label: 'Preferences',
    keevs:
      "Great, your network is loaded! Now tell me what you're targeting so I can match you with the right people.",
    cta: 'Set Preferences',
    href: '/settings?tab=profile',
  },
  {
    key: 'search',
    label: 'Search',
    keevs:
      "You're all set up. Pick a company you'd love to work at and I'll find people who can refer you.",
    cta: 'Find Referrals',
    href: '/referrals',
  },
  {
    key: 'match',
    label: 'Match',
    keevs:
      "You've got matches! Review them and look for the warmest connection — that's your best bet for a referral.",
    cta: 'View Results',
    href: '/referrals',
  },
  {
    key: 'request',
    label: 'Request',
    keevs:
      "Found someone promising? Request an intro and I'll help you draft the perfect referral message.",
    cta: 'Request Intro',
    href: '/referrals',
  },
];

function getCache() {
  try {
    return JSON.parse(localStorage.getItem(CACHE_KEY) || '{}');
  } catch {
    return {};
  }
}

function setCache(data) {
  localStorage.setItem(CACHE_KEY, JSON.stringify(data));
}

/**
 * ReferralJourney — guided 5-stage journey from onboarding to first referral request.
 *
 * Props:
 *   variant — "full" (coach page) | "compact" (KeevsBar breadcrumb)
 */
export default function ReferralJourney({ variant = 'full' }) {
  const location = useLocation();
  const [completed, setCompleted] = useState(getCache);
  const [loading, setLoading] = useState(true);
  const [dismissed, setDismissed] = useState(
    () => localStorage.getItem(DISMISSED_KEY) === 'true',
  );

  const checkStages = useCallback(async () => {
    const done = { ...getCache() };

    try {
      const [contactsRes, prefsRes, searchRes, requestsRes] =
        await Promise.allSettled([
          contactsApi.list({ per_page: 1 }),
          prefsApi.getJob(),
          searchApi.list(),
          mpApi.myRequests(),
        ]);

      // Upload: has at least 1 contact
      if (contactsRes.status === 'fulfilled') {
        const total =
          contactsRes.value?.meta?.total ??
          contactsRes.value?.data?.length ??
          0;
        done.upload = total > 0;
      }

      // Preferences: target_role set
      done.preferences =
        prefsRes.status === 'fulfilled' &&
        !!prefsRes.value?.data?.target_role;

      // Search: has at least 1 search request
      if (searchRes.status === 'fulfilled') {
        const searches = searchRes.value?.data || [];
        done.search = searches.length > 0;
        // Match: at least 1 search has results
        done.match = searches.some(
          (s) => (s.result_count ?? s.results_count ?? 0) > 0,
        );
        // Store last search ID for CTA link
        if (searches.length > 0) {
          done._lastSearchId = searches[0].id;
        }
      }

      // Request: has at least 1 intro request
      if (requestsRes.status === 'fulfilled') {
        const requests = requestsRes.value?.data || [];
        done.request = requests.length > 0;
      }
    } catch {
      // Don't block UI on API failure
    }

    setCache(done);
    setCompleted(done);
    setLoading(false);
  }, []);

  useEffect(() => {
    if (dismissed) {
      setLoading(false);
      return;
    }
    checkStages();
  }, [checkStages, dismissed]);

  // Listen for journey-updated events (dispatched by other pages)
  useEffect(() => {
    const handler = () => checkStages();
    window.addEventListener('journey-updated', handler);
    return () => window.removeEventListener('journey-updated', handler);
  }, [checkStages]);

  // Find current stage (first incomplete)
  const currentIndex = STAGES.findIndex((s) => !completed[s.key]);
  const allComplete = currentIndex === -1;

  if (loading || dismissed) return null;
  if (allComplete && variant === 'compact') return null;

  if (variant === 'compact') {
    return <CompactBreadcrumb stages={STAGES} completed={completed} currentIndex={currentIndex} />;
  }

  return (
    <FullJourney
      stages={STAGES}
      completed={completed}
      currentIndex={currentIndex}
      allComplete={allComplete}
      onDismiss={() => {
        setDismissed(true);
        localStorage.setItem(DISMISSED_KEY, 'true');
      }}
    />
  );
}

/* ------------------------------------------------------------------ */
/* Full variant — rendered on /coach                                   */
/* ------------------------------------------------------------------ */

function FullJourney({ stages, completed, currentIndex, allComplete, onDismiss }) {
  if (allComplete) {
    return (
      <div className="mb-4 rounded-xl border border-emerald-500/20 bg-slate-900 p-5">
        <div className="flex items-start gap-4">
          <KeevsAvatar size="lg" />
          <div className="flex-1">
            <h2 className="text-sm font-semibold text-emerald-400">
              You sent your first referral request!
            </h2>
            <p className="mt-1 text-sm text-slate-300">
              That's already more than most job seekers ever do. I'll keep you
              posted on the response. In the meantime, want to search another
              company?
            </p>
            <div className="mt-3 flex gap-2">
              <Link
                to="/referrals"
                className="rounded-md bg-amber-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-400"
              >
                Search another company
              </Link>
              <button
                type="button"
                onClick={onDismiss}
                className="rounded-md border border-slate-700 px-3 py-1.5 text-xs text-slate-400 hover:text-slate-300"
              >
                Dismiss
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const current = stages[currentIndex];
  const href =
    current.key === 'match' && completed._lastSearchId
      ? `/referrals/${completed._lastSearchId}`
      : current.href;

  return (
    <div
      className="mb-4 rounded-xl border border-slate-700/50 bg-slate-900"
      role="region"
      aria-label="Your referral journey"
    >
      {/* Breadcrumb trail */}
      <div className="border-b border-slate-700/50 px-5 py-3">
        <div className="flex items-center justify-between">
          <p className="text-xs font-medium text-slate-400">
            Your path to first referral
          </p>
          <span className="text-xs text-slate-500">
            {stages.filter((s) => completed[s.key]).length} of {stages.length}
          </span>
        </div>
        <div className="mt-2 flex items-center gap-1">
          {stages.map((stage, i) => {
            const isDone = !!completed[stage.key];
            const isCurrent = i === currentIndex;
            return (
              <div key={stage.key} className="flex items-center gap-1 flex-1">
                <div className="flex flex-col items-center flex-1">
                  <div
                    className={`h-1.5 w-full rounded-full transition-all ${
                      isDone
                        ? 'bg-emerald-500'
                        : isCurrent
                          ? 'bg-amber-500'
                          : 'bg-slate-700'
                    }`}
                  />
                  <span
                    className={`mt-1 text-[10px] ${
                      isDone
                        ? 'text-emerald-400'
                        : isCurrent
                          ? 'text-amber-400 font-medium'
                          : 'text-slate-600'
                    }`}
                  >
                    {stage.label}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Current stage — Keevs prompt */}
      <div className="flex items-start gap-4 px-5 py-4">
        <KeevsAvatar size="lg" pulse />
        <div className="flex-1 min-w-0">
          <p className="text-sm text-slate-300 leading-relaxed">
            {current.keevs}
          </p>
          <Link
            to={href}
            className="mt-3 inline-flex rounded-md bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-400 transition-colors"
          >
            {current.cta}
          </Link>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Compact variant — rendered in KeevsBar                              */
/* ------------------------------------------------------------------ */

function CompactBreadcrumb({ stages, completed, currentIndex }) {
  const current = stages[currentIndex];
  const href =
    current.key === 'match' && completed._lastSearchId
      ? `/referrals/${completed._lastSearchId}`
      : current.href;

  return (
    <div className="flex items-center gap-3 rounded-lg border border-slate-700/50 bg-slate-900/80 px-4 py-2.5">
      <KeevsAvatar size="sm" />
      <div className="flex items-center gap-1.5 flex-1 min-w-0">
        {stages.map((stage, i) => {
          const isDone = !!completed[stage.key];
          const isCurrent = i === currentIndex;
          return (
            <div key={stage.key} className="flex items-center gap-1.5">
              {i > 0 && (
                <svg
                  className={`h-3 w-3 shrink-0 ${isDone ? 'text-emerald-500' : 'text-slate-700'}`}
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth="2"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="m8.25 4.5 7.5 7.5-7.5 7.5"
                  />
                </svg>
              )}
              <span
                className={`text-xs whitespace-nowrap ${
                  isDone
                    ? 'text-emerald-400 line-through'
                    : isCurrent
                      ? 'text-amber-400 font-medium'
                      : 'text-slate-600'
                }`}
              >
                {stage.label}
              </span>
            </div>
          );
        })}
      </div>
      <Link
        to={href}
        className="shrink-0 rounded-md bg-amber-500 px-2.5 py-1 text-xs font-medium text-white hover:bg-amber-400"
      >
        {current.cta}
      </Link>
    </div>
  );
}
