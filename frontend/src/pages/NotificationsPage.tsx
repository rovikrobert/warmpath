import { useEffect, useState } from 'react';
import { feed as feedApi } from '../api/client';
import FeedCard from '../components/FeedCard';
import noNotificationsIllustration from '../assets/illustrations/no-notifications.webp';
import useDocumentTitle from '../hooks/useDocumentTitle';

export default function NotificationsPage() {
  useDocumentTitle('Notifications');
  const [feedItems, setFeedItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    feedApi.list({ limit: 50, exclude_type: 'enrichment_prompt' })
      .then((res) => {
        if (cancelled) return;
        // Deduplicate by title — keep only the newest item per unique title
        const raw = res.data || [];
        const seen = new Set();
        const deduped = raw.filter((item) => {
          if (seen.has(item.title)) return false;
          seen.add(item.title);
          return true;
        });
        setFeedItems(deduped);
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const unseenCount = feedItems.filter((f) => !f.seen_at).length;

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-48 animate-pulse rounded bg-muted" />
        <div className="space-y-3">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-24 animate-pulse rounded-lg bg-muted" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <h1 className="page-title">Notifications</h1>
          {unseenCount > 0 && (
            <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-[11px] font-bold text-background">
              {unseenCount}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {unseenCount > 0 && (
            <button
              type="button"
              onClick={async () => {
                const unseenIds = feedItems.filter((f) => !f.seen_at).map((f) => f.id);
                try {
                  await feedApi.batchSeen(unseenIds);
                  setFeedItems((prev) => prev.map((f) => ({ ...f, seen_at: new Date().toISOString() })));
                  window.dispatchEvent(new Event('feed-updated'));
                } catch { /* silent */ }
              }}
              className="cursor-pointer text-sm text-muted-foreground transition-colors duration-200 hover:text-secondary-foreground"
            >
              Mark all read
            </button>
          )}
          {feedItems.length > 0 && (
            <button
              type="button"
              onClick={async () => {
                try {
                  await feedApi.dismissAll();
                  setFeedItems([]);
                  window.dispatchEvent(new Event('feed-updated'));
                } catch { /* silent */ }
              }}
              className="cursor-pointer text-sm text-muted-foreground transition-colors duration-200 hover:text-secondary-foreground"
            >
              Clear all
            </button>
          )}
        </div>
      </div>

      {feedItems.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <img
            src={noNotificationsIllustration}
            alt=""
            className="mb-6 h-40 w-auto object-contain"
            draggable={false}
          />
          <p className="text-lg font-medium text-foreground">You're all caught up</p>
          <p className="mt-1 text-sm text-muted-foreground">No new notifications right now.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {feedItems.map((item) => (
            <FeedCard
              key={item.id}
              item={item}
              onDismiss={(id) => {
                setFeedItems((prev) => prev.filter((f) => f.id !== id));
                window.dispatchEvent(new Event('feed-updated'));
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}
