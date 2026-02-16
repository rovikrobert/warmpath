import { useEffect, useState } from 'react';
import { credits as creditsApi } from '../api/client';

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
    earned: 'bg-green-100 text-green-700',
    purchased: 'bg-blue-100 text-blue-700',
    spent: 'bg-red-100 text-red-700',
    expired: 'bg-slate-100 text-slate-500',
    refunded: 'bg-amber-100 text-amber-700',
  };
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${colors[type] || colors.earned}`}>
      {type}
    </span>
  );
}

export default function CreditsPage() {
  const [balance, setBalance] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const [balRes, histRes] = await Promise.all([
          creditsApi.balance(),
          creditsApi.history().catch(() => ({ data: [] })),
        ]);
        setBalance(balRes.data);
        setHistory(histRes.data || []);
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
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-amber-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <h1 className="text-xl font-bold text-slate-900">Credits</h1>

      {/* Balance card */}
      <div className="rounded-xl bg-gradient-to-br from-amber-500 to-amber-600 p-6 text-white shadow-sm">
        <p className="text-sm font-medium text-amber-100">Available Balance</p>
        <p className="mt-1 text-4xl font-bold">{balance?.balance ?? 0}</p>
        <div className="mt-4 flex gap-6 text-sm">
          <div>
            <p className="text-amber-200">Total Earned</p>
            <p className="font-semibold">{balance?.earned_total ?? 0}</p>
          </div>
          <div>
            <p className="text-amber-200">Total Spent</p>
            <p className="font-semibold">{balance?.spent_total ?? 0}</p>
          </div>
        </div>
      </div>

      {/* Expiring soon warning */}
      {balance?.expiring_soon > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
          <p className="text-sm text-amber-800">
            <span className="font-semibold">{balance.expiring_soon} credits</span> will expire in the next 30 days. Use them before they're gone!
          </p>
        </div>
      )}

      {/* How to earn credits */}
      <div className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
        <h2 className="mb-3 text-base font-semibold text-slate-900">How to Earn Credits</h2>
        <div className="space-y-3">
          {[
            { action: 'Upload your LinkedIn CSV', amount: '+100', desc: 'Import your connections to get started' },
            { action: 'Facilitate an intro', amount: '+50', desc: 'Approve an intro request from a job seeker' },
            { action: 'Keep data fresh', amount: '+10', desc: 'Re-upload your CSV each quarter' },
            { action: 'Welcome bonus', amount: '+50', desc: 'Awarded when you create your account' },
          ].map((item, i) => (
            <div key={i} className="flex items-center justify-between rounded-lg bg-slate-50 p-3">
              <div>
                <p className="text-sm font-medium text-slate-900">{item.action}</p>
                <p className="text-xs text-slate-500">{item.desc}</p>
              </div>
              <span className="text-sm font-bold text-green-600">{item.amount}</span>
            </div>
          ))}
        </div>
      </div>

      {/* How credits are spent */}
      <div className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
        <h2 className="mb-3 text-base font-semibold text-slate-900">How Credits Are Spent</h2>
        <div className="space-y-3">
          {[
            { action: 'Marketplace search', amount: '-5', desc: 'Search other people\'s networks' },
            { action: 'Request intro', amount: '-20', desc: 'Ask a network holder to introduce you (15 refunded if declined)' },
          ].map((item, i) => (
            <div key={i} className="flex items-center justify-between rounded-lg bg-slate-50 p-3">
              <div>
                <p className="text-sm font-medium text-slate-900">{item.action}</p>
                <p className="text-xs text-slate-500">{item.desc}</p>
              </div>
              <span className="text-sm font-bold text-red-500">{item.amount}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Buy credits stub */}
      <div className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-slate-900">Buy Credits</h2>
            <p className="text-sm text-slate-500">$1 = 5 credits. Credits expire after 12 months.</p>
          </div>
          <button
            disabled
            className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-white opacity-50"
          >
            Coming Soon
          </button>
        </div>
      </div>

      {/* Transaction history */}
      <div className="rounded-xl bg-white shadow-sm ring-1 ring-slate-200">
        <div className="border-b border-slate-200 px-5 py-4">
          <h2 className="text-base font-semibold text-slate-900">Transaction History</h2>
        </div>
        {history.length === 0 ? (
          <div className="p-8 text-center text-sm text-slate-400">
            No transactions yet.
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {history.map((tx) => (
              <div key={tx.id} className="flex items-center justify-between px-5 py-3">
                <div className="flex items-center gap-3">
                  <TypeBadge type={tx.type} />
                  <div>
                    <p className="text-sm text-slate-900">
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
                <span className={`text-sm font-bold ${tx.amount > 0 ? 'text-green-600' : 'text-red-500'}`}>
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
