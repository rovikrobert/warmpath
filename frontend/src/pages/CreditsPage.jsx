import { useEffect, useState } from 'react';
import { credits as creditsApi, usage as usageApi } from '../api/client';
import Spinner from '../components/ui/Spinner';

const REASON_LABELS = {
  welcome_bonus: 'Welcome bonus',
  csv_upload: 'CSV upload',
  marketplace_search: 'Marketplace search',
  intro_request: 'Intro request',
  intro_facilitation: 'Intro facilitated',
  intro_declined_refund: 'Intro declined (refund)',
  credit_purchase: 'Credit purchase',
  credit_expiry: 'Credit expiry',
};

function TypeBadge({ type }) {
  const colors = {
    earned: 'bg-emerald-500/10 text-emerald-400',
    purchased: 'bg-blue-500/10 text-blue-400',
    spent: 'bg-red-500/10 text-red-400',
    expired: 'bg-slate-700/50 text-slate-400',
    refunded: 'bg-amber-500/10 text-amber-400',
  };
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${colors[type] || colors.earned}`}>
      {type}
    </span>
  );
}

function UsageBar({ label, count, limit }) {
  const isBlocked = typeof limit === 'number' && limit === 0;
  const isUnlimited = limit === 'unlimited';
  const pct = isUnlimited ? 0 : isBlocked ? 100 : typeof limit === 'number' ? Math.min(100, (count / limit) * 100) : 0;
  const atLimit = !isUnlimited && typeof limit === 'number' && count >= limit;
  const nearLimit = !isUnlimited && typeof limit === 'number' && count >= limit * 0.8 && !atLimit;

  const barColor = isBlocked ? 'bg-slate-600' : atLimit ? 'bg-red-500' : nearLimit ? 'bg-amber-500' : 'bg-green-500';
  const textColor = isBlocked ? 'text-slate-400' : atLimit ? 'text-red-400' : nearLimit ? 'text-amber-400' : 'text-slate-300';

  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-sm">
        <span className="text-slate-300">{label}</span>
        <span className={`font-medium ${textColor}`}>
          {isBlocked ? 'Upgrade to unlock' : isUnlimited ? `${count} used` : `${count}/${limit}`}
          {atLimit && !isBlocked && ' (limit reached)'}
        </span>
      </div>
      {!isUnlimited && (
        <div className="h-2 overflow-hidden rounded-full bg-slate-800" role="progressbar" aria-valuenow={count} aria-valuemin={0} aria-valuemax={typeof limit === 'number' ? limit : 100} aria-label={`${label} usage`}>
          <div
            className={`h-full rounded-full transition-all ${barColor}`}
            style={{ width: `${Math.max(pct, isBlocked ? 0 : 2)}%` }}
          />
        </div>
      )}
    </div>
  );
}

export default function CreditsPage() {
  const [balance, setBalance] = useState(null);
  const [history, setHistory] = useState([]);
  const [usageData, setUsageData] = useState(null);
  const [showActivity, setShowActivity] = useState(false);
  const [activityLog, setActivityLog] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const [balRes, histRes, usageRes] = await Promise.all([
          creditsApi.balance(),
          creditsApi.history().catch(() => ({ data: [] })),
          usageApi.summary().catch(() => null),
        ]);
        setBalance(balRes.data);
        setHistory(histRes.data || []);
        if (usageRes) setUsageData(usageRes.data);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20" aria-live="polite" aria-busy="true">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6" role="main">
      <h1 className="text-xl font-bold text-slate-50">Credits</h1>

      {/* Balance card */}
      <div className="rounded-xl bg-gradient-to-br from-amber-500 to-amber-600 p-6 text-white shadow-sm">
        <p className="text-sm font-medium text-amber-100">Available Balance</p>
        <p className="mt-1 text-4xl font-bold font-mono">{balance?.balance ?? 0}</p>
        <div className="mt-4 flex gap-6 text-sm">
          <div>
            <p className="text-amber-200">Total Earned</p>
            <p className="font-semibold font-mono">{balance?.earned_total ?? 0}</p>
          </div>
          <div>
            <p className="text-amber-200">Total Spent</p>
            <p className="font-semibold font-mono">{balance?.spent_total ?? 0}</p>
          </div>
        </div>
      </div>

      {/* Expiring soon warning */}
      {balance?.expiring_soon > 0 && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4" role="alert" aria-live="polite">
          <p className="text-sm text-amber-400">
            <span className="font-semibold">{balance.expiring_soon} credits</span> will expire in the next 30 days. Use them before they're gone!
          </p>
        </div>
      )}

      {/* Usage this month */}
      {usageData && (
        <div className="rounded-xl bg-slate-900 p-5 border border-slate-700/50">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold text-slate-50">Usage This Month</h2>
            <span className="rounded-full bg-slate-700/50 px-2.5 py-0.5 text-xs font-medium text-slate-400">
              {usageData.plan_tier === 'free' ? 'Free plan' : usageData.plan_tier}
            </span>
          </div>
          <div className="space-y-3">
            {[
              { key: 'smart_search', label: 'Smart searches' },
              { key: 'intro_draft', label: 'Messages drafted' },
              { key: 'csv_upload', label: 'CSV uploads' },
              { key: 'marketplace_search', label: 'Marketplace searches' },
              { key: 'intro_request', label: 'Intro requests' },
            ].map(({ key, label }) => (
              <UsageBar
                key={key}
                label={label}
                count={usageData.counts?.[key] ?? 0}
                limit={usageData.limits?.[key] ?? 'unlimited'}
              />
            ))}
          </div>
          <button
            onClick={async () => {
              if (!showActivity) {
                const res = await usageApi.history().catch(() => ({ data: [] }));
                setActivityLog(res.data || []);
              }
              setShowActivity(!showActivity);
            }}
            className="mt-4 text-sm font-medium text-amber-400 hover:text-amber-300"
          >
            {showActivity ? 'Hide activity' : 'View all activity'}
          </button>
          {showActivity && activityLog.length > 0 && (
            <div className="mt-3 max-h-60 divide-y divide-slate-700/50 overflow-y-auto rounded-lg border border-slate-700/50">
              {activityLog.map((entry) => (
                <div key={entry.id} className="flex items-center justify-between px-3 py-2 text-xs">
                  <span className="text-slate-300">{entry.action}</span>
                  <span className="text-slate-400">
                    {entry.created_at ? new Date(entry.created_at).toLocaleString() : ''}
                  </span>
                </div>
              ))}
            </div>
          )}
          {showActivity && activityLog.length === 0 && (
            <p className="mt-3 text-xs text-slate-400">No activity recorded yet.</p>
          )}
        </div>
      )}

      {/* How to earn credits */}
      <div className="rounded-xl bg-slate-900 p-5 border border-slate-700/50">
        <h2 className="mb-3 text-base font-semibold text-slate-50">How to Earn Credits</h2>
        <div className="space-y-3">
          {[
            { action: 'Upload your LinkedIn CSV', amount: '+100', desc: 'Import your connections to get started' },
            { action: 'Facilitate an intro', amount: '+50', desc: 'Approve an intro request from a job seeker' },
            { action: 'Keep data fresh', amount: '+10', desc: 'Re-upload your CSV each quarter' },
            { action: 'Welcome bonus', amount: '+50', desc: 'Awarded when you create your account' },
          ].map((item, i) => (
            <div key={i} className="flex items-center justify-between rounded-lg bg-slate-800/50 p-3">
              <div>
                <p className="text-sm font-medium text-slate-50">{item.action}</p>
                <p className="text-xs text-slate-400">{item.desc}</p>
              </div>
              <span className="text-sm font-bold font-mono text-emerald-400">{item.amount}</span>
            </div>
          ))}
        </div>
      </div>

      {/* How credits are spent */}
      <div className="rounded-xl bg-slate-900 p-5 border border-slate-700/50">
        <h2 className="mb-3 text-base font-semibold text-slate-50">How Credits Are Spent</h2>
        <div className="space-y-3">
          {[
            { action: 'Marketplace search', amount: '-5', desc: 'Search other people\'s networks' },
            { action: 'Request intro', amount: '-20', desc: 'Ask a network holder to introduce you (15 refunded if declined)' },
          ].map((item, i) => (
            <div key={i} className="flex items-center justify-between rounded-lg bg-slate-800/50 p-3">
              <div>
                <p className="text-sm font-medium text-slate-50">{item.action}</p>
                <p className="text-xs text-slate-400">{item.desc}</p>
              </div>
              <span className="text-sm font-bold font-mono text-red-400">{item.amount}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Buy credits stub */}
      <div className="rounded-xl bg-slate-900 p-5 border border-slate-700/50">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-slate-50">Buy Credits</h2>
            <p className="text-sm text-slate-400">$1 = 5 credits. Credits expire after 12 months.</p>
          </div>
          <button
            disabled
            aria-disabled="true"
            className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-white opacity-50"
          >
            Coming Soon
          </button>
        </div>
      </div>

      {/* Transaction history */}
      <div className="rounded-xl bg-slate-900 border border-slate-700/50">
        <div className="border-b border-slate-700/50 px-5 py-4">
          <h2 className="text-base font-semibold text-slate-50">Transaction History</h2>
        </div>
        {history.length === 0 ? (
          <div className="p-8 text-center text-sm text-slate-400">
            No transactions yet.
          </div>
        ) : (
          <div className="divide-y divide-slate-700/50">
            {history.map((tx) => (
              <div key={tx.id} className="flex items-center justify-between px-5 py-3">
                <div className="flex items-center gap-3">
                  <TypeBadge type={tx.type} />
                  <div>
                    <p className="text-sm text-slate-50">
                      {REASON_LABELS[tx.reason] || tx.reason}
                    </p>
                    <p className="text-xs text-slate-400">
                      {new Date(tx.created_at).toLocaleDateString()}
                      {tx.expires_at && (
                        <span> &middot; Expires {new Date(tx.expires_at).toLocaleDateString()}</span>
                      )}
                    </p>
                  </div>
                </div>
                <span className={`text-sm font-bold font-mono ${tx.amount > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {tx.amount > 0 ? '+' : ''}{tx.amount}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
