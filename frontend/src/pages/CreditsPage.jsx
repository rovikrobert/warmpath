import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { credits as creditsApi, usage as usageApi } from '../api/client';
import Spinner from '../components/ui/Spinner';
import DashboardSkeleton from '../components/skeletons/DashboardSkeleton';

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
    return <DashboardSkeleton />;
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6" role="main">
      <h1 className="page-title">Credits</h1>

      {/* Balance card */}
      <div className="surface-elevated p-6">
        <p className="stat-label">Available Balance</p>
        <p className="stat-number mt-1 text-4xl text-amber-400">{balance?.balance ?? 0}</p>
        <div className="mt-4 flex gap-6 text-sm">
          <div>
            <p className="text-slate-400">Total Earned</p>
            <p className="font-semibold font-mono text-slate-50">{balance?.earned_total ?? 0}</p>
          </div>
          <div>
            <p className="text-slate-400">Total Spent</p>
            <p className="font-semibold font-mono text-slate-50">{balance?.spent_total ?? 0}</p>
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
        <div className="surface-raised p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="section-title">Usage This Month</h2>
            <span className="rounded-full bg-slate-700/50 px-2.5 py-0.5 text-xs font-medium text-slate-400">
              {usageData.beta_sandbox ? 'Beta' : usageData.plan_tier === 'free' ? 'Free plan' : usageData.plan_tier}
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
      <div className="surface-raised p-5">
        <h2 className="section-title mb-3">How to Earn Credits</h2>
        <div className="space-y-3">
          {[
            { action: 'Upload your LinkedIn CSV', amount: '+100', desc: 'Import your connections to get started' },
            { action: 'Facilitate an intro', amount: '+50', desc: 'Approve an intro request from a candidate' },
            { action: 'Keep data fresh', amount: '+10', desc: 'Re-upload your CSV each quarter' },
            { action: 'Welcome bonus', amount: usageData?.beta_sandbox ? '+500' : '+50', desc: usageData?.beta_sandbox ? 'Beta bonus' : 'Awarded when you create your account' },
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
      <div className="surface-raised p-5">
        <h2 className="section-title mb-3">How Credits Are Spent</h2>
        <div className="space-y-3">
          {[
            { action: 'Marketplace search', amount: '-5', desc: 'Search other people\'s networks' },
            { action: 'Request intro', amount: '-20', desc: 'Ask a connection owner to introduce you (15 refunded if declined)' },
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

      {/* Buy credits stub — hidden during beta */}
      {!(usageData?.beta_sandbox) && (
        <div className="surface-raised p-5">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="section-title">Buy Credits</h2>
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
      )}

      {/* Transaction history */}
      <div className="surface-raised">
        <div className="border-b border-slate-700/50 px-5 py-4">
          <h2 className="section-title">Transaction History</h2>
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
                    <p className="text-sm text-slate-50 truncate max-w-[200px] sm:max-w-none">
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

      {/* Next action footer */}
      <div className="surface-raised p-5">
        <h2 className="section-title mb-3">Put Your Credits to Work</h2>
        <div className="flex flex-col gap-3 sm:flex-row">
          <Link
            to="/referrals"
            className="flex flex-1 items-center gap-3 rounded-lg bg-slate-800/50 p-3 text-sm font-medium text-slate-200 hover:bg-slate-700/50 transition-colors"
          >
            <svg className="h-5 w-5 text-amber-400 shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
            </svg>
            <div>
              <p>Find Referrals</p>
              <p className="text-xs text-slate-400 font-normal">Use credits to search networks</p>
            </div>
          </Link>
          <Link
            to="/contacts"
            className="flex flex-1 items-center gap-3 rounded-lg bg-slate-800/50 p-3 text-sm font-medium text-slate-200 hover:bg-slate-700/50 transition-colors"
          >
            <svg className="h-5 w-5 text-amber-400 shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
            </svg>
            <div>
              <p>Upload Contacts</p>
              <p className="text-xs text-slate-400 font-normal">Earn 100 credits per CSV upload</p>
            </div>
          </Link>
          <Link
            to="/invite"
            className="flex flex-1 items-center gap-3 rounded-lg bg-slate-800/50 p-3 text-sm font-medium text-slate-200 hover:bg-slate-700/50 transition-colors"
          >
            <svg className="h-5 w-5 text-amber-400 shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 11.25v8.25a1.5 1.5 0 01-1.5 1.5H5.25a1.5 1.5 0 01-1.5-1.5v-8.25M12 4.875A2.625 2.625 0 109.375 7.5H12m0-2.625V7.5m0-2.625A2.625 2.625 0 1114.625 7.5H12m0 0V21m-8.625-9.75h18c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125h-18c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125z" />
            </svg>
            <div>
              <p>Invite & Earn</p>
              <p className="text-xs text-slate-400 font-normal">Earn credits for every referral</p>
            </div>
          </Link>
        </div>
      </div>
    </div>
  );
}
