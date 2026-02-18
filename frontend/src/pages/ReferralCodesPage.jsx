import { useEffect, useState } from 'react';
import { referrals as referralsApi } from '../api/client';

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
      className="rounded border border-slate-200 px-2 py-1 text-xs text-slate-500 hover:bg-slate-50"
    >
      {copied ? 'Copied!' : 'Copy'}
    </button>
  );
}

const TYPE_LABELS = {
  nh_invite: 'Network Holder',
  js_invite: 'Job Seeker',
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
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-amber-500 border-t-transparent" role="status" aria-label="Loading referral codes" />
      </div>
    );
  }

  const inputClass = 'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500';

  return (
    <div className="mx-auto max-w-3xl" role="main">
      <h1 className="mb-6 text-xl font-bold text-slate-900">Invite &amp; Earn</h1>

      {/* Create Code */}
      <section className="mb-6 rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200" aria-label="Create referral code">
        <h2 className="mb-1 text-base font-semibold text-slate-900">Create a Referral Code</h2>
        <p className="mb-4 text-sm text-slate-500">
          Invite friends and earn credits when they sign up. Network holder invites earn 25 credits, job seeker invites earn 50 credits per conversion.
        </p>

        <form onSubmit={handleCreate} className="space-y-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Invite type</label>
            <div className="flex gap-3" role="radiogroup" aria-label="Referral code type">
              {[
                { value: 'nh_invite', label: 'Network Holder', desc: '25 credits/conversion' },
                { value: 'js_invite', label: 'Job Seeker', desc: '50 credits/conversion' },
              ].map((opt) => (
                <label
                  key={opt.value}
                  className={`flex flex-1 cursor-pointer items-center gap-2 rounded-lg border p-3 text-sm transition ${
                    codeType === opt.value
                      ? 'border-amber-400 bg-amber-50 text-amber-800'
                      : 'border-slate-200 text-slate-600 hover:border-slate-300'
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
                    <span className="ml-1 text-xs text-slate-400">{opt.desc}</span>
                  </div>
                </label>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="target-email" className="mb-1 block text-sm font-medium text-slate-700">
                Target email <span className="text-slate-400">(optional)</span>
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
              <label htmlFor="max-uses" className="mb-1 block text-sm font-medium text-slate-700">
                Max uses <span className="text-slate-400">(optional)</span>
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

          {error && <p role="alert" className="rounded-md bg-red-50 p-2 text-sm text-red-600">{error}</p>}

          <button
            type="submit"
            disabled={creating}
            className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50"
          >
            {creating ? 'Creating...' : 'Create Code'}
          </button>
        </form>

        {newCode && (
          <div className="mt-4 flex items-center gap-3 rounded-lg border border-green-200 bg-green-50 p-3" role="status" aria-live="polite">
            <span className="text-sm text-green-700">Code created:</span>
            <code className="rounded bg-white px-2 py-1 font-mono text-sm text-slate-900">{newCode.code}</code>
            <CopyButton text={newCode.code} />
          </div>
        )}
      </section>

      {/* My Codes */}
      <section className="mb-6" aria-label="My referral codes">
        <h2 className="mb-3 text-base font-semibold text-slate-900">My Codes</h2>
        {codes.length === 0 ? (
          <div className="rounded-xl bg-white p-8 text-center ring-1 ring-slate-200">
            <p className="text-sm text-slate-500">No referral codes yet. Create one above to start earning credits.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {codes.map((c) => (
              <div key={c.id || c.code} className="flex items-center justify-between rounded-xl bg-white px-5 py-4 shadow-sm ring-1 ring-slate-200">
                <div className="flex items-center gap-3">
                  <code className="rounded bg-slate-100 px-2 py-1 font-mono text-sm text-slate-800">{c.code}</code>
                  <CopyButton text={c.code} />
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                    c.code_type === 'nh_invite' ? 'bg-blue-100 text-blue-700' : 'bg-purple-100 text-purple-700'
                  }`}>
                    {TYPE_LABELS[c.code_type] || c.code_type}
                  </span>
                </div>
                <div className="flex items-center gap-4 text-sm text-slate-500">
                  <span>{c.times_used ?? 0}{c.max_uses ? ` / ${c.max_uses}` : ''} uses</span>
                  <span>{c.credits_per_conversion ?? 0} credits each</span>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                    c.is_active !== false ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-500'
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
        <h2 className="mb-3 text-base font-semibold text-slate-900">Leaderboard</h2>
        {leaderboard.length === 0 ? (
          <div className="rounded-xl bg-white p-8 text-center ring-1 ring-slate-200">
            <p className="text-sm text-slate-500">No conversions yet. Be the first!</p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-xl bg-white ring-1 ring-slate-200">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50">
                  <th className="px-5 py-3 text-left font-medium text-slate-600">#</th>
                  <th className="px-5 py-3 text-left font-medium text-slate-600">Name</th>
                  <th className="px-5 py-3 text-right font-medium text-slate-600">Conversions</th>
                  <th className="px-5 py-3 text-right font-medium text-slate-600">Credits Earned</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {leaderboard.map((entry, i) => (
                  <tr key={entry.user_id || i} className="hover:bg-slate-50">
                    <td className="px-5 py-3 text-slate-500">{i + 1}</td>
                    <td className="px-5 py-3 font-medium text-slate-900">{entry.name || 'Anonymous'}</td>
                    <td className="px-5 py-3 text-right text-slate-700">{entry.total_conversions ?? 0}</td>
                    <td className="px-5 py-3 text-right font-medium text-amber-600">{entry.total_credits ?? 0}</td>
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
