import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { feed as feedApi } from '../api/client';
import KeevsAvatar from './KeevsAvatar';
import FeedCard from './FeedCard';

/**
 * Route-to-feed-type mapping.
 * Determines which feed item type is most relevant on each page.
 */
const ROUTE_FEED_TYPE = {
  '/contacts': 'enrichment_prompt',
  '/search': 'marketplace_signal',
  '/matches': 'follow_up_nudge',
  '/applications': 'outcome_check',
  '/coach': null, // Coach page has its own feed section
  '/marketplace': 'marketplace_signal',
  '/dashboard': 'network_insight',
};

function getRelevantType(pathname) {
  // Exact match first
  if (ROUTE_FEED_TYPE[pathname] !== undefined) return ROUTE_FEED_TYPE[pathname];
  // Prefix match
  for (const [route, type] of Object.entries(ROUTE_FEED_TYPE)) {
    if (pathname.startsWith(route)) return type;
  }
  return 'job_alert'; // Default on unknown pages
}

/**
 * KeevsBar — thin contextual nudge bar that appears at the top of main content.
 *
 * Shows one relevant feed item based on the current page. Collapsed by default
 * into a single line with the Keevs avatar. Clicking expands to show the full
 * feed card with action/dismiss. Auto-hides on coach page (which has its own feed).
 *
 * Props:
 *   className — extra wrapper classes
 */
export default function KeevsBar({ className = '' }) {
  const location = useLocation();
  const [item, setItem] = useState(null);
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [dismissed, setDismissed] = useState(false);

  const feedType = getRelevantType(location.pathname);

  useEffect(() => {
    // Don't show on coach page (has its own feed) or during onboarding
    if (feedType === null || location.pathname.startsWith('/onboarding')) {
      setItem(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setDismissed(false);
    setExpanded(false);

    feedApi.list({ item_type: feedType, limit: 1 })
      .then((res) => {
        if (!cancelled) {
          setItem(res.data?.[0] || null);
        }
      })
      .catch(() => {
        if (!cancelled) setItem(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [location.pathname, feedType]);

  // Mark as seen when expanded
  useEffect(() => {
    if (expanded && item && !item.seen_at) {
      feedApi.markSeen(item.id).catch(() => {});
    }
  }, [expanded, item]);

  // Don't render anything if no relevant item or on coach page
  if (loading || !item || dismissed || feedType === null) return null;

  return (
    <div className={`mb-4 ${className}`}>
      {!expanded ? (
        /* Collapsed — single line nudge */
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="flex w-full items-center gap-3 rounded-lg border border-slate-700/50 bg-slate-900/80 px-4 py-2.5 text-left transition hover:border-amber-500/30 hover:bg-slate-900"
        >
          <KeevsAvatar size="sm" />
          <p className="min-w-0 flex-1 truncate text-sm text-slate-300">
            <span className="font-medium text-amber-400">Keevs:</span>{' '}
            {item.title}
          </p>
          <svg className="h-4 w-4 shrink-0 text-slate-500" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
          </svg>
        </button>
      ) : (
        /* Expanded — full feed card with Keevs branding */
        <div className="rounded-lg border border-amber-500/20 bg-slate-900/80 p-3">
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <KeevsAvatar size="sm" />
              <span className="text-xs font-medium text-amber-400">Keevs says</span>
            </div>
            <button
              type="button"
              onClick={() => setExpanded(false)}
              className="text-slate-500 hover:text-slate-300 transition"
              aria-label="Collapse"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 15.75 7.5-7.5 7.5 7.5" />
              </svg>
            </button>
          </div>
          <FeedCard
            item={item}
            onDismiss={() => setDismissed(true)}
          />
        </div>
      )}
    </div>
  );
}
