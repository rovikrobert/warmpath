import { Link } from 'react-router-dom';
import { SCORE_GLOSSARY, LIKELIHOOD_MAP } from '../utils/scores';

export default function ScoreGlossary() {
  return (
    <div className="mx-auto max-w-2xl" role="main">
      <div className="mb-6">
        <Link to="/dashboard" className="mb-1 inline-block text-sm text-amber-400 hover:text-amber-300">
          &larr; Dashboard
        </Link>
        <h1 className="text-xl font-bold text-slate-50">How Scores Work</h1>
        <p className="mt-1 text-sm text-slate-400">
          WarmPath uses a few key metrics to help you find the best referral paths. Here's what each one means.
        </p>
      </div>

      <div className="space-y-6">
        {SCORE_GLOSSARY.map((entry) => (
          <div key={entry.name} className="rounded-xl bg-slate-900 p-5 border border-slate-700/50">
            <div className="mb-2 flex items-center gap-3">
              <h2 className="text-base font-semibold text-slate-50">{entry.name}</h2>
              <span className="rounded-full bg-slate-700/50 px-2 py-0.5 text-xs text-slate-400">
                {entry.range}
              </span>
            </div>
            <p className="mb-3 text-sm text-slate-400">{entry.description}</p>

            {entry.tiers ? (
              <div className="space-y-2">
                {entry.tiers.map((tier) => (
                  <div key={tier.label} className="flex items-start gap-3">
                    <span className={`mt-0.5 shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${tier.color}`}>
                      {tier.min != null ? `${tier.min}+` : tier.label}
                    </span>
                    <div>
                      <span className="text-sm font-medium text-slate-300">{tier.label}</span>
                      {tier.desc && <p className="text-xs text-slate-400">{tier.desc}</p>}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="space-y-2">
                {Object.entries(LIKELIHOOD_MAP).map(([key, val]) => (
                  <div key={key} className="flex items-center gap-3">
                    <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${val.color}`}>
                      {key}
                    </span>
                    <span className="text-sm text-slate-400">{val.label}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}

        <div className="rounded-xl bg-slate-800/50 p-5 border border-slate-700/50">
          <h2 className="mb-2 text-base font-semibold text-slate-50">How Match Strength is calculated</h2>
          <p className="text-sm text-slate-400">
            Match Strength combines two factors equally:
          </p>
          <ul className="mt-2 space-y-1 text-sm text-slate-400">
            <li><strong className="text-slate-300">Role Relevance (50%)</strong> — How well the contact's role and company match what you're looking for.</li>
            <li><strong className="text-slate-300">Warm Score (50%)</strong> — How strong your connection is to this person.</li>
          </ul>
          <p className="mt-3 text-xs text-slate-400">
            Formula: Match Strength = (Relevance &times; 0.5) + (Warm Score &times; 0.5)
          </p>
        </div>
      </div>
    </div>
  );
}
