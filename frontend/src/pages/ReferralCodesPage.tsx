import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { referrals as referralsApi } from '../api/client';
import EmptyState from '../components/ui/EmptyState';
import noResultsIllustration from '../assets/illustrations/no-results.png';
import Spinner from '../components/ui/Spinner';
import { useAuth } from '../context/AuthContext';
import useDocumentTitle from '../hooks/useDocumentTitle';

function CopyButton({ text, label = 'Copy', className }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // fallback — select the text
    }
  };

  return (
    <button
      onClick={handleCopy}
      aria-label={copied ? 'Copied' : label}
      className={className || 'cursor-pointer rounded border border-border px-2 py-1 text-xs text-muted-foreground transition-colors duration-200 hover:bg-muted'}
    >
      {copied ? 'Copied!' : label}
    </button>
  );
}

function buildInviteLink(code, intent) {
  const base = `${window.location.origin}/join?ref=${encodeURIComponent(code)}`;
  if (intent === 'sha[RESEND_KEY_REDACTED]') return `${base}&intent=network`;
  if (intent === 'find_referrals') return `${base}&intent=seeker`;
  return `${base}&intent=network`;
}

export default function ReferralCodesPage() {
  useDocumentTitle('Invite Friends');
  const { user } = useAuth();
  const [codes, setCodes] = useState<any[]>([]);
  const [leaderboard, setLeaderboard] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');

  const load = async () => {
    try {
      const [codesRes, lbRes] = await Promise.all([
        referralsApi.mine().catch(() => ({ data: [] })),
        referralsApi.leaderboard().catch(() => ({ data: [] })),
      ]);
      setCodes(codesRes.data || []);
      setLeaderboard(lbRes.data || []);
    } catch {
      // non-critical
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleCreate = async () => {
    setCreating(true);
    setError('');
    try {
      await referralsApi.create({});
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20" role="main" aria-live="polite" aria-busy="true">
        <Spinner size="lg" />
      </div>
    );
  }

  const myCode = codes.length > 0 ? codes[0] : null;

  return (
    <div className="mx-auto max-w-3xl" role="main">
      <h1 className="page-title mb-6">Invite &amp; Earn</h1>

      {/* My Referral Code */}
      <section className="mb-6 surface-raised p-5" aria-label="My referral code">
        <h2 className="section-title mb-1">Your Referral Code</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          Share your code with friends. You earn 25 credits each time they complete a key action (upload contacts, search, or subscribe).
        </p>

        {myCode ? (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
            <code className="rounded-lg bg-muted px-4 py-2 font-mono text-lg text-foreground">{myCode.code}</code>
            <CopyButton text={myCode.code} />
            <CopyButton
              text={buildInviteLink(myCode.code, user?.intent)}
              label="Copy invite link"
              className="cursor-pointer rounded bg-primary px-3 py-1 text-xs font-medium text-white transition-colors duration-200 hover:bg-primary/90"
            />
            <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground sm:gap-4">
              <span>{myCode.uses_count ?? 0} uses</span>
              <span>{myCode.credits_per_conversion ?? 25} credits each</span>
              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                myCode.is_active !== false ? 'bg-success/10 text-success' : 'bg-muted/50 text-muted-foreground'
              }`}>
                {myCode.is_active !== false ? 'Active' : 'Inactive'}
              </span>
            </div>
          </div>
        ) : (
          <div>
            {error && <p role="alert" className="mb-3 rounded-md bg-destructive/10 p-2 text-sm text-destructive">{error}</p>}
            <button
              onClick={handleCreate}
              disabled={creating}
              className="cursor-pointer rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white transition-colors duration-200 hover:bg-primary/90 disabled:opacity-50"
            >
              {creating ? 'Creating...' : 'Create My Referral Code'}
            </button>
          </div>
        )}
      </section>

      {/* Leaderboard */}
      <section aria-label="Referral leaderboard">
        <h2 className="section-title mb-3">Leaderboard</h2>
        {leaderboard.length === 0 ? (
          <EmptyState
            illustration={noResultsIllustration}
            title="Earn credits by inviting friends"
            description="Share your referral code. You earn 25 credits each time a friend uploads contacts, runs a search, or subscribes."
            stats={[
              { value: '25', label: 'credits per conversion' },
              { value: '\u221E', label: 'invite limit' },
            ]}
            primaryAction={!myCode ? { label: 'Create My Referral Code', onClick: handleCreate } : undefined}
          />
        ) : (
          <div className="overflow-hidden surface-raised">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted">
                  <th className="px-5 py-3 text-left font-medium text-muted-foreground">#</th>
                  <th className="px-5 py-3 text-left font-medium text-muted-foreground">Name</th>
                  <th className="px-5 py-3 text-right font-medium text-muted-foreground">Conversions</th>
                  <th className="px-5 py-3 text-right font-medium text-muted-foreground">Credits Earned</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {leaderboard.map((entry, i) => (
                  <tr key={entry.user_id || i} className="hover:bg-muted">
                    <td className="px-5 py-3 text-muted-foreground">{i + 1}</td>
                    <td className="px-5 py-3 font-medium text-foreground">{entry.name || 'Anonymous'}</td>
                    <td className="px-5 py-3 text-right text-secondary-foreground">{entry.total_conversions ?? 0}</td>
                    <td className="px-5 py-3 text-right font-medium font-mono text-primary">{entry.total_credits ?? 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Quick links */}
      <div className="mt-6 flex flex-wrap items-center gap-3 text-sm">
        <Link to="/credits" className="text-primary transition-colors duration-200 hover:text-primary/80">View credits &rarr;</Link>
        <span className="text-muted-foreground">&middot;</span>
        <Link to="/coach" className="text-muted-foreground transition-colors duration-200 hover:text-secondary-foreground">Back to Coach</Link>
        <span className="text-muted-foreground">&middot;</span>
        <Link to="/referrals" className="text-muted-foreground transition-colors duration-200 hover:text-secondary-foreground">Find referrals</Link>
      </div>
    </div>
  );
}
