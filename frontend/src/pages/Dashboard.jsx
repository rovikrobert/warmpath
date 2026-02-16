import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { contacts as contactsApi, search as searchApi, health as healthApi } from '../api/client';
import UploadModal from '../components/UploadModal';

export default function Dashboard() {
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [searches, setSearches] = useState([]);
  const [contactCount, setContactCount] = useState(null);
  const [showUpload, setShowUpload] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [contactsRes, searchRes, usageRes] = await Promise.all([
        contactsApi.list(1, 1),
        searchApi.list(),
        healthApi.usage().catch(() => null),
      ]);
      setContactCount(contactsRes.meta?.total ?? contactsRes.data?.length ?? 0);
      setSearches(searchRes.data ?? []);
      if (usageRes) setStats(usageRes.data);
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
        <div className="rounded-lg bg-white p-4 ring-1 ring-slate-200">
          <p className="text-xs text-slate-500">Searches</p>
          <p className="text-2xl font-bold text-slate-900">{searches.length}</p>
        </div>
        <div className="rounded-lg bg-white p-4 ring-1 ring-slate-200">
          <p className="text-xs text-slate-500">API Calls Today</p>
          <p className="text-2xl font-bold text-slate-900">{stats?.today_count ?? '—'}</p>
        </div>
        <div className="rounded-lg bg-white p-4 ring-1 ring-slate-200">
          <p className="text-xs text-slate-500">AI Queries</p>
          <p className="text-2xl font-bold text-slate-900">{stats?.ai_query_count ?? '—'}</p>
        </div>
      </div>

      {/* Action buttons */}
      <div className="mb-6 flex flex-wrap gap-3">
        <button
          onClick={() => setShowUpload(true)}
          className="rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-medium text-white hover:bg-amber-600"
        >
          {hasContacts ? 'Upload More Contacts' : 'Upload LinkedIn CSV'}
        </button>
        {hasContacts && (
          <Link
            to="/search/new"
            className="rounded-lg border border-amber-500 px-4 py-2.5 text-sm font-medium text-amber-600 hover:bg-amber-50"
          >
            New Search
          </Link>
        )}
      </div>

      {/* Empty state */}
      {!hasContacts && (
        <div className="rounded-xl bg-white p-12 text-center ring-1 ring-slate-200">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-amber-100">
            <span className="text-2xl text-amber-600">~</span>
          </div>
          <h2 className="mb-2 text-lg font-semibold text-slate-900">Get started with WarmPath</h2>
          <p className="mx-auto mb-6 max-w-sm text-sm text-slate-500">
            Upload your LinkedIn connections CSV to start finding warm paths to your target contacts.
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
            <h2 className="text-base font-semibold text-slate-900">Your Searches</h2>
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
                      onClick={() => navigate(`/search/${s.id}`)}
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
            {contactCount} contacts imported. Create your first search to find warm paths.
          </p>
          <Link
            to="/search/new"
            className="inline-block rounded-lg bg-amber-500 px-6 py-2.5 text-sm font-medium text-white hover:bg-amber-600"
          >
            Create First Search
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
