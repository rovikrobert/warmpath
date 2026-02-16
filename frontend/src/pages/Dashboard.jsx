import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { contacts as contactsApi, search as searchApi, usage as usageApi, marketplace as mpApi } from '../api/client';
import UploadModal from '../components/UploadModal';

export default function Dashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [searches, setSearches] = useState([]);
  const [contactCount, setContactCount] = useState(null);
  const [marketplaceStats, setMarketplaceStats] = useState(null);
  const [usageData, setUsageData] = useState(null);
  const [showUpload, setShowUpload] = useState(false);
  const [loading, setLoading] = useState(true);

  const isSeeker = !user?.user_type || user.user_type === 'job_seeker' || user.user_type === 'both';
  const isHolder = user?.user_type === 'network_holder' || user?.user_type === 'both';

  const load = async () => {
    setLoading(true);
    try {
      const [contactsRes, searchRes, usageRes] = await Promise.all([
        contactsApi.list({ page: 1, per_page: 1 }),
        searchApi.list(),
        usageApi.summary().catch(() => null),
      ]);
      setContactCount(contactsRes.meta?.total ?? contactsRes.data?.length ?? 0);
      setSearches(searchRes.data ?? []);
      if (usageRes) {
        setStats(usageRes.data);
        setUsageData(usageRes.data);
      }

      // Load marketplace stats for holders
      if (isHolder) {
        const [listingsRes, incomingRes] = await Promise.all([
          mpApi.myListings().catch(() => ({ data: [] })),
          mpApi.incomingRequests().catch(() => ({ data: [] })),
        ]);
        setMarketplaceStats({
          listings: listingsRes.data?.length ?? 0,
          pendingRequests: (incomingRes.data || []).filter((r) => r.status === 'requested').length,
        });
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const hasContacts = contactCount > 0;

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-amber-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <div>
      {/* Stats bar */}
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-lg bg-white p-4 ring-1 ring-slate-200">
          <p className="text-xs text-slate-500">Contacts</p>
          <p className="text-2xl font-bold text-slate-900">{contactCount ?? 0}</p>
        </div>
        {isSeeker && (
          <div className="rounded-lg bg-white p-4 ring-1 ring-slate-200">
            <p className="text-xs text-slate-500">Searches</p>
            <p className="text-2xl font-bold text-slate-900">{searches.length}</p>
          </div>
        )}
        {isHolder && marketplaceStats && (
          <div className="rounded-lg bg-white p-4 ring-1 ring-slate-200">
            <p className="text-xs text-slate-500">Shared Listings</p>
            <p className="text-2xl font-bold text-slate-900">{marketplaceStats.listings}</p>
          </div>
        )}
        {isHolder && marketplaceStats && (
          <div className="rounded-lg bg-white p-4 ring-1 ring-slate-200">
            <p className="text-xs text-slate-500">Pending Requests</p>
            <p className="text-2xl font-bold text-slate-900">{marketplaceStats.pendingRequests}</p>
          </div>
        )}
        {!isHolder && (
          <div className="rounded-lg bg-white p-4 ring-1 ring-slate-200">
            <p className="text-xs text-slate-500">API Calls Today</p>
            <p className="text-2xl font-bold text-slate-900">{stats?.today_count ?? '—'}</p>
          </div>
        )}
      </div>

      {/* Usage this month */}
      {usageData && (
        <div className="mb-6 rounded-lg bg-white p-4 ring-1 ring-slate-200">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">This Month</h3>
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
            {[
              { key: 'smart_search', label: 'Searches' },
              { key: 'intro_draft', label: 'Messages drafted' },
              { key: 'marketplace_search', label: 'Marketplace searches' },
              { key: 'intro_request', label: 'Intro requests' },
            ].map(({ key, label }) => {
              const count = usageData.counts?.[key] ?? 0;
              const limit = usageData.limits?.[key];
              const isUnlimited = limit === 'unlimited';
              const atLimit = !isUnlimited && typeof limit === 'number' && count >= limit;
              const nearLimit = !isUnlimited && typeof limit === 'number' && count >= limit * 0.8 && !atLimit;
              return (
                <span
                  key={key}
                  className={
                    atLimit ? 'font-medium text-red-600' :
                    nearLimit ? 'font-medium text-amber-600' :
                    'text-slate-700'
                  }
                >
                  {count}{!isUnlimited && typeof limit === 'number' ? `/${limit}` : ''} {label}
                </span>
              );
            })}
          </div>
        </div>
      )}

      {/* Action buttons */}
      <div className="mb-6 flex flex-wrap gap-3">
        <button
          onClick={() => setShowUpload(true)}
          className="rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-medium text-white hover:bg-amber-600"
        >
          {hasContacts ? 'Upload More Contacts' : 'Upload LinkedIn CSV'}
        </button>
        {isSeeker && hasContacts && (
          <Link
            to="/referrals"
            className="rounded-lg border border-amber-500 px-4 py-2.5 text-sm font-medium text-amber-600 hover:bg-amber-50"
          >
            Find Referrals
          </Link>
        )}
        {isHolder && (
          <Link
            to="/marketplace/dashboard"
            className="rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50"
          >
            Marketplace Dashboard
          </Link>
        )}
      </div>

      {/* Marketplace activity cards */}
      {isHolder && marketplaceStats && marketplaceStats.pendingRequests > 0 && (
        <div className="mb-6 rounded-lg border border-amber-200 bg-amber-50 p-4">
          <p className="text-sm text-amber-800">
            You have <strong>{marketplaceStats.pendingRequests}</strong> pending intro request{marketplaceStats.pendingRequests > 1 ? 's' : ''} waiting for your review.
          </p>
          <Link to="/marketplace/dashboard" className="mt-1 inline-block text-sm font-medium text-amber-600 hover:text-amber-700">
            Review requests &rarr;
          </Link>
        </div>
      )}

      {/* Empty state */}
      {!hasContacts && (
        <div className="rounded-xl bg-white p-12 text-center ring-1 ring-slate-200">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-amber-100">
            <span className="text-2xl text-amber-600">~</span>
          </div>
          <h2 className="mb-2 text-lg font-semibold text-slate-900">Get started with WarmPath</h2>
          <p className="mx-auto mb-6 max-w-sm text-sm text-slate-500">
            Upload your LinkedIn connections CSV to start finding warm referral paths to your target companies.
          </p>
          <button
            onClick={() => setShowUpload(true)}
            className="rounded-lg bg-amber-500 px-6 py-2.5 text-sm font-medium text-white hover:bg-amber-600"
          >
            Upload Your Connections
          </button>
        </div>
      )}

      {/* Searches list */}
      {searches.length > 0 && (
        <div className="overflow-hidden rounded-xl bg-white shadow-sm ring-1 ring-slate-200">
          <div className="border-b border-slate-200 px-4 py-3">
            <h2 className="text-base font-semibold text-slate-900">Recent Searches</h2>
          </div>
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50">
              <tr>
                <th className="px-4 py-3 font-medium text-slate-600">Name</th>
                <th className="hidden px-4 py-3 font-medium text-slate-600 sm:table-cell">Status</th>
                <th className="hidden px-4 py-3 font-medium text-slate-600 md:table-cell">Matches</th>
                <th className="px-4 py-3 font-medium text-slate-600">Created</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {searches.map((s) => (
                <tr key={s.id} className="hover:bg-amber-50/30">
                  <td className="px-4 py-3">
                    <p className="font-medium text-slate-900">{s.name}</p>
                    {s.description && (
                      <p className="text-xs text-slate-500 line-clamp-1">{s.description}</p>
                    )}
                  </td>
                  <td className="hidden px-4 py-3 sm:table-cell">
                    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                      s.status === 'completed' ? 'bg-green-100 text-green-700' :
                      s.status === 'running' ? 'bg-amber-100 text-amber-700' :
                      s.status === 'failed' ? 'bg-red-100 text-red-700' :
                      'bg-slate-100 text-slate-600'
                    }`}>
                      {s.status}
                    </span>
                  </td>
                  <td className="hidden px-4 py-3 text-slate-600 md:table-cell">
                    {s.match_count ?? '—'}
                  </td>
                  <td className="px-4 py-3 text-slate-500">
                    {new Date(s.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => navigate(s.name?.startsWith('Smart Search') ? `/referrals/${s.id}` : `/search/${s.id}`)}
                      className="rounded-md bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-200"
                    >
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Searches empty state (has contacts but no searches) */}
      {hasContacts && searches.length === 0 && (
        <div className="rounded-xl bg-white p-8 text-center ring-1 ring-slate-200">
          <p className="mb-3 text-sm text-slate-500">
            {contactCount} contacts imported. Find referral paths to your target companies.
          </p>
          <Link
            to="/referrals"
            className="inline-block rounded-lg bg-amber-500 px-6 py-2.5 text-sm font-medium text-white hover:bg-amber-600"
          >
            Find Referrals
          </Link>
        </div>
      )}

      {showUpload && (
        <UploadModal
          onClose={() => setShowUpload(false)}
          onComplete={load}
          hasContacts={hasContacts}
        />
      )}
    </div>
  );
}
