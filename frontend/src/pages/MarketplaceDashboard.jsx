import { useEffect, useState } from 'react';
import { marketplace as mpApi, credits as creditsApi } from '../api/client';

function StatusBadge({ status }) {
  const map = {
    requested: 'bg-amber-100 text-amber-700',
    reviewing: 'bg-blue-100 text-blue-700',
    approved: 'bg-green-100 text-green-700',
    declined: 'bg-red-100 text-red-700',
    completed: 'bg-slate-100 text-slate-600',
  };
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${map[status] || map.requested}`}>
      {status}
    </span>
  );
}

export default function MarketplaceDashboard() {
  const [prefs, setPrefs] = useState(null);
  const [listings, setListings] = useState([]);
  const [incoming, setIncoming] = useState([]);
  const [balance, setBalance] = useState(0);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState(false);
  const [actionLoading, setActionLoading] = useState(null);

  const load = async () => {
    try {
      const [prefsRes, listingsRes, incomingRes, balRes] = await Promise.all([
        mpApi.getSharingPrefs().catch(() => ({ data: { opt_in_marketplace: false, is_paused: false } })),
        mpApi.myListings().catch(() => ({ data: [] })),
        mpApi.incomingRequests().catch(() => ({ data: [] })),
        creditsApi.balance().catch(() => ({ data: { balance: 0 } })),
      ]);
      setPrefs(prefsRes.data);
      setListings(listingsRes.data || []);
      setIncoming(incomingRes.data || []);
      setBalance(balRes.data?.balance ?? 0);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const toggleSharing = async () => {
    setToggling(true);
    try {
      const newState = !prefs.opt_in_marketplace;
      const res = await mpApi.updateSharingPrefs({
        opt_in_marketplace: newState,
        is_paused: false,
        category_filters: prefs.category_filters || null,
        excluded_contact_ids: prefs.excluded_contact_ids || null,
      });
      setPrefs(res.data);
      if (newState) {
        const listingsRes = await mpApi.myListings().catch(() => ({ data: [] }));
        setListings(listingsRes.data || []);
      } else {
        setListings([]);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setToggling(false);
    }
  };

  const togglePause = async () => {
    setToggling(true);
    try {
      const res = await mpApi.updateSharingPrefs({
        opt_in_marketplace: prefs.opt_in_marketplace,
        is_paused: !prefs.is_paused,
        category_filters: prefs.category_filters || null,
        excluded_contact_ids: prefs.excluded_contact_ids || null,
      });
      setPrefs(res.data);
    } catch (err) {
      console.error(err);
    } finally {
      setToggling(false);
    }
  };

  const handleAction = async (id, action) => {
    setActionLoading(id);
    try {
      await mpApi.updateRequest(id, { action });
      await load();
    } catch (err) {
      console.error(err);
    } finally {
      setActionLoading(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-amber-500 border-t-transparent" />
      </div>
    );
  }

  const pendingCount = incoming.filter((r) => r.status === 'requested').length;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-slate-900">Marketplace Dashboard</h1>

      {/* Sharing Toggle */}
      <div className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-slate-900">Network Sharing</h2>
            <p className="text-sm text-slate-500">
              {prefs?.opt_in_marketplace
                ? prefs?.is_paused ? 'Your network is paused — listings are hidden temporarily.' : 'Your network is shared on the marketplace.'
                : 'Share your network to help others get referred and earn credits.'}
            </p>
          </div>
          <div className="flex gap-2">
            {prefs?.opt_in_marketplace && (
              <button
                onClick={togglePause}
                disabled={toggling}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50"
              >
                {prefs?.is_paused ? 'Resume' : 'Pause'}
              </button>
            )}
            <button
              onClick={toggleSharing}
              disabled={toggling}
              className={`rounded-md px-4 py-1.5 text-sm font-medium disabled:opacity-50 ${
                prefs?.opt_in_marketplace
                  ? 'border border-red-200 text-red-600 hover:bg-red-50'
                  : 'bg-amber-500 text-white hover:bg-amber-600'
              }`}
            >
              {toggling ? '...' : prefs?.opt_in_marketplace ? 'Opt Out' : 'Opt In'}
            </button>
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-lg bg-white p-4 ring-1 ring-slate-200">
          <p className="text-xs text-slate-500">Active Listings</p>
          <p className="text-2xl font-bold text-slate-900">{listings.length}</p>
        </div>
        <div className="rounded-lg bg-white p-4 ring-1 ring-slate-200">
          <p className="text-xs text-slate-500">Pending Requests</p>
          <p className="text-2xl font-bold text-slate-900">{pendingCount}</p>
        </div>
        <div className="rounded-lg bg-white p-4 ring-1 ring-slate-200">
          <p className="text-xs text-slate-500">Total Requests</p>
          <p className="text-2xl font-bold text-slate-900">{incoming.length}</p>
        </div>
        <div className="rounded-lg bg-white p-4 ring-1 ring-slate-200">
          <p className="text-xs text-slate-500">Credits</p>
          <p className="text-2xl font-bold text-amber-600">{balance}</p>
        </div>
      </div>

      {/* Incoming Requests */}
      {incoming.length > 0 && (
        <div className="rounded-xl bg-white shadow-sm ring-1 ring-slate-200">
          <div className="border-b border-slate-200 px-5 py-4">
            <h2 className="text-base font-semibold text-slate-900">
              Incoming Requests
              {pendingCount > 0 && (
                <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">{pendingCount} pending</span>
              )}
            </h2>
          </div>
          <div className="divide-y divide-slate-100">
            {incoming.map((req) => (
              <div key={req.id} className="px-5 py-4">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <StatusBadge status={req.status} />
                      <span className="text-xs text-slate-400">
                        {new Date(req.requested_at).toLocaleDateString()}
                      </span>
                    </div>
                    {/* Job seeker info */}
                    {req.job_seeker_profile_snapshot && (
                      <p className="mt-1 text-sm text-slate-700">
                        {req.job_seeker_profile_snapshot.full_name || 'Anonymous job seeker'}
                        {req.job_seeker_profile_snapshot.message && (
                          <span className="text-slate-400"> — "{req.job_seeker_profile_snapshot.message}"</span>
                        )}
                      </p>
                    )}
                    {/* Contact info (holder's own contact) */}
                    {req.contact_name && (
                      <p className="mt-1 text-xs text-slate-500">
                        Your contact: {req.contact_name}
                        {req.contact_title && `, ${req.contact_title}`}
                        {req.contact_company && ` at ${req.contact_company}`}
                      </p>
                    )}
                    {req.network_holder_notes && (
                      <p className="mt-1 text-xs text-slate-400">Your notes: {req.network_holder_notes}</p>
                    )}
                  </div>
                  {req.status === 'requested' && (
                    <div className="flex shrink-0 gap-2">
                      <button
                        onClick={() => handleAction(req.id, 'approve')}
                        disabled={actionLoading === req.id}
                        className="rounded-md bg-green-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-600 disabled:opacity-50"
                      >
                        Approve
                      </button>
                      <button
                        onClick={() => handleAction(req.id, 'decline')}
                        disabled={actionLoading === req.id}
                        className="rounded-md border border-red-200 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
                      >
                        Decline
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* My Listings */}
      {listings.length > 0 && (
        <div className="overflow-hidden rounded-xl bg-white shadow-sm ring-1 ring-slate-200">
          <div className="border-b border-slate-200 px-5 py-4">
            <h2 className="text-base font-semibold text-slate-900">My Listings</h2>
          </div>
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50">
              <tr>
                <th className="px-5 py-3 font-medium text-slate-600">Contact</th>
                <th className="px-5 py-3 font-medium text-slate-600">Title</th>
                <th className="hidden px-5 py-3 font-medium text-slate-600 sm:table-cell">Role Level</th>
                <th className="hidden px-5 py-3 font-medium text-slate-600 md:table-cell">Strength</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {listings.map((l) => (
                <tr key={l.id}>
                  <td className="px-5 py-3 text-slate-900">{l.contact_name || '—'}</td>
                  <td className="px-5 py-3 text-slate-600">{l.contact_title || '—'}</td>
                  <td className="hidden px-5 py-3 text-slate-600 sm:table-cell">{l.role_level}</td>
                  <td className="hidden px-5 py-3 text-slate-500 md:table-cell">{l.warm_score_range}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Empty state */}
      {listings.length === 0 && incoming.length === 0 && (
        <div className="rounded-xl bg-white p-12 text-center ring-1 ring-slate-200">
          <p className="text-sm text-slate-500">
            {prefs?.opt_in_marketplace
              ? 'No listings yet. Upload contacts to generate marketplace listings.'
              : 'Opt in to share your network and start earning credits from referral requests.'}
          </p>
        </div>
      )}
    </div>
  );
}
