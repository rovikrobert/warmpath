import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { feed as feedApi } from '../api/client';
import { useAuth } from '../context/AuthContext';
import KeevsAvatar from './KeevsAvatar';
import TrebAvatar from './TrebAvatar';

/**
 * Map current route to the most relevant feed item type.
 * null = suppress bar on this route.
 */
const ROUTE_FEED_TYPE = {
  '/coach': null,
  '/notifications': null,
  '/contacts': 'enrichment_prompt',
  '/referrals': 'marketplace_signal',
  '/applications': 'outcome_check',
  '/marketplace': 'marketplace_signal',
  '/settings': null,
  '/credits': null,
};

const TREB_ROUTES = ['/marketplace', '/settings'];

/**
 * Static seed nudges for first-session users (no feed items yet).
 * Keyed by route prefix → { title, action_label, action_url }.
 * Intent-specific overrides via `_nh` suffix for share_network users.
 */
const SEED_NUDGES = {
  '/contacts': {
    title: 'Upload your LinkedIn CSV to discover warm paths at your target companies.',
    action_label: 'Upload CSV',
    action_url: '/contacts',
  },
  '/contacts_nh': {
    title: 'Your imported connections are here. Review and manage what you share on the marketplace.',
    action_label: 'Manage sharing',
    action_url: '/settings',
  },
  '/referrals': {
    title: 'Search for people at your target companies — we\'ll find warm introductions.',
    action_label: 'Start a search',
    action_url: '/referrals',
  },
  '/applications': {
    title: 'Track your applications here. Referred applications convert 10x better than cold ones.',
    action_label: 'Find referrals',
    action_url: '/referrals',
  },
  '/marketplace': {
    title: 'Browse the marketplace to find connections at companies you\'re targeting.',
    action_label: 'Explore',
    action_url: '/marketplace',
  },
};

interface FeedItemCompact {
  id: string;
  item_type: string;
  title: string;
  action_url?: string;
  action_label?: string;
}

function getRelevantType(pathname: string): string | null {
  for (const [route, type] of Object.entries(ROUTE_FEED_TYPE)) {
    if (pathname.startsWith(route)) return type;
  }
  return 'job_alert';
}

function getBarPersona(intent: string | undefined, pathname: string): 'keevs' | 'treb' {
  if (intent === 'share_network') {
    return 'treb';
  }
  if (intent === 'find_referrals') {
    return 'keevs';
  }
  // explore users: route determines persona
  for (const route of TREB_ROUTES) {
    if (pathname.startsWith(route)) return 'treb';
  }
  return 'keevs';
}

/**
 * KeevsBar — contextual nudge bar that shows the most relevant feed item
 * for the current page. Suppressed on /coach, /settings, /credits.
 */
export default function KeevsBar() {
  const [item, setItem] = useState<FeedItemCompact | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const location = useLocation();
  const { user } = useAuth();
  const isBeta = import.meta.env.VITE_BETA_MODE === 'true';
  // Mobile: above bottom tab bar (bottom-20); beta adds feedback FAB so go higher (bottom-36)
  // Desktop: bottom-4 default; beta shifts above feedback FAB (bottom-20)
  const bottomClass = isBeta
    ? 'bottom-36 lg:bottom-20'
    : 'bottom-20 lg:bottom-4';

  const relevantType = getRelevantType(location.pathname);

  // Suppress on certain pages
  if (relevantType === null) return null;

  const persona = getBarPersona(user?.intent, location.pathname);
  const Avatar = persona === 'treb' ? TrebAvatar : KeevsAvatar;
  const personaName = persona === 'treb' ? 'Treb' : 'Keevs';
  const accentClass = persona === 'treb' ? 'text-teal-400' : 'text-primary';

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const resp = await feedApi.list({ limit: 5, exclude_type: 'enrichment_prompt' });
        const items = resp?.data || [];
        const match = items.find((i) => i.item_type === relevantType) || items[0];
        if (!cancelled && match) {
          setItem(match);
          return;
        }
      } catch {
        // fall through to seed nudge
      }
      // No feed items — use seed nudge for first-session users
      if (!cancelled) {
        const route = Object.keys(SEED_NUDGES)
          .filter((k) => !k.includes('_'))
          .find((k) => location.pathname.startsWith(k));
        if (route) {
          const nhKey = `${route}_nh`;
          const seed = (user?.intent === 'share_network' && SEED_NUDGES[nhKey])
            || SEED_NUDGES[route];
          if (seed) setItem({ id: '__seed', ...seed });
        }
      }
    }
    load();
    return () => { cancelled = true; };
  }, [relevantType, location.pathname, user?.intent]);

  useEffect(() => {
    setDismissed(false);
    setExpanded(false);
  }, [location.pathname]);

  if (!item || dismissed) return null;

  const handleDismiss = async () => {
    if (item.id === '__seed') {
      setDismissed(true);
      return;
    }
    try {
      await feedApi.dismiss(item.id);
      setDismissed(true);
      window.dispatchEvent(new Event('feed-updated'));
    } catch { /* keep visible */ }
  };

  if (!expanded) {
    return (
      <div className={`fixed ${bottomClass} right-4 z-40`}>
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="group flex items-center gap-2 rounded-full border border-border bg-card px-3 py-2 shadow-lg transition hover:border-border"
          aria-label={`${personaName} has a suggestion`}
        >
          <Avatar size="sm" pulse />
          <span className={`text-xs font-medium ${accentClass}`}>{personaName} says...</span>
        </button>
      </div>
    );
  }

  return (
    <div className={`fixed ${bottomClass} right-4 z-40 w-80 rounded-lg border border-border bg-card p-3 shadow-xl`}>
      <div className="flex items-start gap-2">
        <Avatar size="sm" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-foreground leading-snug">{item.title}</p>
          {item.action_url && (
            <Link
              to={item.action_url}
              className={`mt-1 inline-block text-xs font-medium ${accentClass} hover:opacity-80`}
            >
              {item.action_label || 'View'} →
            </Link>
          )}
        </div>
        <button
          type="button"
          onClick={handleDismiss}
          className="shrink-0 text-muted-foreground hover:text-muted-foreground"
          aria-label="Dismiss"
        >
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>
  );
}
