import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { SCORE_GLOSSARY, LIKELIHOOD_MAP } from '../utils/scores';
import useDocumentTitle from '../hooks/useDocumentTitle';

const SECTION_IDS = {
  'Match Strength': 'match-strength',
  'Warm Score': 'warm-score',
  'Job Fit': 'job-fit',
  'Referral Likelihood': 'referral-likelihood',
};

export default function ScoreGlossary() {
  useDocumentTitle('How Scores Work');
  const navigate = useNavigate();
  const [guidanceOpen, setGuidanceOpen] = useState(null);

  return (
    <div className="mx-auto max-w-2xl" role="main">
      <div className="mb-6">
        <button
          onClick={() => navigate(-1)}
          className="mb-1 inline-block text-sm text-amber-400 hover:text-amber-300"
        >
          &larr; Back
        </button>
        <h1 className="text-xl font-bold text-slate-50">How Scores Work</h1>
        <p className="mt-1 text-sm text-slate-400">
          WarmPath uses a few key metrics to help you find the best referral paths. Here's what each one means.
        </p>
      </div>

      {/* Role-based guidance */}
      <div className="mb-6 space-y-2">
        <button
          onClick={() => setGuidanceOpen(guidanceOpen === 'seeker' ? null : 'seeker')}
          className="w-full rounded-lg border border-slate-700/50 bg-slate-800/50 px-4 py-3 text-left text-sm font-medium text-slate-200 hover:bg-slate-800"
          aria-expanded={guidanceOpen === 'seeker'}
        >
          <span className="flex items-center justify-between">
            Looking for a referral?
            <span className="text-slate-500">{guidanceOpen === 'seeker' ? '−' : '+'}</span>
          </span>
        </button>
        {guidanceOpen === 'seeker' && (
          <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 px-4 py-3 text-sm text-slate-400">
            <ul className="space-y-1.5">
              <li><strong className="text-slate-300">Match Strength</strong> — your main score in search results. It balances role relevance with connection warmth. Trust it to rank your options.</li>
              <li><strong className="text-slate-300">Warm Score</strong> — matters when choosing who to ask from your own network. Higher means they're more likely to respond.</li>
              <li><strong className="text-slate-300">Connection Strength</strong> — the marketplace version of Warm Score. Tells you how strong the network holder's relationship is with a contact before you spend credits.</li>
            </ul>
          </div>
        )}

        <button
          onClick={() => setGuidanceOpen(guidanceOpen === 'holder' ? null : 'holder')}
          className="w-full rounded-lg border border-slate-700/50 bg-slate-800/50 px-4 py-3 text-left text-sm font-medium text-slate-200 hover:bg-slate-800"
          aria-expanded={guidanceOpen === 'holder'}
        >
          <span className="flex items-center justify-between">
            Sharing your network?
            <span className="text-slate-500">{guidanceOpen === 'holder' ? '−' : '+'}</span>
          </span>
        </button>
        {guidanceOpen === 'holder' && (
          <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 px-4 py-3 text-sm text-slate-400">
            <ul className="space-y-1.5">
              <li><strong className="text-slate-300">Warm Score</strong> — reflects your relationship strength with each contact. It determines the Connection Strength label job seekers see in the marketplace.</li>
              <li><strong className="text-slate-300">Connection Strength</strong> — the anonymized version of your Warm Score that appears in marketplace listings. Higher scores attract more intro requests.</li>
            </ul>
          </div>
        )}
      </div>

      <div className="space-y-6">
        {SCORE_GLOSSARY.map((entry) => (
          <div key={entry.name} id={SECTION_IDS[entry.name]} className="rounded-xl bg-slate-900 p-5 border border-slate-700/50 scroll-mt-20">
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

        <div id="match-calculation" className="rounded-xl bg-slate-800/50 p-5 border border-slate-700/50 scroll-mt-20">
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

        {/* Navigation */}
        <div className="flex flex-wrap items-center gap-3 pt-2 text-sm">
          <Link to="/referrals" className="text-amber-400 hover:text-amber-300">Find referral paths &rarr;</Link>
          <span className="text-slate-600">&middot;</span>
          <button onClick={() => navigate(-1)} className="text-slate-400 hover:text-slate-300">
            &larr; Back
          </button>
        </div>
      </div>
    </div>
  );
}
