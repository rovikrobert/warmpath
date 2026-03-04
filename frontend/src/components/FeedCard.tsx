import { useState } from 'react';
import { Link } from 'react-router-dom';
import { feed as feedApi } from '../api/client';
/**
 * Feed item icons mapped to item_type.
 * Each returns an SVG element matching the design system.
 */
const ICONS = {
  job_alert: (
    <svg className="h-5 w-5 text-success" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 14.15v4.25c0 1.094-.787 2.036-1.872 2.18-2.087.277-4.216.42-6.378.42s-4.291-.143-6.378-.42c-1.085-.144-1.872-1.086-1.872-2.18v-4.25m16.5 0a2.18 2.18 0 0 0 .75-1.661V8.706c0-1.081-.768-2.015-1.837-2.175a48.114 48.114 0 0 0-3.413-.387m4.5 8.006c-.194.165-.42.295-.673.38A23.978 23.978 0 0 1 12 15.75c-2.648 0-5.195-.429-7.577-1.22a2.016 2.016 0 0 1-.673-.38m0 0A2.18 2.18 0 0 1 3 12.489V8.706c0-1.081.768-2.015 1.837-2.175a48.111 48.111 0 0 1 3.413-.387m7.5 0V5.25A2.25 2.25 0 0 0 13.5 3h-3a2.25 2.25 0 0 0-2.25 2.25v.894m7.5 0a48.667 48.667 0 0 0-7.5 0" />
    </svg>
  ),
  enrichment_prompt: (
    <svg className="h-5 w-5 text-primary" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 5.25h.008v.008H12v-.008Z" />
    </svg>
  ),
  outcome_check: (
    <svg className="h-5 w-5 text-info" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
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
  intro_approval_nudge: (
    <svg className="h-5 w-5 text-success" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M6.633 10.25c.806 0 1.533-.446 2.031-1.08a9.041 9.041 0 0 1 2.861-2.4c.723-.384 1.35-.956 1.653-1.715a4.498 4.498 0 0 0 .322-1.672V2.75a.75.75 0 0 1 .75-.75 2.25 2.25 0 0 1 2.25 2.25c0 1.152-.26 2.243-.723 3.218-.266.558.107 1.282.725 1.282m0 0h3.126c1.026 0 1.945.694 2.054 1.715.045.422.068.85.068 1.285a11.95 11.95 0 0 1-2.649 7.521c-.388.482-.987.729-1.605.729H13.48c-.483 0-.964-.078-1.423-.23l-3.114-1.04a4.501 4.501 0 0 0-1.423-.23H5.904m7.594-4.277A9.041 9.041 0 0 0 16.5 10.5m-2.002-.25h3.126" />
    </svg>
  ),
  manual_send_reminder: (
    <svg className="h-5 w-5 text-sky-400" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 12 3.269 3.125A59.769 59.769 0 0 1 21.485 12 59.768 59.768 0 0 1 3.27 20.875L5.999 12Zm0 0h7.5" />
    </svg>
  ),
  network_insight: (
    <svg className="h-5 w-5 text-cyan-400" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 3v11.25A2.25 2.25 0 0 0 6 16.5h2.25M3.75 3h-1.5m1.5 0h16.5m0 0h1.5m-1.5 0v11.25A2.25 2.25 0 0 1 18 16.5h-2.25m-7.5 0h7.5m-7.5 0-1 3m8.5-3 1 3m0 0 .5 1.5m-.5-1.5h-9.5m0 0-.5 1.5" />
    </svg>
  ),
};

const PRIORITY_COLORS = {
  high: 'border-l-primary',        // priority >= 80
  medium: 'border-l-muted-foreground', // priority >= 50
  low: 'border-l-muted',           // priority < 50
};

function getPriorityColor(priority: number): string {
  if (priority >= 80) return PRIORITY_COLORS.high;
  if (priority >= 50) return PRIORITY_COLORS.medium;
  return PRIORITY_COLORS.low;
}

/**
 * Enrichment prompt inline response component.
 * Renders quick-tap buttons for relationship type, would_refer, etc.
 */
interface FeedItem {
  id: string;
  item_type: string;
  title: string;
  body?: string;
  priority: number;
  action_url?: string;
  action_label?: string;
  created_at: string;
  seen_at?: string | null;
  acted_on_at?: string | null;
  metadata?: Record<string, any>;
}

interface EnrichmentActionsProps {
  item: FeedItem;
  onRespond: (item: FeedItem, signalType: string, value: string) => Promise<void>;
}

export function EnrichmentActions({ item, onRespond }: EnrichmentActionsProps) {
  const [loading, setLoading] = useState(false);
  const meta = item.metadata || {};
  const signalType = meta.signal_type || 'relationship_type';
  const contactName = meta.contact_name || 'this contact';

  const options = signalType === 'relationship_type'
    ? [
        { label: 'Former colleague', value: 'former_colleague' },
        { label: 'Current colleague', value: 'current_colleague' },
        { label: 'Manager', value: 'manager' },
        { label: 'Friend', value: 'friend' },
        { label: 'Alumni', value: 'alumni' },
        { label: 'Other', value: 'other' },
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

  const handleClick = async (opt: { label: string; value: string }) => {
    setLoading(true);
    try {
      await onRespond(item, signalType, opt.value);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {options.map((opt) => (
        <button
          key={opt.label}
          type="button"
          disabled={loading}
          onClick={() => handleClick(opt)}
          className="rounded-full border border-border bg-muted px-3 py-1 text-xs font-medium text-secondary-foreground transition hover:border-primary hover:bg-primary/10 hover:text-primary disabled:opacity-50 disabled:cursor-not-allowed"
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
interface FeedCardProps {
  item: FeedItem;
  onDismiss?: (id: string) => void;
  onAct?: (id: string) => void;
  compact?: boolean;
}

export default function FeedCard({ item, onDismiss, onAct, compact = false }: FeedCardProps) {
  const [dismissed, setDismissed] = useState(false);
  const [responded, setResponded] = useState(false);

  if (dismissed) return null;

  const icon = ICONS[item.item_type] || ICONS.network_insight;
  const priorityColor = getPriorityColor(item.priority);
  const isUnseen = !item.seen_at;

  const handleDismiss = async (e: React.MouseEvent) => {
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
      <div className={`flex items-start gap-2 rounded-lg border-l-2 ${priorityColor} bg-muted/50 px-3 py-2`}>
        <div className="mt-0.5 shrink-0">{icon}</div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-foreground">{item.title}</p>
          {item.action_url && (
            <Link
              to={item.action_url}
              onClick={handleAction}
              className="text-xs font-medium text-primary hover:text-primary"
            >
              {item.action_label || 'View'}
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
    );
  }

  return (
    <div
      className={`rounded-lg border border-border border-l-2 ${priorityColor} bg-card p-4 transition ${
        isUnseen ? 'ring-1 ring-ring/20' : ''
      }`}
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5 shrink-0">{icon}</div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <h3 className="text-sm font-medium text-foreground">{item.title}</h3>
            <button
              type="button"
              onClick={handleDismiss}
              className="shrink-0 text-muted-foreground hover:text-muted-foreground transition"
              aria-label="Dismiss feed item"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          {item.body && (
            <p className="mt-1 text-sm text-muted-foreground leading-relaxed">{item.body}</p>
          )}

          {/* Enrichment inline response */}
          {item.item_type === 'enrichment_prompt' && !responded && !item.acted_on_at && (
            <EnrichmentActions item={item} onRespond={handleEnrichmentResponse} />
          )}
          {responded && (
            <p className="mt-2 text-xs text-success">Thanks! This helps improve your matches.</p>
          )}

          {/* Action button */}
          {item.action_url && item.item_type !== 'enrichment_prompt' && (
            <div className="mt-3">
              <Link
                to={item.action_url}
                onClick={handleAction}
                className="inline-flex items-center gap-1.5 rounded-md bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary transition hover:bg-primary/20"
              >
                {item.action_label || 'View'}
                <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" />
                </svg>
              </Link>
            </div>
          )}

          {/* Timestamp */}
          <p className="mt-2 text-xs text-muted-foreground">
            {new Date(item.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
          </p>
        </div>
      </div>
    </div>
  );
}
