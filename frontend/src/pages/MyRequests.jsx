import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { marketplace as mpApi } from '../api/client';

function StatusBadge({ status }) {
  const map = {
    requested: 'bg-amber-100 text-amber-700',
    reviewing: 'bg-blue-100 text-blue-700',
    approved: 'bg-green-100 text-green-700',
    declined: 'bg-red-100 text-red-700',
    completed: 'bg-slate-100 text-slate-600',
    expired: 'bg-slate-100 text-slate-400',
  };
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${map[status] || map.requested}`}>
      {status}
    </span>
  );
}

export default function MyRequests() {
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    mpApi.myRequests()
      .then((res) => setRequests(res.data || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-amber-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <div>
      <h1 className="mb-6 text-xl font-bold text-slate-900">My Intro Requests</h1>

      {requests.length === 0 ? (
        <div className="rounded-xl bg-white p-12 text-center ring-1 ring-slate-200">
          <p className="mb-3 text-sm text-slate-500">
            No intro requests yet. Search the marketplace to find referral paths.
          </p>
          <Link
            to="/referrals"
            className="inline-block rounded-lg bg-amber-500 px-6 py-2.5 text-sm font-medium text-white hover:bg-amber-600"
          >
            Find Referrals
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {requests.map((req) => (
            <div key={req.id} className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={req.status} />
                    <span className="text-xs text-slate-400">
                      {new Date(req.requested_at).toLocaleDateString()}
                    </span>
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
                  {req.network_holder_notes && (
                    <p className="mt-2 text-xs text-slate-500">
                      Holder notes: {req.network_holder_notes}
                    </p>
                  )}
                </div>
                {req.status === 'approved' && (
                  <span className="shrink-0 rounded-md bg-green-50 px-2 py-1 text-xs text-green-700">
                    Intro approved! Check your messages.
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
