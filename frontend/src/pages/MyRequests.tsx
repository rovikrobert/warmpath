import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { marketplace as mpApi, applications as appsApi } from '../api/client';
import { MarketplaceBadge } from '../utils/marketplace';
import ScoreExplainer from '../components/ScoreExplainer';
import useDocumentTitle from '../hooks/useDocumentTitle';

function StatusBadge({ status }) {
  const labels = { requested: 'Pending', reviewing: 'Reviewing', approved: 'Approved', declined: 'Declined', completed: 'Completed', expired: 'Expired' };
  const colors = {
    requested: 'bg-primary/10 text-primary',
    reviewing: 'bg-blue-500/10 text-blue-400',
    approved: 'bg-emerald-500/10 text-emerald-400',
    declined: 'bg-red-500/10 text-red-400',
    completed: 'bg-muted/50 text-muted-foreground',
    expired: 'bg-muted/50 text-muted-foreground',
  };
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${colors[status] || colors.requested}`}>
      {labels[status] || status}
    </span>
  );
}

export default function MyRequests() {
  useDocumentTitle('My Requests');
  const [requests, setRequests] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [trackedIds, setTrackedIds] = useState(new Set());
  const [trackingId, setTrackingId] = useState(null);

  useEffect(() => {
    mpApi.myRequests()
      .then((res) => setRequests(res.data || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);


  const handleTrackApp = async (reqId) => {
    setTrackingId(reqId);
    try {
      await appsApi.fromFacilitation(reqId);
      setTrackedIds((prev) => new Set([...prev, reqId]));
    } catch (err) {
      // Already tracked or other error — still mark as tracked for UX
      setTrackedIds((prev) => new Set([...prev, reqId]));
      console.error(err);
    } finally {
      setTrackingId(null);
    }
  };
  const filtered = filter === 'all' ? requests : requests.filter((r) => r.status === filter);
  const counts = {
    all: requests.length,
    requested: requests.filter((r) => r.status === 'requested').length,
    approved: requests.filter((r) => r.status === 'approved').length,
    declined: requests.filter((r) => r.status === 'declined').length,
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20" aria-live="polite" aria-busy="true">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" role="status" aria-label="Loading requests" />
      </div>
    );
  }

  return (
    <div role="main">
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-xl font-bold text-foreground">Marketplace Requests</h1>
        <Link to="/referrals" className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90">
          Find Referrals
        </Link>
      </div>

      {/* Filter tabs */}
      {requests.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label="Filter requests by status">
          {[
            { key: 'all', label: 'All' },
            { key: 'requested', label: 'Pending' },
            { key: 'approved', label: 'Approved' },
            { key: 'declined', label: 'Declined' },
          ].map((tab) => (
            <button
              key={tab.key}
              onClick={() => setFilter(tab.key)}
              aria-pressed={filter === tab.key}
              className={`rounded-full px-3 py-1 text-sm font-medium transition ${
                filter === tab.key
                  ? 'bg-primary text-white'
                  : 'bg-muted text-muted-foreground border border-border hover:bg-muted'
              }`}
            >
              {tab.label} {counts[tab.key] > 0 && <span className="ml-1 text-xs">({counts[tab.key]})</span>}
            </button>
          ))}
        </div>
      )}

      {requests.length === 0 ? (
        <div className="rounded-xl bg-card p-12 text-center border border-border">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-muted" aria-hidden="true">
            <span className="text-xl text-muted-foreground">~</span>
          </div>
          <h2 className="mb-2 text-base font-semibold text-foreground">No intro requests yet</h2>
          <p className="mx-auto mb-4 max-w-sm text-sm text-muted-foreground">
            Search the marketplace to discover referral paths at companies you're interested in.
          </p>
          <Link
            to="/referrals"
            className="inline-block rounded-lg bg-primary px-6 py-2.5 text-sm font-medium text-white hover:bg-primary/90"
          >
            Find Referrals
          </Link>
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl bg-card p-8 text-center border border-border">
          <p className="text-sm text-muted-foreground">No requests with this status.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((req) => (
            <div key={req.id} className="rounded-xl bg-card border border-border">
              <div className="p-5">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <StatusBadge status={req.status} />
                      <span className="text-xs text-muted-foreground">
                        {new Date(req.requested_at).toLocaleDateString()}
                      </span>
                      {req.reviewed_at && (
                        <span className="text-xs text-muted-foreground">
                          &middot; Reviewed {new Date(req.reviewed_at).toLocaleDateString()}
                        </span>
                      )}
                    </div>

                    {req.listing_summary && (
                      <div className="mt-2">
                        <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                          <MarketplaceBadge value={req.listing_summary.role_level} type="role" />
                          <span>at {req.listing_summary.company_name}</span>
                        </div>
                        <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                          {req.listing_summary.department_category && <span>{req.listing_summary.department_category}</span>}
                          {req.listing_summary.department_category && <span>&middot;</span>}
                          <MarketplaceBadge value={req.listing_summary.warm_score_range} type="strength" />
                          <ScoreExplainer
                            title="Connection Strength"
                            body="The network holder's relationship strength with this contact. Stronger connections lead to better intro outcomes."
                            learnMoreHref="/help/scores#warm-score"
                          />
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Approved: show holder's message and next steps */}
                {req.status === 'approved' && (
                  <div className="mt-4 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-4" aria-live="polite">
                    <h4 className="mb-1 text-sm font-semibold text-emerald-400">Intro Approved!</h4>
                    {req.network_holder_notes && (
                      <p className="mb-3 text-sm text-emerald-400/80">
                        Their message: "{req.network_holder_notes}"
                      </p>
                    )}
                    <div className="space-y-2 text-sm text-emerald-400/80">
                      <p className="font-medium">Next steps:</p>
                      <ol className="ml-4 list-decimal space-y-1">
                        <li>They'll introduce you to their contact via LinkedIn or email.</li>
                        <li>Look out for a connection request or intro message in the next few days.</li>
                        <li>When you hear from the contact, send a warm follow-up thanking them for their time.</li>
                        <li>Mention the specific role you're interested in and keep the conversation natural.</li>
                      </ol>
                    <div className="mt-3 border-t border-emerald-500/20 pt-3">
                      {trackedIds.has(req.id) ? (
                        <p className="text-sm text-emerald-400/80">
                          Application tracked — <Link to="/applications" className="underline hover:text-emerald-300">view pipeline</Link>
                        </p>
                      ) : (
                        <button
                          onClick={() => handleTrackApp(req.id)}
                          disabled={trackingId === req.id}
                          className="rounded-md bg-emerald-500/20 px-3 py-1.5 text-sm font-medium text-emerald-400 hover:bg-emerald-500/30 disabled:opacity-50"
                        >
                          {trackingId === req.id ? 'Tracking...' : 'Track this application'}
                        </button>
                      )}
                    </div>
                    </div>
                  </div>
                )}

                {/* Declined: show reason if available */}
                {req.status === 'declined' && (
                  <div className="mt-4 rounded-lg border border-red-500/30 bg-red-500/10 p-3" aria-live="polite">
                    <p className="text-sm text-red-400">
                      This request was declined.
                      {req.network_holder_notes && <> Reason: "{req.network_holder_notes}"</>}
                      {' '}15 of 20 credits have been refunded.
                    </p>
                  </div>
                )}

                {/* Pending: reminder */}
                {req.status === 'requested' && (
                  <p className="mt-3 text-xs text-muted-foreground">
                    Waiting for the connection owner to review your request. You'll be notified when they respond.
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
