import { useEffect, useState } from 'react';
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

const TYPE_LABELS = {
  nh_invite: 'Share Connections',
  js_invite: 'Find Referrals',
};

export default function ReferralCodesPage() {
  const [codes, setCodes] = useState([]);
  const [leaderboard, setLeaderboard] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');
  const [newCode, setNewCode] = useState(null);

  // Create form state
  const [codeType, setCodeType] = useState('nh_invite');
  const [targetEmail, setTargetEmail] = useState('');
  const [maxUses, setMaxUses] = useState('');

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

  const handleCreate = async (e) => {
    e.preventDefault();
    setCreating(true);
    setError('');
    setNewCode(null);
    try {
      const body = { code_type: codeType };
      if (targetEmail.trim()) body.target_email = targetEmail.trim();
      if (maxUses) body.max_uses = parseInt(maxUses, 10);
      const res = await referralsApi.create(body);
      setNewCode(res.data);
      setTargetEmail('');
      setMaxUses('');
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

  const inputClass = 'w-full rounded-lg border border-slate-700/50 bg-slate-800 text-slate-100 placeholder-slate-500 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500';

  return (
    <div className="mx-auto max-w-3xl" role="main">
      <h1 className="mb-6 text-xl font-bold text-slate-50">Invite &amp; Earn</h1>

      {/* Create Code */}
      <section className="mb-6 rounded-xl bg-slate-900 p-5 border border-slate-700/50" aria-label="Create referral code">
        <h2 className="mb-1 text-base font-semibold text-slate-50">Create a Referral Code</h2>
        <p className="mb-4 text-sm text-slate-400">
          Invite friends and earn credits when they sign up. Invite someone to share connections (25 credits) or to find referrals (50 credits) when they convert.
        </p>

        <form onSubmit={handleCreate} className="space-y-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-300">Invite type</label>
            <div className="flex gap-3" role="radiogroup" aria-label="Referral code type">
              {[
                { value: 'nh_invite', label: 'Share Connections', desc: '25 credits/conversion' },
                { value: 'js_invite', label: 'Find Referrals', desc: '50 credits/conversion' },
              ].map((opt) => (
                <label
                  key={opt.value}
                  className={`flex flex-1 cursor-pointer items-center gap-2 rounded-lg border p-3 text-sm transition ${
                    codeType === opt.value
                      ? 'border-amber-500/50 bg-amber-500/10 text-amber-400'
                      : 'border-slate-700/50 text-slate-400 hover:border-slate-600'
                  }`}
                >
                  <input
                    type="radio"
                    name="code_type"
                    value={opt.value}
                    checked={codeType === opt.value}
                    onChange={() => setCodeType(opt.value)}
                    className="accent-amber-500"
                  />
                  <div>
                    <span className="font-medium">{opt.label}</span>
                    <span className="ml-1 text-xs text-slate-500">{opt.desc}</span>
                  </div>
                </label>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="target-email" className="mb-1 block text-sm font-medium text-slate-300">
                Target email <span className="text-slate-500">(optional)</span>
              </label>
              <input
                id="target-email"
                type="email"
                value={targetEmail}
                onChange={(e) => setTargetEmail(e.target.value)}
                placeholder="friend@example.com"
                className={inputClass}
              />
            </div>
            <div>
              <label htmlFor="max-uses" className="mb-1 block text-sm font-medium text-slate-300">
                Max uses <span className="text-slate-500">(optional)</span>
              </label>
              <input
                id="max-uses"
                type="number"
                min="1"
                value={maxUses}
                onChange={(e) => setMaxUses(e.target.value)}
                placeholder="Unlimited"
                className={inputClass}
              />
            </div>
          </div>

          {error && <p role="alert" className="rounded-md bg-red-500/10 p-2 text-sm text-red-400">{error}</p>}

          <button
            type="submit"
            disabled={creating}
            className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-400 disabled:opacity-50"
          >
            {creating ? 'Creating...' : 'Create Code'}
          </button>
        </form>

        {newCode && (
          <div className="mt-4 flex items-center gap-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3" role="status" aria-live="polite">
            <span className="text-sm text-emerald-400">Code created:</span>
            <code className="rounded bg-slate-800 px-2 py-1 font-mono text-sm text-slate-100">{newCode.code}</code>
            <CopyButton text={newCode.code} />
          </div>
        )}
      </section>

      {/* My Codes */}
      <section className="mb-6" aria-label="My referral codes">
        <h2 className="mb-3 text-base font-semibold text-slate-50">My Codes</h2>
        {codes.length === 0 ? (
          <div className="rounded-xl bg-slate-900 p-8 text-center border border-slate-700/50">
            <p className="text-sm text-slate-400">No referral codes yet. Create one above to start earning credits.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {codes.map((c) => (
              <div key={c.id || c.code} className="flex items-center justify-between rounded-xl bg-slate-900 px-5 py-4 border border-slate-700/50">
                <div className="flex items-center gap-3">
                  <code className="rounded bg-slate-800 px-2 py-1 font-mono text-sm text-slate-100">{c.code}</code>
                  <CopyButton text={c.code} />
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                    c.code_type === 'nh_invite' ? 'bg-blue-500/10 text-blue-400' : 'bg-purple-500/10 text-purple-400'
                  }`}>
                    {TYPE_LABELS[c.code_type] || c.code_type}
                  </span>
                </div>
                <div className="flex items-center gap-4 text-sm text-slate-400">
                  <span>{c.times_used ?? 0}{c.max_uses ? ` / ${c.max_uses}` : ''} uses</span>
                  <span>{c.credits_per_conversion ?? 0} credits each</span>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                    c.is_active !== false ? 'bg-emerald-500/10 text-emerald-400' : 'bg-slate-700/50 text-slate-400'
                  }`}>
                    {c.is_active !== false ? 'Active' : 'Inactive'}
                  </span>
                </div>
              </div>
            ))}
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
    </div>
  );
}
