import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { privacy as privacyApi, auth as authApi } from '../api/client';
import { useAuth } from '../context/AuthContext';
import Spinner from '../components/ui/Spinner';
import useDocumentTitle from '../hooks/useDocumentTitle';

const REGULATION_OPTIONS = ['GDPR', 'CCPA', 'PDPA', 'Other'];
const REQUEST_TYPES = [
  { value: 'access', label: 'Access my data' },
  { value: 'deletion', label: 'Delete my data' },
  { value: 'rectification', label: 'Correct my data' },
  { value: 'portability', label: 'Data portability' },
];

export default function PrivacySettingsPage() {
  useDocumentTitle('Privacy Settings');
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [restricted, setRestricted] = useState(false);
  const [marketingOptedOut, setMarketingOptedOut] = useState(false);
  const [consentRecords, setConsentRecords] = useState([]);
  const [togglingRestrict, setTogglingRestrict] = useState(false);
  const [togglingMarketing, setTogglingMarketing] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportDone, setExportDone] = useState(false);
  const [error, setError] = useState('');

  // Data request form
  const [requestType, setRequestType] = useState('access');
  const [requestDetails, setRequestDetails] = useState('');
  const [requestRegulation, setRequestRegulation] = useState('GDPR');
  const [submittingRequest, setSubmittingRequest] = useState(false);
  const [requestSuccess, setRequestSuccess] = useState('');

  // Delete account
  const [showDelete, setShowDelete] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState('');
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const consentRes = await privacyApi.listConsent().catch(() => ({ data: [] }));
        setConsentRecords(consentRes.data || []);

        // Derive toggle states from user or consent records
        setRestricted(user?.processing_restricted || false);
        setMarketingOptedOut(user?.marketing_opt_out || false);
      } catch {
        // non-critical
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [user]);

  const handleExport = async () => {
    setExporting(true);
    setError('');
    try {
      const res = await privacyApi.exportData();
      // Download as JSON file
      const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'warmpath-data-export.json';
      a.click();
      URL.revokeObjectURL(url);
      setExportDone(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setExporting(false);
    }
  };

  const handleToggleRestrict = async () => {
    setTogglingRestrict(true);
    setError('');
    try {
      if (restricted) {
        await privacyApi.unrestrictProcessing();
        setRestricted(false);
      } else {
        await privacyApi.restrictProcessing();
        setRestricted(true);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setTogglingRestrict(false);
    }
  };

  const handleToggleMarketing = async () => {
    setTogglingMarketing(true);
    setError('');
    try {
      if (marketingOptedOut) {
        await privacyApi.marketingOptIn();
        setMarketingOptedOut(false);
      } else {
        await privacyApi.marketingOptOut();
        setMarketingOptedOut(true);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setTogglingMarketing(false);
    }
  };

  const handleDataRequest = async (e) => {
    e.preventDefault();
    setSubmittingRequest(true);
    setError('');
    setRequestSuccess('');
    try {
      await privacyApi.dataRequest({
        request_type: requestType,
        details: requestDetails.trim() || undefined,
        regulation: requestRegulation,
      });
      setRequestSuccess('Your request has been submitted. We will respond within the regulatory deadline.');
      setRequestDetails('');
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmittingRequest(false);
    }
  };

  const handleDeleteAccount = async () => {
    if (deleteConfirm !== 'DELETE') return;
    setDeleting(true);
    setError('');
    try {
      await authApi.deleteAccount({ confirm: true });
      logout();
      navigate('/');
    } catch (err) {
      setError(err.message);
    } finally {
      setDeleting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20" role="main" aria-live="polite" aria-busy="true">
        <Spinner size="lg" />
      </div>
    );
  }

  const inputClass = 'w-full rounded-lg border border-border bg-muted text-foreground placeholder:text-muted-foreground px-3 py-2 text-sm focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring';

  return (
    <div className="mx-auto max-w-3xl" role="main">
      <h1 className="mb-6 text-xl font-bold text-foreground">Privacy Settings</h1>

      {error && (
        <div role="alert" aria-live="polite" className="mb-4 rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Data Export */}
      <section className="mb-6 rounded-xl bg-card p-5 border border-border" aria-label="Data export">
        <h2 className="mb-1 text-base font-semibold text-foreground">Download My Data</h2>
        <p className="mb-3 text-sm text-muted-foreground">
          Export all your personal data as a JSON file. This includes your profile, contacts, search history, and credit transactions.
        </p>
        <button
          onClick={handleExport}
          disabled={exporting}
          className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50"
        >
          {exporting ? 'Preparing...' : exportDone ? 'Download Again' : 'Download My Data'}
        </button>
        {exportDone && (
          <p className="mt-2 text-xs text-success" role="status">Download started.</p>
        )}
      </section>

      {/* Processing Restriction */}
      <section className="mb-6 rounded-xl bg-card p-5 border border-border" aria-label="Processing restriction">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-foreground">Restrict Processing</h2>
            <p className="text-sm text-muted-foreground">
              Limit how we process your data. Your account will remain active but some features may be unavailable.
            </p>
          </div>
          <button
            onClick={handleToggleRestrict}
            disabled={togglingRestrict}
            role="switch"
            aria-checked={restricted}
            aria-label="Restrict data processing"
            className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full transition-colors duration-200 ${
              restricted ? 'bg-primary' : 'bg-muted-foreground'
            } disabled:opacity-50`}
          >
            <span
              className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform duration-200 ${
                restricted ? 'translate-x-5' : 'translate-x-0.5'
              } mt-0.5`}
            />
          </button>
        </div>
      </section>

      {/* Marketing Preferences */}
      <section className="mb-6 rounded-xl bg-card p-5 border border-border" aria-label="Marketing preferences">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-foreground">Marketing Communications</h2>
            <p className="text-sm text-muted-foreground">
              {marketingOptedOut
                ? 'You have opted out of marketing emails. Toggle to opt back in.'
                : 'Receive product updates and tips. Toggle off to opt out.'}
            </p>
          </div>
          <button
            onClick={handleToggleMarketing}
            disabled={togglingMarketing}
            role="switch"
            aria-checked={!marketingOptedOut}
            aria-label="Marketing communications"
            className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full transition-colors duration-200 ${
              !marketingOptedOut ? 'bg-primary' : 'bg-muted-foreground'
            } disabled:opacity-50`}
          >
            <span
              className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform duration-200 ${
                !marketingOptedOut ? 'translate-x-5' : 'translate-x-0.5'
              } mt-0.5`}
            />
          </button>
        </div>
      </section>

      {/* Consent Records */}
      <section className="mb-6 rounded-xl bg-card p-5 border border-border" aria-label="Consent records">
        <h2 className="mb-3 text-base font-semibold text-foreground">Consent Records</h2>
        {consentRecords.length === 0 ? (
          <p className="text-sm text-muted-foreground">No consent records on file.</p>
        ) : (
          <div className="space-y-2">
            {consentRecords.map((record, i) => (
              <div key={record.id || i} className="flex items-center justify-between rounded-lg border border-border p-3">
                <div>
                  <p className="text-sm font-medium text-foreground">{record.processing_activity || record.activity}</p>
                  <p className="text-xs text-muted-foreground">
                    {record.status || (record.consented ? 'Consented' : 'Withdrawn')}
                    {record.created_at && ` — ${new Date(record.created_at).toLocaleDateString()}`}
                  </p>
                </div>
                <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                  record.consented || record.status === 'granted'
                    ? 'bg-success/10 text-success'
                    : 'bg-muted/50 text-muted-foreground'
                }`}>
                  {record.consented || record.status === 'granted' ? 'Active' : 'Withdrawn'}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Formal Data Request */}
      <section className="mb-6 rounded-xl bg-card p-5 border border-border" aria-label="Formal data request">
        <h2 className="mb-1 text-base font-semibold text-foreground">Formal Data Request</h2>
        <p className="mb-3 text-sm text-muted-foreground">
          Submit a formal data subject access request (DSAR). We will respond within the regulatory deadline.
        </p>

        <form onSubmit={handleDataRequest} className="space-y-3">
          <div>
            <label htmlFor="request-type" className="mb-1 block text-sm font-medium text-secondary-foreground">Request type</label>
            <select
              id="request-type"
              value={requestType}
              onChange={(e) => setRequestType(e.target.value)}
              className={inputClass}
            >
              {REQUEST_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="request-details" className="mb-1 block text-sm font-medium text-secondary-foreground">
              Details <span className="text-muted-foreground">(optional)</span>
            </label>
            <textarea
              id="request-details"
              value={requestDetails}
              onChange={(e) => setRequestDetails(e.target.value)}
              placeholder="Any specific details about your request..."
              rows={3}
              className={inputClass}
            />
          </div>

          <div>
            <label htmlFor="request-regulation" className="mb-1 block text-sm font-medium text-secondary-foreground">Regulation</label>
            <select
              id="request-regulation"
              value={requestRegulation}
              onChange={(e) => setRequestRegulation(e.target.value)}
              className={inputClass}
            >
              {REGULATION_OPTIONS.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>

          {requestSuccess && (
            <p role="status" className="rounded-md bg-success/10 p-2 text-sm text-success">{requestSuccess}</p>
          )}

          <button
            type="submit"
            disabled={submittingRequest}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50"
          >
            {submittingRequest ? 'Submitting...' : 'Submit Request'}
          </button>
        </form>
      </section>

      {/* Delete Account — Danger Zone */}
      <section className="rounded-xl border-2 border-destructive/30 bg-destructive/10 p-5" aria-label="Delete account">
        <h2 className="mb-1 text-base font-semibold text-destructive">Delete Account</h2>
        <p className="mb-3 text-sm text-muted-foreground">
          Permanently delete your account, contacts, search history, and all associated data. This action cannot be undone.
        </p>

        {!showDelete ? (
          <button
            onClick={() => setShowDelete(true)}
            className="rounded-lg border border-destructive/30 px-4 py-2 text-sm font-medium text-destructive hover:bg-destructive/20"
          >
            Delete My Account
          </button>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-destructive">
              Type <strong>DELETE</strong> to confirm permanent deletion:
            </p>
            <input
              type="text"
              value={deleteConfirm}
              onChange={(e) => setDeleteConfirm(e.target.value)}
              placeholder="Type DELETE"
              aria-label="Type DELETE to confirm"
              className="w-full rounded-lg border border-destructive/30 bg-muted text-foreground placeholder:text-muted-foreground px-3 py-2 text-sm focus:border-destructive focus:outline-none focus:ring-1 focus:ring-destructive"
            />
            <div className="flex gap-2">
              <button
                onClick={handleDeleteAccount}
                disabled={deleting || deleteConfirm !== 'DELETE'}
                className="rounded-lg bg-destructive px-4 py-2 text-sm font-medium text-white hover:bg-destructive/90 disabled:opacity-50"
              >
                {deleting ? 'Deleting...' : 'Permanently Delete'}
              </button>
              <button
                onClick={() => { setShowDelete(false); setDeleteConfirm(''); }}
                className="rounded-lg border border-border px-4 py-2 text-sm text-muted-foreground hover:bg-muted"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
