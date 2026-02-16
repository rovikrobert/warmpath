import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { marketplace as mpApi } from '../api/client';

function StatusBadge({ status }) {
  const labels = { requested: 'Pending', reviewing: 'Reviewing', approved: 'Approved', declined: 'Declined', completed: 'Completed', expired: 'Expired' };
  const colors = {
    requested: 'bg-amber-100 text-amber-700',
    reviewing: 'bg-blue-100 text-blue-700',
    approved: 'bg-green-100 text-green-700',
    declined: 'bg-red-100 text-red-700',
    completed: 'bg-slate-100 text-slate-600',
    expired: 'bg-slate-100 text-slate-400',
  };
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${colors[status] || colors.requested}`}>
      {labels[status] || status}
    </span>
  );
}

export default function MyRequests() {
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');

  useEffect(() => {
    mpApi.myRequests()
      .then((res) => setRequests(res.data || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const filtered = filter === 'all' ? requests : requests.filter((r) => r.status === filter);
  const counts = {
    all: requests.length,
    requested: requests.filter((r) => r.status === 'requested').length,
    approved: requests.filter((r) => r.status === 'approved').length,
    declined: requests.filter((r) => r.status === 'declined').length,
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-amber-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-bold text-slate-900">Marketplace Requests</h1>
        <Link to="/referrals" className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-600">
          Find Referrals
        </Link>
      </div>

      {/* Filter tabs */}
      {requests.length > 0 && (
        <div className="mb-4 flex gap-2">
          {[
            { key: 'all', label: 'All' },
            { key: 'requested', label: 'Pending' },
            { key: 'approved', label: 'Approved' },
            { key: 'declined', label: 'Declined' },
          ].map((tab) => (
            <button
              key={tab.key}
              onClick={() => setFilter(tab.key)}
              className={`rounded-full px-3 py-1 text-sm font-medium transition ${
                filter === tab.key
                  ? 'bg-amber-500 text-white'
                  : 'bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50'
              }`}
            >
              {tab.label} {counts[tab.key] > 0 && <span className="ml-1 text-xs">({counts[tab.key]})</span>}
            </button>
          ))}
        </div>
      )}

      {requests.length === 0 ? (
        <div className="rounded-xl bg-white p-12 text-center ring-1 ring-slate-200">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-slate-100">
            <span className="text-xl text-slate-400">~</span>
          </div>
          <h2 className="mb-2 text-base font-semibold text-slate-900">No intro requests yet</h2>
          <p className="mx-auto mb-4 max-w-sm text-sm text-slate-500">
            Search the marketplace to discover referral paths at companies you're interested in.
          </p>
          <Link
            to="/referrals"
            className="inline-block rounded-lg bg-amber-500 px-6 py-2.5 text-sm font-medium text-white hover:bg-amber-600"
          >
            Find Referrals
          </Link>
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl bg-white p-8 text-center ring-1 ring-slate-200">
          <p className="text-sm text-slate-500">No requests with this status.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((req) => (
            <div key={req.id} className="rounded-xl bg-white shadow-sm ring-1 ring-slate-200">
              <div className="p-5">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <StatusBadge status={req.status} />
                      <span className="text-xs text-slate-400">
                        {new Date(req.requested_at).toLocaleDateString()}
                      </span>
                      {req.reviewed_at && (
                        <span className="text-xs text-slate-400">
                          &middot; Reviewed {new Date(req.reviewed_at).toLocaleDateString()}
                        </span>
                      )}
                    </div>

                    {req.listing_summary && (
                      <div className="mt-2">
                        <p className="text-sm font-medium text-slate-900">
                          {req.listing_summary.role_level} at {req.listing_summary.company_name}
                        </p>
                        <p className="text-xs text-slate-500">
                          {req.listing_summary.department_category && `${req.listing_summary.department_category} · `}
                          {req.listing_summary.warm_sco[RESEND_KEY_REDACTED]} connection
                        </p>
                      </div>
                    )}
                  </div>
                </div>

                {/* Approved: show holder's message and next steps */}
                {req.status === 'approved' && (
                  <div className="mt-4 rounded-lg border border-green-200 bg-green-50 p-4">
                    <h4 className="mb-1 text-sm font-semibold text-green-800">Intro Approved!</h4>
                    {req.network_holder_notes && (
                      <p className="mb-3 text-sm text-green-700">
                        Message from network holder: "{req.network_holder_notes}"
                      </p>
                    )}
                    <div className="space-y-2 text-sm text-green-700">
                      <p className="font-medium">Next steps:</p>
                      <ol className="ml-4 list-decimal space-y-1">
                        <li>The network holder will introduce you to their contact via LinkedIn or email.</li>
                        <li>Look out for a connection request or intro message in the next few days.</li>
                        <li>When you hear from the contact, send a warm follow-up thanking them for their time.</li>
                        <li>Mention the specific role you're interested in and keep the conversation natural.</li>
                      </ol>
                    </div>
                  </div>
                )}

                {/* Declined: show reason if available */}
                {req.status === 'declined' && (
                  <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3">
                    <p className="text-sm text-red-700">
                      This request was declined.
                      {req.network_holder_notes && <> Reason: "{req.network_holder_notes}"</>}
                      {' '}15 of 20 credits have been refunded.
                    </p>
                  </div>
                )}

                {/* Pending: reminder */}
                {req.status === 'requested' && (
                  <p className="mt-3 text-xs text-slate-400">
                    Waiting for the network holder to review your request. You'll be notified when they respond.
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
