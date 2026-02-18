import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { marketplace as mpApi, credits as creditsApi } from '../api/client';

function StatusBadge({ status }) {
  const labels = { requested: 'Pending', reviewing: 'Reviewing', approved: 'Approved', declined: 'Declined', completed: 'Completed' };
  const colors = {
    requested: 'bg-amber-100 text-amber-700',
    reviewing: 'bg-blue-100 text-blue-700',
    approved: 'bg-green-100 text-green-700',
    declined: 'bg-red-100 text-red-700',
    completed: 'bg-slate-100 text-slate-600',
  };
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${colors[status] || colors.requested}`}>
      {labels[status] || status}
    </span>
  );
}

export default function MarketplaceDashboard() {
  const [listings, setListings] = useState([]);
  const [incoming, setIncoming] = useState([]);
  const [balance, setBalance] = useState(0);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(null);
  const [approvedCoaching, setApprovedCoaching] = useState(null); // id of request showing coaching

  const load = async () => {
    try {
      const [listingsRes, incomingRes, balRes] = await Promise.all([
        mpApi.myListings().catch(() => ({ data: [] })),
        mpApi.incomingRequests().catch(() => ({ data: [] })),
        creditsApi.balance().catch(() => ({ data: { balance: 0 } })),
      ]);
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

  const handleAction = async (id, action) => {
    setActionLoading(id);
    try {
      await mpApi.updateRequest(id, { action });
      if (action === 'approve') {
        setApprovedCoaching(id);
      }
      await load();
    } catch (err) {
      console.error(err);
    } finally {
      setActionLoading(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20" aria-live="polite" aria-busy="true">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-amber-500 border-t-transparent" role="status" aria-label="Loading dashboard" />
      </div>
    );
  }

  const pendingRequests = incoming.filter((r) => r.status === 'requested');
  const pastRequests = incoming.filter((r) => r.status !== 'requested');
  const approvedCount = incoming.filter((r) => r.status === 'approved').length;
  const totalResponded = incoming.filter((r) => ['approved', 'declined'].includes(r.status)).length;
  const responseRate = totalResponded > 0 ? Math.round((approvedCount / totalResponded) * 100) : 0;

  return (
    <div className="space-y-6" role="main">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-slate-900">Network Holder Dashboard</h1>
        <Link to="/marketplace/settings" className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50">
          Sharing Settings
        </Link>
      </div>

      {/* Referral bonus callout */}
      {approvedCount === 0 && (
        <div className="rounded-lg border border-green-200 bg-green-50 p-4">
          <div className="flex items-start gap-3">
            <svg className="mt-0.5 h-5 w-5 shrink-0 text-green-600" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v12m-3-2.818.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
            </svg>
            <div>
              <p className="text-sm font-semibold text-green-800">Your employer pays $2,000-$10,000 per referral hire</p>
              <p className="mt-0.5 text-sm text-green-700">
                When you approve an intro and your contact hires the candidate, the referral bonus goes directly to you.
                WarmPath sends you pre-qualified candidates so you don't have to find them yourself.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Reputation + Stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        <div className="rounded-lg bg-white p-4 ring-1 ring-slate-200">
          <p className="text-xs text-slate-500">Active Listings</p>
          <p className="text-2xl font-bold text-slate-900">{listings.length}</p>
        </div>
        <div className="rounded-lg bg-white p-4 ring-1 ring-slate-200">
          <p className="text-xs text-slate-500">Pending Requests</p>
          <p className="text-2xl font-bold text-amber-600">{pendingRequests.length}</p>
        </div>
        <div className="rounded-lg bg-white p-4 ring-1 ring-slate-200">
          <p className="text-xs text-slate-500">Intros Facilitated</p>
          <p className="text-2xl font-bold text-slate-900">{approvedCount}</p>
        </div>
        <div className="rounded-lg bg-white p-4 ring-1 ring-slate-200">
          <p className="text-xs text-slate-500">Response Rate</p>
          <p className="text-2xl font-bold text-slate-900">{responseRate}%</p>
        </div>
        <div className="rounded-lg bg-white p-4 ring-1 ring-slate-200">
          <p className="text-xs text-slate-500">Credits</p>
          <p className="text-2xl font-bold text-amber-600">{balance}</p>
        </div>
      </div>

      {/* Incoming Requests (Pending) */}
      <div className="rounded-xl bg-white shadow-sm ring-1 ring-slate-200">
        <div className="border-b border-slate-200 px-5 py-4">
          <h2 className="text-base font-semibold text-slate-900">
            Incoming Requests
            {pendingRequests.length > 0 && (
              <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
                {pendingRequests.length} pending
              </span>
            )}
          </h2>
        </div>

        {pendingRequests.length === 0 && pastRequests.length === 0 ? (
          <div className="p-8 text-center text-sm text-slate-400">
            No intro requests yet. When job seekers find your contacts on the marketplace, their requests will appear here.
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {/* Pending first */}
            {pendingRequests.map((req) => (
              <div key={req.id} className="px-5 py-4">
                <div className="flex items-start gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <StatusBadge status={req.status} />
                      <span className="text-xs text-slate-400">
                        {new Date(req.requested_at).toLocaleDateString()}
                      </span>
                    </div>

                    {/* Job seeker profile snapshot */}
                    <div className="mt-2 rounded-lg bg-blue-50 p-3">
                      <p className="text-xs font-medium uppercase tracking-wider text-blue-600">Job Seeker</p>
                      <p className="mt-1 text-sm font-medium text-slate-900">
                        {req.job_seeker_profile_snapshot?.full_name || 'Anonymous'}
                      </p>
                      {req.job_seeker_profile_snapshot?.user_type && (
                        <p className="text-xs text-slate-500">{req.job_seeker_profile_snapshot.user_type}</p>
                      )}
                      {req.job_seeker_profile_snapshot?.email && (
                        <p className="text-xs text-slate-500">{req.job_seeker_profile_snapshot.email}</p>
                      )}
                      {req.job_seeker_profile_snapshot?.message && (
                        <p className="mt-2 text-sm italic text-slate-600">
                          "{req.job_seeker_profile_snapshot.message}"
                        </p>
                      )}
                    </div>

                    {/* Listing + your contact info */}
                    <div className="mt-2 rounded-lg bg-slate-50 p-3">
                      <p className="text-xs font-medium uppercase tracking-wider text-slate-500">Your Contact</p>
                      <p className="mt-1 text-sm font-medium text-slate-900">
                        {req.contact_name || 'Unknown'}
                        {req.contact_title && <span className="font-normal text-slate-500">, {req.contact_title}</span>}
                      </p>
                      {req.contact_company && (
                        <p className="text-xs text-slate-500">at {req.contact_company}</p>
                      )}
                      {req.contact_email && (
                        <p className="text-xs text-slate-400">{req.contact_email}</p>
                      )}
                    </div>
                  </div>

                  <div className="flex shrink-0 flex-col gap-2">
                    <button
                      onClick={() => handleAction(req.id, 'approve')}
                      disabled={actionLoading === req.id}
                      aria-label={`Approve intro request from ${req.job_seeker_profile_snapshot?.full_name || 'job seeker'}`}
                      className="rounded-md bg-green-500 px-4 py-2 text-sm font-medium text-white hover:bg-green-600 disabled:opacity-50"
                    >
                      Approve
                    </button>
                    <button
                      onClick={() => handleAction(req.id, 'decline')}
                      disabled={actionLoading === req.id}
                      aria-label={`Decline intro request from ${req.job_seeker_profile_snapshot?.full_name || 'job seeker'}`}
                      className="rounded-md border border-red-200 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
                    >
                      Decline
                    </button>
                  </div>
                </div>
              </div>
            ))}

            {/* Past requests */}
            {pastRequests.map((req) => (
              <div key={req.id} className="px-5 py-4">
                <div className="flex items-center gap-2">
                  <StatusBadge status={req.status} />
                  <span className="text-sm text-slate-700">
                    {req.job_seeker_profile_snapshot?.full_name || 'Anonymous'}
                  </span>
                  <span className="text-xs text-slate-400">
                    &rarr; {req.contact_name || 'Unknown'}
                    {req.contact_company && ` at ${req.contact_company}`}
                  </span>
                  <span className="ml-auto text-xs text-slate-400">
                    {new Date(req.requested_at).toLocaleDateString()}
                  </span>
                </div>

                {/* Coaching text after approval */}
                {req.status === 'approved' && (req.id === approvedCoaching || !approvedCoaching) && (
                  <div className="mt-3 rounded-lg border border-green-200 bg-green-50 p-4" aria-live="polite">
                    <p className="mb-2 text-sm font-semibold text-green-800">
                      Now introduce {req.job_seeker_profile_snapshot?.full_name || 'the job seeker'} to {req.contact_name || 'your contact'}
                    </p>
                    <p className="text-sm text-green-700">
                      Reach out to {req.contact_name || 'your contact'} via LinkedIn or email with a quick intro. Here's a suggested message:
                    </p>
                    <div className="mt-2 rounded-md bg-white p-3 text-sm text-slate-700">
                      <p>Hey {req.contact_name?.split(' ')[0] || 'there'},</p>
                      <p className="mt-2">
                        I'd like to introduce you to {req.job_seeker_profile_snapshot?.full_name || 'someone'} who's
                        interested in opportunities at {req.contact_company || 'your company'}.
                        They came through WarmPath and I thought you two should connect.
                      </p>
                      <p className="mt-2">
                        {req.job_seeker_profile_snapshot?.full_name || 'They'}, meet {req.contact_name || 'my contact'}
                        {req.contact_title ? ` — ${req.contact_title}` : ''} at {req.contact_company || 'the company'}.
                      </p>
                      <p className="mt-2">I'll let you two take it from here!</p>
                    </div>
                    <p className="mt-2 text-xs text-green-600">
                      You earned 50 credits for facilitating this intro.
                    </p>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* My Listings */}
      {listings.length > 0 && (
        <div className="overflow-hidden rounded-xl bg-white shadow-sm ring-1 ring-slate-200">
          <div className="border-b border-slate-200 px-5 py-4">
            <h2 className="text-base font-semibold text-slate-900">My Listings ({listings.length})</h2>
            <p className="text-xs text-slate-400">These contacts appear anonymized on the marketplace.</p>
          </div>
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50">
              <tr>
                <th className="px-5 py-3 font-medium text-slate-600">Contact</th>
                <th className="px-5 py-3 font-medium text-slate-600">Title</th>
                <th className="hidden px-5 py-3 font-medium text-slate-600 sm:table-cell">Company</th>
                <th className="hidden px-5 py-3 font-medium text-slate-600 md:table-cell">Role Level</th>
                <th className="hidden px-5 py-3 font-medium text-slate-600 md:table-cell">Strength</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {listings.map((l) => (
                <tr key={l.id}>
                  <td className="px-5 py-3 text-slate-900">{l.contact_name || '—'}</td>
                  <td className="px-5 py-3 text-slate-600">{l.contact_title || '—'}</td>
                  <td className="hidden px-5 py-3 text-slate-600 sm:table-cell">{l.contact_company || '—'}</td>
                  <td className="hidden px-5 py-3 text-slate-600 md:table-cell">{l.role_level}</td>
                  <td className="hidden px-5 py-3 text-slate-500 md:table-cell">{l.warm_score_range}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
