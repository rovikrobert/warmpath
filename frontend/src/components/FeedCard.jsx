import { useState } from 'react';
import { Link } from 'react-router-dom';
import { feed as feedApi } from '../api/client';
import KeevsAvatar from './KeevsAvatar';

/**
 * Feed item icons mapped to item_type.
 * Each returns an SVG element matching the design system.
 */
const ICONS = {
  job_alert: (
    <svg className="h-5 w-5 text-emerald-400" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 14.15v4.25c0 1.094-.787 2.036-1.872 2.18-2.087.277-4.216.42-6.378.42s-4.291-.143-6.378-.42c-1.085-.144-1.872-1.086-1.872-2.18v-4.25m16.5 0a2.18 2.18 0 0 0 .75-1.661V8.706c0-1.081-.768-2.015-1.837-2.175a48.114 48.114 0 0 0-3.413-.387m4.5 8.006c-.194.165-.42.295-.673.38A23.978 23.978 0 0 1 12 15.75c-2.648 0-5.195-.429-7.577-1.22a2.016 2.016 0 0 1-.673-.38m0 0A2.18 2.18 0 0 1 3 12.489V8.706c0-1.081.768-2.015 1.837-2.175a48.111 48.111 0 0 1 3.413-.387m7.5 0V5.25A2.25 2.25 0 0 0 13.5 3h-3a2.25 2.25 0 0 0-2.25 2.25v.894m7.5 0a48.667 48.667 0 0 0-7.5 0" />
    </svg>
  ),
  enrichment_prompt: (
    <svg className="h-5 w-5 text-amber-400" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 5.25h.008v.008H12v-.008Z" />
    </svg>
  ),
  outcome_check: (
    <svg className="h-5 w-5 text-blue-400" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
    </svg>
  ),
  marketplace_signal: (
    <svg className="h-5 w-5 text-purple-400" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M18 18.72a9.094 9.094 0 0 0 3.741-.479 3 3 0 0 0-4.682-2.72m.94 3.198.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0 1 12 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 0 1 6 18.719m12 0a5.971 5.971 0 0 0-.941-3.197m0 0A5.995 5.995 0 0 0 12 12.75a5.995 5.995 0 0 0-5.058 2.772m0 0a3 3 0 0 0-4.681 2.72 8.986 8.986 0 0 0 3.74.477m.94-3.197a5.971 5.971 0 0 0-.94 3.197M15 6.75a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm6 3a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Zm-13.5 0a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Z" />
    </svg>
  ),
  follow_up_nudge: (
    <svg className="h-5 w-5 text-rose-400" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6 9v.75a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 0 1-5.714 0m5.714 0a3 3 0 1 1-5.714 0" />
    </svg>
  ),
  network_insight: (
    <svg className="h-5 w-5 text-cyan-400" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 3v11.25A2.25 2.25 0 0 0 6 16.5h2.25M3.75 3h-1.5m1.5 0h16.5m0 0h1.5m-1.5 0v11.25A2.25 2.25 0 0 1 18 16.5h-2.25m-7.5 0h7.5m-7.5 0-1 3m8.5-3 1 3m0 0 .5 1.5m-.5-1.5h-9.5m0 0-.5 1.5" />
    </svg>
  ),
};

const PRIORITY_COLORS = {
  high: 'border-l-amber-500',     // priority >= 80
  medium: 'border-l-slate-500',    // priority >= 50
  low: 'border-l-slate-700',       // priority < 50
};

function getPriorityColor(priority) {
  if (priority >= 80) return PRIORITY_COLORS.high;
  if (priority >= 50) return PRIORITY_COLORS.medium;
  return PRIORITY_COLORS.low;
}

/**
 * Enrichment prompt inline response component.
 * Renders quick-tap buttons for relationship type, would_refer, etc.
 */
export function EnrichmentActions({ item, onRespond }) {
  const meta = item.metadata || {};
  const signalType = meta.signal_type || 'relationship_type';
  const contactName = meta.contact_name || 'this contact';

  const options = signalType === 'relationship_type'
    ? [
        { label: 'Colleague', value: 'colleague' },
        { label: 'Manager', value: 'manager' },
        { label: 'Report', value: 'report' },
        { label: 'Friend', value: 'friend' },
        { label: 'Acquaintance', value: 'acquaintance' },
      ]
    : signalType === 'would_refer'
    ? [
        { label: 'Definitely', value: 'definitely' },
        { label: 'Probably', value: 'probably' },
        { label: 'Maybe', value: 'maybe' },
        { label: 'No', value: 'no' },
      ]
    : [];

  if (options.length === 0) return null;

  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {options.map((opt) => (
        <button
          key={opt.label}
          type="button"
          onClick={() => onRespond(item, signalType, opt.value)}
          className="rounded-full border border-slate-600 bg-slate-800 px-3 py-1 text-xs font-medium text-slate-300 transition hover:border-amber-500 hover:bg-amber-500/10 hover:text-amber-400"
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

/**
 * FeedCard — renders a single feed item with action, dismiss, and optional enrichment response.
 *
 * Props:
 *   item       — feed item object from the API
 *   onDismiss  — callback(id) when item is dismissed
 *   onAct      — callback(id) when action is taken
 *   compact    — boolean, renders a smaller variant for KeevsBar
 */
export default function FeedCard({ item, onDismiss, onAct, compact = false }) {
  const [dismissed, setDismissed] = useState(false);
  const [responded, setResponded] = useState(false);

  if (dismissed) return null;

  const icon = ICONS[item.item_type] || ICONS.network_insight;
  const priorityColor = getPriorityColor(item.priority);
  const isUnseen = !item.seen_at;

  const handleDismiss = async (e) => {
    e.stopPropagation();
    try {
      await feedApi.dismiss(item.id);
      setDismissed(true);
      onDismiss?.(item.id);
      window.dispatchEvent(new Event('feed-updated'));
    } catch {
      // Silently fail — item remains visible
    }
  };

  const handleAction = async () => {
    try {
      await feedApi.act(item.id);
      onAct?.(item.id);
    } catch {
      // Still navigate even if tracking fails
    }
  };

  const handleEnrichmentResponse = async (feedItem, signalType, signalValue) => {
    try {
      await feedApi.enrichmentResponse({
        feed_item_id: feedItem.id,
        contact_id: feedItem.metadata?.contact_id,
        signal_type: signalType,
        signal_value: signalValue,
      });
      setResponded(true);
    } catch {
      // TODO: surface error
    }
  };

  if (compact) {
    return (
      <div className={`flex items-start gap-2 rounded-lg border-l-2 ${priorityColor} bg-slate-800/50 px-3 py-2`}>
        <div className="mt-0.5 shrink-0">{icon}</div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-slate-200">{item.title}</p>
          {item.action_url && (
            <Link
              to={item.action_url}
              onClick={handleAction}
              className="text-xs font-medium text-amber-400 hover:text-amber-300"
            >
              {item.action_label || 'View'}
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
    );
  }

  return (
    <div
      className={`rounded-lg border border-slate-700/50 border-l-2 ${priorityColor} bg-slate-900 p-4 transition ${
        isUnseen ? 'ring-1 ring-amber-500/20' : ''
      }`}
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5 shrink-0">{icon}</div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <h3 className="text-sm font-medium text-slate-100">{item.title}</h3>
            <button
              type="button"
              onClick={handleDismiss}
              className="shrink-0 text-slate-600 hover:text-slate-400 transition"
              aria-label="Dismiss feed item"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          {item.body && (
            <p className="mt-1 text-sm text-slate-400 leading-relaxed">{item.body}</p>
          )}

          {/* Enrichment inline response */}
          {item.item_type === 'enrichment_prompt' && !responded && !item.acted_on_at && (
            <EnrichmentActions item={item} onRespond={handleEnrichmentResponse} />
          )}
          {responded && (
            <p className="mt-2 text-xs text-emerald-400">Thanks! This helps improve your matches.</p>
          )}

          {/* Action button */}
          {item.action_url && item.item_type !== 'enrichment_prompt' && (
            <div className="mt-3">
              <Link
                to={item.action_url}
                onClick={handleAction}
                className="inline-flex items-center gap-1.5 rounded-md bg-amber-500/10 px-3 py-1.5 text-xs font-medium text-amber-400 transition hover:bg-amber-500/20"
              >
                {item.action_label || 'View'}
                <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" />
                </svg>
              </Link>
            </div>
          )}

          {/* Timestamp */}
          <p className="mt-2 text-xs text-slate-600">
            {new Date(item.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
          </p>
        </div>
      </div>
    </div>
  );
}
