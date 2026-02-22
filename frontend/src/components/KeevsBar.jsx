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
  '/contacts': 'enrichment_prompt',
  '/referrals': 'marketplace_signal',
  '/applications': 'outcome_check',
  '/marketplace': 'marketplace_signal',
  '/settings': null,
  '/credits': null,
};

const TREB_ROUTES = ['/marketplace', '/settings'];

function getRelevantType(pathname) {
  for (const [route, type] of Object.entries(ROUTE_FEED_TYPE)) {
    if (pathname.startsWith(route)) return type;
  }
  return 'job_alert';
}

function getBarPersona(intent, pathname) {
  if (intent === 'sha[RESEND_KEY_REDACTED]') {
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
  const [item, setItem] = useState(null);
  const [dismissed, setDismissed] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const location = useLocation();
  const { user } = useAuth();

  const relevantType = getRelevantType(location.pathname);

  // Suppress on certain pages
  if (relevantType === null) return null;

  const persona = getBarPersona(user?.intent, location.pathname);
  const Avatar = persona === 'treb' ? TrebAvatar : KeevsAvatar;
  const personaName = persona === 'treb' ? 'Treb' : 'Keevs';
  const accentClass = persona === 'treb' ? 'text-teal-400' : 'text-amber-400';

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const resp = await feedApi.list({ limit: 5, unseen_only: true });
        const items = resp?.data?.items || [];
        const match = items.find((i) => i.item_type === relevantType) || items[0];
        if (!cancelled && match) setItem(match);
      } catch {
        // silently fail
      }
    }
    load();
    return () => { cancelled = true; };
  }, [relevantType]);

  useEffect(() => {
    setDismissed(false);
    setExpanded(false);
  }, [location.pathname]);

  if (!item || dismissed) return null;

  const handleDismiss = async () => {
    try {
      await feedApi.dismiss(item.id);
      setDismissed(true);
      window.dispatchEvent(new Event('feed-updated'));
    } catch { /* keep visible */ }
  };

  if (!expanded) {
    return (
      <div className="fixed bottom-4 right-4 z-40">
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="group flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900 px-3 py-2 shadow-lg transition hover:border-slate-600"
          aria-label={`${personaName} has a suggestion`}
        >
          <Avatar size="sm" pulse />
          <span className={`text-xs font-medium ${accentClass}`}>{personaName} says...</span>
        </button>
      </div>
    );
  }

  return (
    <div className="fixed bottom-4 right-4 z-40 w-80 rounded-lg border border-slate-700 bg-slate-900 p-3 shadow-xl">
      <div className="flex items-start gap-2">
        <Avatar size="sm" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-slate-200 leading-snug">{item.title}</p>
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
          className="shrink-0 text-slate-600 hover:text-slate-400"
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
