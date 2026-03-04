import { useEffect, useState } from 'react';
import { feed as feedApi } from '../api/client';
import FeedCard from '../components/FeedCard';
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
      .catch((err) => { console.error('NotificationsPage: feed load failed', err); })
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
                } catch (err) { console.error('NotificationsPage: batch seen failed', err); }
              }}
              className="text-sm text-muted-foreground hover:text-secondary-foreground transition-colors"
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
                } catch (err) { console.error('NotificationsPage: dismiss all failed', err); }
              }}
              className="text-sm text-muted-foreground hover:text-secondary-foreground transition-colors"
            >
              Clear all
            </button>
          )}
        </div>
      </div>

      {feedItems.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <svg className="h-12 w-12 text-muted-foreground mb-4" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6 9v.75a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 0 1-5.714 0m5.714 0a3 3 0 1 1-5.714 0" />
          </svg>
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
