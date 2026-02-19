import { useCallback, useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { search as searchApi, matches as matchesApi } from '../api/client';
import MatchBadge from '../components/MatchBadge';
import ScoreExplainer from '../components/ScoreExplainer';
import { MATCH_TIERS } from '../utils/scores';
import Button from '../components/ui/Button';
import Spinner from '../components/ui/Spinner';
import Modal from '../components/ui/Modal';

function IntroModal({ intro, onClose }) {
  if (!intro) return null;
  return (
    <Modal open={!!intro} onClose={onClose} title="Intro Drafts" maxWidth="max-w-xl">
      <div className="space-y-4">
        {intro.messages?.map((msg) => (
          <div key={msg.id} className="rounded-lg border border-slate-700/50 p-4">
            <div className="mb-2 flex items-center justify-between">
              <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-400">
                {msg.variant_label}
              </span>
              <span className="text-xs text-slate-400">{msg.ai_model_version}</span>
            </div>
            {msg.subject_line && (
              <p className="mb-1 text-xs text-slate-400">
                Subject: <span className="font-medium text-slate-300">{msg.subject_line}</span>
              </p>
            )}
            <p className="whitespace-pre-wrap text-sm text-slate-300">{msg.message_body}</p>
          </div>
        ))}
      </div>
    </Modal>
  );
}

export default function SearchResults() {
  const { id } = useParams();
  const [searchInfo, setSearchInfo] = useState(null);
  const [results, setResults] = useState([]);
  const [meta, setMeta] = useState({});
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({
    min_relevance: 40, min_warm: '', match_type: '', company: '', page: 1, per_page: 20,
  });
  const [introLoading, setIntroLoading] = useState(null);
  const [introModal, setIntroModal] = useState(null);

  const loadResults = useCallback(async () => {
    setLoading(true);
    try {
      const params = { ...filters };
      if (!params.min_warm) delete params.min_warm;
      if (!params.match_type) delete params.match_type;
      if (!params.company) delete params.company;
      const res = await searchApi.results(id, params);
      setResults(res.data);
      setMeta(res.meta);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [id, filters]);

  useEffect(() => {
    searchApi.get(id).then((res) => setSearchInfo(res.data)).catch(console.error);
  }, [id]);

  useEffect(() => { loadResults(); }, [loadResults]);

  const setFilter = (key, value) => {
    setFilters((f) => ({ ...f, [key]: value, page: 1 }));
  };

  const handleDraftIntro = async (contactId) => {
    setIntroLoading(contactId);
    try {
      const res = await matchesApi.createIntro({
        contact_id: contactId,
        tone: 'professional',
        channel: 'linkedin',
      });
      setIntroModal(res.data);
    } catch (err) {
      alert(err.message);
    } finally {
      setIntroLoading(null);
    }
  };

  const dist = meta.sco[RESEND_KEY_REDACTED] || {};

  return (
    <div role="main">
      {/* Header */}
      <div className="mb-4 flex items-start justify-between">
        <div>
          <Link to="/coach" className="mb-1 inline-block text-sm text-amber-400 hover:text-amber-300">&larr; Coach</Link>
          <h1 className="text-2xl font-bold text-slate-50">{searchInfo?.name || 'Search Results'}</h1>
          {searchInfo?.description && (
            <p className="mt-1 text-sm text-slate-400">{searchInfo.description}</p>
          )}
        </div>
      </div>

      {/* Stats summary */}
      {meta.total_matches !== undefined && (
        <div className="mb-4 grid grid-cols-3 gap-3">
          <div className="rounded-lg bg-slate-900 p-3 border border-slate-700/50">
            <p className="text-xs text-slate-400">Total Matches</p>
            <p className="text-lg font-bold text-slate-50">{meta.total_matches}</p>
          </div>
          <div className="rounded-lg bg-slate-900 p-3 border border-slate-700/50">
            <p className="text-xs text-slate-400">
              Avg Match Strength
              <ScoreExplainer
                title="Match Strength"
                body="Combines role relevance (50%) and relationship warmth (50%)."
                tiers={MATCH_TIERS}
              />
            </p>
            <p className="text-lg font-bold text-slate-50">
              {meta.avg_relevance != null && meta.avg_warm != null
                ? Math.round((meta.avg_relevance + meta.avg_warm) / 2)
                : meta.avg_relevance ?? '—'}
            </p>
          </div>
          <div className="rounded-lg bg-slate-900 p-3 border border-slate-700/50">
            <p className="text-xs text-slate-400">Strong+ Matches</p>
            <p className="text-lg font-bold text-emerald-400">
              {(dist['90-100'] || 0) + (dist['70-89'] || 0)}
            </p>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="mb-4 flex flex-wrap items-end gap-3 rounded-lg bg-slate-900 p-3 border border-slate-700/50" role="search" aria-label="Filter search results">
        <div>
          <label htmlFor="filter-min-relevance" className="mb-1 block text-xs text-slate-400">
            Min Match Strength
            <ScoreExplainer title="Match Strength" body="Filters out contacts below this combined score (relevance + warmth)." />
          </label>
          <input
            id="filter-min-relevance"
            type="range"
            min="0" max="100" step="10"
            value={filters.min_relevance}
            onChange={(e) => setFilter('min_relevance', Number(e.target.value))}
            aria-valuenow={filters.min_relevance}
            aria-valuemin={0}
            aria-valuemax={100}
            className="w-28 accent-amber-500"
          />
          <span className="ml-1 text-xs text-slate-400" aria-hidden="true">{filters.min_relevance}</span>
        </div>
        <div>
          <label htmlFor="filter-match-type" className="mb-1 block text-xs text-slate-400">Match Type</label>
          <select
            id="filter-match-type"
            value={filters.match_type}
            onChange={(e) => setFilter('match_type', e.target.value)}
            className="rounded-md border-slate-700/50 bg-slate-800 px-2 py-1.5 text-xs text-slate-100 focus:border-amber-500"
          >
            <option value="">All</option>
            <option value="direct">Direct</option>
            <option value="indirect">Indirect</option>
            <option value="weak">Weak</option>
          </select>
        </div>
        <div>
          <label htmlFor="filter-company" className="mb-1 block text-xs text-slate-400">Company</label>
          <input
            id="filter-company"
            type="text"
            value={filters.company}
            onChange={(e) => setFilter('company', e.target.value)}
            placeholder="Filter..."
            className="w-32 rounded-md border-slate-700/50 bg-slate-800 px-2 py-1.5 text-xs text-slate-100 placeholder-slate-500 focus:border-amber-500"
          />
        </div>
      </div>

      {/* Results table */}
      {loading ? (
        <div className="flex items-center justify-center py-12" aria-live="polite">
          <Spinner size="md" />
        </div>
      ) : results.length === 0 ? (
        <div className="rounded-xl bg-slate-900 p-12 text-center border border-slate-700/50" aria-live="polite">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-slate-800" aria-hidden="true">
            <svg className="h-7 w-7 text-slate-400" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
            </svg>
          </div>
          <h2 className="mb-2 text-base font-semibold text-slate-50">No matches found</h2>
          <p className="mx-auto mb-4 max-w-sm text-sm text-slate-400">
            No contacts matched your current filters. Try lowering the minimum match strength or clearing the company filter.
          </p>
          <button
            onClick={() => setFilters({ min_relevance: 0, min_warm: '', match_type: '', company: '', page: 1, per_page: 20 })}
            className="inline-block rounded-lg bg-amber-500 px-6 py-2.5 text-sm font-medium text-white hover:bg-amber-400"
          >
            Reset Filters
          </button>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl bg-slate-900 border border-slate-700/50">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-700/50 bg-slate-800/50">
              <tr>
                <th className="px-4 py-3 font-medium text-slate-400">Contact</th>
                <th className="hidden px-4 py-3 font-medium text-slate-400 md:table-cell">Company</th>
                <th className="px-3 py-3 font-medium text-slate-400 text-center">
                  Match Strength
                  <ScoreExplainer title="Match Strength" body="Combines role relevance (50%) and relationship warmth (50%)." tiers={MATCH_TIERS} />
                </th>
                <th className="hidden px-3 py-3 font-medium text-slate-400 text-center sm:table-cell">Type</th>
                <th className="px-4 py-3 font-medium text-slate-400"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/50">
              {results.map((r) => (
                <tr key={r.id} className="hover:bg-slate-800/50">
                  <td className="px-4 py-3">
                    <p className="font-medium text-slate-50">{r.contact_name}</p>
                    <p className="text-xs text-slate-400">{r.contact_title}</p>
                    <p className="text-xs text-slate-400 md:hidden">{r.contact_company}</p>
                  </td>
                  <td className="hidden px-4 py-3 text-slate-400 md:table-cell">{r.contact_company}</td>
                  <td className="px-3 py-3 text-center">
                    <MatchBadge score={r.combined_score} showScore />
                  </td>
                  <td className="hidden px-3 py-3 text-center sm:table-cell">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                      r.match_type === 'direct' ? 'bg-emerald-500/10 text-emerald-400' :
                      r.match_type === 'indirect' ? 'bg-amber-500/10 text-amber-400' :
                      'bg-slate-700/50 text-slate-400'
                    }`}>
                      {r.match_type}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <Button
                      onClick={() => handleDraftIntro(r.contact_id)}
                      loading={introLoading === r.contact_id}
                      size="sm"
                    >
                      Draft Intro
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {meta.total_pages > 1 && (
        <nav className="mt-4 flex items-center justify-between" aria-label="Search results pagination">
          <p className="text-sm text-slate-400">
            Showing {results.length} of {meta.total_matches} matches (page {meta.page}/{meta.total_pages})
          </p>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setFilters((f) => ({ ...f, page: f.page - 1 }))}
              disabled={filters.page <= 1}
              aria-label="Previous page"
            >
              Prev
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setFilters((f) => ({ ...f, page: f.page + 1 }))}
              disabled={filters.page >= meta.total_pages}
              aria-label="Next page"
            >
              Next
            </Button>
          </div>
        </nav>
      )}

      {introModal && <IntroModal intro={introModal} onClose={() => setIntroModal(null)} />}
    </div>
  );
}
