import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { referrals as referralsApi } from '../api/client';
import Spinner from '../components/ui/Spinner';

function CopyButton({ text }) {
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
      aria-label={copied ? 'Copied' : 'Copy code'}
      className="rounded border border-slate-700/50 px-2 py-1 text-xs text-slate-400 hover:bg-slate-800"
    >
      {copied ? 'Copied!' : 'Copy'}
    </button>
  );
}

export default function ReferralCodesPage() {
  const [codes, setCodes] = useState([]);
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
      <h1 className="mb-6 text-xl font-bold text-slate-50">Invite &amp; Earn</h1>

      {/* My Referral Code */}
      <section className="mb-6 rounded-xl bg-slate-900 p-5 border border-slate-700/50" aria-label="My referral code">
        <h2 className="mb-1 text-base font-semibold text-slate-50">Your Referral Code</h2>
        <p className="mb-4 text-sm text-slate-400">
          Share your code with friends. You earn 25 credits each time they complete a key action (upload contacts, search, or subscribe).
        </p>

        {myCode ? (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
            <code className="rounded-lg bg-slate-800 px-4 py-2 font-mono text-lg text-slate-100">{myCode.code}</code>
            <CopyButton text={myCode.code} />
            <div className="flex flex-wrap items-center gap-2 text-sm text-slate-400 sm:gap-4">
              <span>{myCode.uses_count ?? 0} uses</span>
              <span>{myCode.credits_per_conversion ?? 25} credits each</span>
              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                myCode.is_active !== false ? 'bg-emerald-500/10 text-emerald-400' : 'bg-slate-700/50 text-slate-400'
              }`}>
                {myCode.is_active !== false ? 'Active' : 'Inactive'}
              </span>
            </div>
          </div>
        ) : (
          <div>
            {error && <p role="alert" className="mb-3 rounded-md bg-red-500/10 p-2 text-sm text-red-400">{error}</p>}
            <button
              onClick={handleCreate}
              disabled={creating}
              className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-400 disabled:opacity-50"
            >
              {creating ? 'Creating...' : 'Create My Referral Code'}
            </button>
          </div>
        )}
      </section>

      {/* Leaderboard */}
      <section aria-label="Referral leaderboard">
        <h2 className="mb-3 text-base font-semibold text-slate-50">Leaderboard</h2>
        {leaderboard.length === 0 ? (
          <div className="rounded-xl bg-slate-900 p-8 text-center border border-slate-700/50">
            <p className="text-sm text-slate-400">No conversions yet. Be the first!</p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-xl bg-slate-900 border border-slate-700/50">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700/50 bg-slate-800">
                  <th className="px-5 py-3 text-left font-medium text-slate-400">#</th>
                  <th className="px-5 py-3 text-left font-medium text-slate-400">Name</th>
                  <th className="px-5 py-3 text-right font-medium text-slate-400">Conversions</th>
                  <th className="px-5 py-3 text-right font-medium text-slate-400">Credits Earned</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/50">
                {leaderboard.map((entry, i) => (
                  <tr key={entry.user_id || i} className="hover:bg-slate-800">
                    <td className="px-5 py-3 text-slate-400">{i + 1}</td>
                    <td className="px-5 py-3 font-medium text-slate-50">{entry.name || 'Anonymous'}</td>
                    <td className="px-5 py-3 text-right text-slate-300">{entry.total_conversions ?? 0}</td>
                    <td className="px-5 py-3 text-right font-medium font-mono text-amber-400">{entry.total_credits ?? 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Quick links */}
      <div className="mt-6 flex flex-wrap items-center gap-3 text-sm">
        <Link to="/credits" className="text-amber-400 hover:text-amber-300">View credits &rarr;</Link>
        <span className="text-slate-600">&middot;</span>
        <Link to="/coach" className="text-slate-400 hover:text-slate-300">Back to Coach</Link>
        <span className="text-slate-600">&middot;</span>
        <Link to="/referrals" className="text-slate-400 hover:text-slate-300">Find referrals</Link>
      </div>
    </div>
  );
}
