import { useEffect, useState } from 'react';
import { applications as appsApi } from '../api/client';
import FeedbackModal from '../components/FeedbackModal';

const PIPELINE_STAGES = [
  { key: 'draft', label: 'Draft', color: 'bg-slate-100 text-slate-600' },
  { key: 'message_sent', label: 'Sent', color: 'bg-blue-100 text-blue-700' },
  { key: 'responded', label: 'Responded', color: 'bg-amber-100 text-amber-700' },
  { key: 'interview_scheduled', label: 'Interview', color: 'bg-purple-100 text-purple-700' },
  { key: 'interviewed', label: 'Interviewed', color: 'bg-purple-100 text-purple-700' },
  { key: 'offer_received', label: 'Offer', color: 'bg-green-100 text-green-700' },
  { key: 'offer_accepted', label: 'Accepted', color: 'bg-green-200 text-green-800' },
  { key: 'rejected', label: 'Rejected', color: 'bg-red-100 text-red-700' },
  { key: 'withdrawn', label: 'Withdrawn', color: 'bg-slate-100 text-slate-500' },
  { key: 'no_response', label: 'No Response', color: 'bg-slate-100 text-slate-400' },
];

const KANBAN_COLUMNS = [
  { key: 'draft', label: 'Draft' },
  { key: 'message_sent', label: 'Sent' },
  { key: 'responded', label: 'Responded' },
  { key: 'interview', label: 'Interview', statuses: ['interview_scheduled', 'interviewed'] },
  { key: 'offer', label: 'Offer', statuses: ['offer_received', 'offer_accepted'] },
  { key: 'closed', label: 'Closed', statuses: ['rejected', 'withdrawn', 'no_response'] },
];

function StatusBadge({ status }) {
  const stage = PIPELINE_STAGES.find((s) => s.key === status);
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${stage?.color || 'bg-slate-100 text-slate-600'}`}>
      {stage?.label || status}
    </span>
  );
}

function AppCard({ app, onStatusChange, updating }) {
  const isMarketplace = app.channel === 'marketplace' || app.match_result_id;
  const nextStatuses = getNextStatuses(app.status);

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
      <div className="flex items-start justify-between">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-slate-900">{app.company_name}</p>
          {app.role_title && (
            <p className="truncate text-xs text-slate-500">{app.role_title}</p>
          )}
        </div>
        {isMarketplace && (
          <span className="ml-2 shrink-0 rounded bg-purple-50 px-1.5 py-0.5 text-xs font-medium text-purple-600">
            Via Marketplace
          </span>
        )}
      </div>

      {app.contact_name && (
        <p className="mt-1 text-xs text-slate-400">Contact: {app.contact_name}</p>
      )}
      {app.channel && !isMarketplace && (
        <p className="mt-0.5 text-xs text-slate-400">via {app.channel}</p>
      )}
      {app.notes && (
        <p className="mt-1 truncate text-xs text-slate-400">{app.notes}</p>
      )}

      {app.days_since_sent != null && app.status === 'message_sent' && (
        <p className={`mt-1 text-xs ${app.needs_follow_up ? 'font-medium text-amber-600' : 'text-slate-400'}`}>
          {app.days_since_sent}d since sent{app.needs_follow_up ? ' — follow up?' : ''}
        </p>
      )}

      <div className="mt-2 flex items-center justify-between">
        <span className="text-xs text-slate-400">
          {new Date(app.created_at).toLocaleDateString()}
        </span>
        {nextStatuses.length > 0 && (
          <select
            value=""
            onChange={(e) => onStatusChange(app.id, e.target.value)}
            disabled={updating === app.id}
            aria-label={`Change status for ${app.company_name}`}
            className="rounded border border-slate-200 px-1 py-0.5 text-xs text-slate-600 focus:border-amber-500 focus:outline-none"
          >
            <option value="" disabled>Move to...</option>
            {nextStatuses.map((s) => {
              const stage = PIPELINE_STAGES.find((p) => p.key === s);
              return <option key={s} value={s}>{stage?.label || s}</option>;
            })}
          </select>
        )}
      </div>
    </div>
  );
}

function getNextStatuses(current) {
  const transitions = {
    draft: ['message_sent', 'withdrawn'],
    message_sent: ['responded', 'no_response', 'withdrawn'],
    responded: ['interview_scheduled', 'rejected', 'withdrawn'],
    interview_scheduled: ['interviewed', 'rejected', 'withdrawn'],
    interviewed: ['offer_received', 'rejected', 'withdrawn'],
    offer_received: ['offer_accepted', 'rejected', 'withdrawn'],
  };
  return transitions[current] || [];
}

export default function ApplicationsPage() {
  const [apps, setApps] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [newApp, setNewApp] = useState({ company_name: '', role_title: '', channel: '', notes: '' });
  const [creating, setCreating] = useState(false);
  const [showFeedback, setShowFeedback] = useState(false);

  const load = async () => {
    try {
      const [appsRes, statsRes] = await Promise.all([
        appsApi.list(),
        appsApi.stats().catch(() => null),
      ]);
      setApps(appsRes.data || []);
      if (statsRes) setStats(statsRes.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleStatusChange = async (id, status) => {
    setUpdating(id);
    try {
      await appsApi.update(id, { status });
      await load();
      setTimeout(() => setShowFeedback(true), 5000);
    } catch (err) {
      console.error(err);
    } finally {
      setUpdating(null);
    }
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!newApp.company_name.trim()) return;
    setCreating(true);
    try {
      await appsApi.create({
        company_name: newApp.company_name,
        role_title: newApp.role_title || null,
        channel: newApp.channel || null,
        notes: newApp.notes || null,
      });
      setNewApp({ company_name: '', role_title: '', channel: '', notes: '' });
      setShowCreate(false);
      await load();
    } catch (err) {
      console.error(err);
    } finally {
      setCreating(false);
    }
  };

  const getColumnApps = (col) => {
    const statuses = col.statuses || [col.key];
    return apps.filter((a) => statuses.includes(a.status));
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20" role="main" aria-live="polite" aria-busy="true">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-amber-500 border-t-transparent" role="status" aria-label="Loading applications" />
      </div>
    );
  }

  return (
    <div role="main">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-bold text-slate-900">My Applications</h1>
        <button
          onClick={() => setShowCreate(!showCreate)}
          aria-expanded={showCreate}
          aria-controls="create-application-form"
          className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-600"
        >
          {showCreate ? 'Cancel' : 'Track Application'}
        </button>
      </div>

      {/* Stats */}
      {stats && (
        <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-5">
          <div className="rounded-lg bg-white p-3 ring-1 ring-slate-200">
            <p className="text-xs text-slate-500">Total</p>
            <p className="text-xl font-bold text-slate-900">{stats.total}</p>
          </div>
          <div className="rounded-lg bg-white p-3 ring-1 ring-slate-200">
            <p className="text-xs text-slate-500">Response Rate</p>
            <p className="text-xl font-bold text-slate-900">{Math.round(stats.response_rate * 100)}%</p>
          </div>
          <div className="rounded-lg bg-white p-3 ring-1 ring-slate-200">
            <p className="text-xs text-slate-500">Interview Rate</p>
            <p className="text-xl font-bold text-slate-900">{Math.round(stats.interview_rate * 100)}%</p>
          </div>
          <div className="rounded-lg bg-white p-3 ring-1 ring-slate-200">
            <p className="text-xs text-slate-500">Avg Response</p>
            <p className="text-xl font-bold text-slate-900">
              {stats.avg_days_to_response != null ? `${Math.round(stats.avg_days_to_response)}d` : '—'}
            </p>
          </div>
          <div className="rounded-lg bg-white p-3 ring-1 ring-slate-200">
            <p className="text-xs text-slate-500">Best Channel</p>
            <p className="text-xl font-bold text-slate-900">{stats.best_channel || '—'}</p>
          </div>
        </div>
      )}

      {/* Create form */}
      {showCreate && (
        <form id="create-application-form" onSubmit={handleCreate} aria-label="Track a new application" className="mb-6 rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
          <h2 className="mb-3 text-base font-semibold text-slate-900">Track a New Application</h2>
          <div className="grid grid-cols-2 gap-3">
            <input
              id="new-app-company"
              type="text"
              value={newApp.company_name}
              onChange={(e) => setNewApp({ ...newApp, company_name: e.target.value })}
              placeholder="Company name *"
              aria-label="Company name"
              required
              aria-required="true"
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
            />
            <input
              id="new-app-role"
              type="text"
              value={newApp.role_title}
              onChange={(e) => setNewApp({ ...newApp, role_title: e.target.value })}
              placeholder="Role title"
              aria-label="Role title"
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
            />
            <select
              id="new-app-channel"
              value={newApp.channel}
              onChange={(e) => setNewApp({ ...newApp, channel: e.target.value })}
              aria-label="Application channel"
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
            >
              <option value="">Channel</option>
              <option value="linkedin">LinkedIn</option>
              <option value="email">Email</option>
              <option value="marketplace">Marketplace</option>
              <option value="direct">Direct</option>
              <option value="recruiter">Recruiter</option>
            </select>
            <input
              id="new-app-notes"
              type="text"
              value={newApp.notes}
              onChange={(e) => setNewApp({ ...newApp, notes: e.target.value })}
              placeholder="Notes"
              aria-label="Notes"
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
            />
          </div>
          <button
            type="submit"
            disabled={creating || !newApp.company_name.trim()}
            className="mt-3 rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50"
          >
            {creating ? 'Adding...' : 'Add Application'}
          </button>
        </form>
      )}

      {/* Kanban board */}
      {apps.length === 0 ? (
        <div className="rounded-xl bg-white p-12 text-center ring-1 ring-slate-200">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-slate-100">
            <span className="text-xl text-slate-400">~</span>
          </div>
          <h2 className="mb-2 text-base font-semibold text-slate-900">No applications yet</h2>
          <p className="mx-auto mb-4 max-w-sm text-sm text-slate-500">
            Track your job applications here. Applications from marketplace intros will appear automatically.
          </p>
          <button
            onClick={() => setShowCreate(true)}
            className="rounded-lg bg-amber-500 px-6 py-2.5 text-sm font-medium text-white hover:bg-amber-600"
          >
            Track Your First Application
          </button>
        </div>
      ) : (
        <div className="overflow-x-auto pb-4">
          <div className="flex gap-3" style={{ minWidth: `${KANBAN_COLUMNS.length * 220}px` }}>
            {KANBAN_COLUMNS.map((col) => {
              const colApps = getColumnApps(col);
              return (
                <div key={col.key} className="w-56 shrink-0">
                  <div className="mb-2 flex items-center gap-2">
                    <h3 className="text-sm font-semibold text-slate-700">{col.label}</h3>
                    {colApps.length > 0 && (
                      <span className="rounded-full bg-slate-200 px-1.5 py-0.5 text-xs text-slate-600">{colApps.length}</span>
                    )}
                  </div>
                  <div className="space-y-2">
                    {colApps.map((app) => (
                      <AppCard
                        key={app.id}
                        app={app}
                        onStatusChange={handleStatusChange}
                        updating={updating}
                      />
                    ))}
                    {colApps.length === 0 && (
                      <div className="rounded-lg border-2 border-dashed border-slate-200 p-4 text-center text-xs text-slate-400">
                        No applications
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {showFeedback && (
        <FeedbackModal
          feature="application_tracker"
          onClose={() => setShowFeedback(false)}
        />
      )}
    </div>
  );
}
