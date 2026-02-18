import { useCallback, useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { search as searchApi, matches as matchesApi } from '../api/client';
import MatchBadge from '../components/MatchBadge';
import ScoreExplainer from '../components/ScoreExplainer';
import { MATCH_TIERS } from '../utils/scores';

function IntroModal({ intro, onClose }) {
  if (!intro) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-labelledby="search-intro-modal-title">
      <div className="w-full max-w-xl rounded-xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <h2 id="search-intro-modal-title" className="text-lg font-semibold text-slate-900">Intro Drafts</h2>
          <button onClick={onClose} aria-label="Close intro drafts" className="text-slate-400 hover:text-slate-600 text-xl leading-none">&times;</button>
        </div>
        <div className="max-h-[70vh] overflow-y-auto px-6 py-4 space-y-4">
          {intro.messages?.map((msg) => (
            <div key={msg.id} className="rounded-lg border border-slate-200 p-4">
              <div className="mb-2 flex items-center justify-between">
                <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
                  {msg.variant_label}
                </span>
                <span className="text-xs text-slate-400">{msg.ai_model_version}</span>
              </div>
              {msg.subject_line && (
                <p className="mb-1 text-xs text-slate-500">
                  Subject: <span className="font-medium text-slate-700">{msg.subject_line}</span>
                </p>
              )}
              <p className="whitespace-pre-wrap text-sm text-slate-700">{msg.message_body}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
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

  const dist = meta.score_distribution || {};

  return (
    <div role="main">
      {/* Header */}
      <div className="mb-4 flex items-start justify-between">
        <div>
          <Link to="/dashboard" className="mb-1 inline-block text-sm text-amber-600 hover:text-amber-700">&larr; Dashboard</Link>
          <h1 className="text-2xl font-bold text-slate-900">{searchInfo?.name || 'Search Results'}</h1>
          {searchInfo?.description && (
            <p className="mt-1 text-sm text-slate-500">{searchInfo.description}</p>
          )}
        </div>
      </div>

      {/* Stats summary */}
      {meta.total_matches !== undefined && (
        <div className="mb-4 grid grid-cols-3 gap-3">
          <div className="rounded-lg bg-white p-3 ring-1 ring-slate-200">
            <p className="text-xs text-slate-500">Total Matches</p>
            <p className="text-lg font-bold text-slate-900">{meta.total_matches}</p>
          </div>
          <div className="rounded-lg bg-white p-3 ring-1 ring-slate-200">
            <p className="text-xs text-slate-500">
              Avg Match Strength
              <ScoreExplainer
                title="Match Strength"
                body="Combines role relevance (50%) and relationship warmth (50%)."
                tiers={MATCH_TIERS}
              />
            </p>
            <p className="text-lg font-bold text-slate-900">
              {meta.avg_relevance != null && meta.avg_warm != null
                ? Math.round((meta.avg_relevance + meta.avg_warm) / 2)
                : meta.avg_relevance ?? '—'}
            </p>
          </div>
          <div className="rounded-lg bg-white p-3 ring-1 ring-slate-200">
            <p className="text-xs text-slate-500">Strong+ Matches</p>
            <p className="text-lg font-bold text-green-600">
              {(dist['90-100'] || 0) + (dist['70-89'] || 0)}
            </p>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="mb-4 flex flex-wrap items-end gap-3 rounded-lg bg-white p-3 ring-1 ring-slate-200" role="search" aria-label="Filter search results">
        <div>
          <label htmlFor="filter-min-relevance" className="mb-1 block text-xs text-slate-500">
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
          <span className="ml-1 text-xs text-slate-600" aria-hidden="true">{filters.min_relevance}</span>
        </div>
        <div>
          <label htmlFor="filter-match-type" className="mb-1 block text-xs text-slate-500">Match Type</label>
          <select
            id="filter-match-type"
            value={filters.match_type}
            onChange={(e) => setFilter('match_type', e.target.value)}
            className="rounded-md border border-slate-300 px-2 py-1.5 text-xs"
          >
            <option value="">All</option>
            <option value="direct">Direct</option>
            <option value="indirect">Indirect</option>
            <option value="weak">Weak</option>
          </select>
        </div>
        <div>
          <label htmlFor="filter-company" className="mb-1 block text-xs text-slate-500">Company</label>
          <input
            id="filter-company"
            type="text"
            value={filters.company}
            onChange={(e) => setFilter('company', e.target.value)}
            placeholder="Filter..."
            className="w-32 rounded-md border border-slate-300 px-2 py-1.5 text-xs"
          />
        </div>
      </div>

      {/* Results table */}
      {loading ? (
        <div className="flex items-center justify-center py-12" aria-live="polite">
          <div className="h-6 w-6 animate-spin rounded-full border-4 border-amber-500 border-t-transparent" role="status" aria-label="Loading results" />
        </div>
      ) : results.length === 0 ? (
        <div className="rounded-lg bg-white p-8 text-center ring-1 ring-slate-200" aria-live="polite">
          <p className="text-sm text-slate-500">No matches found with current filters</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl bg-white shadow-sm ring-1 ring-slate-200">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50">
              <tr>
                <th className="px-4 py-3 font-medium text-slate-600">Contact</th>
                <th className="hidden px-4 py-3 font-medium text-slate-600 md:table-cell">Company</th>
                <th className="px-3 py-3 font-medium text-slate-600 text-center">
                  Match Strength
                  <ScoreExplainer title="Match Strength" body="Combines role relevance (50%) and relationship warmth (50%)." tiers={MATCH_TIERS} />
                </th>
                <th className="hidden px-3 py-3 font-medium text-slate-600 text-center sm:table-cell">Type</th>
                <th className="px-4 py-3 font-medium text-slate-600"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {results.map((r) => (
                <tr key={r.id} className="hover:bg-amber-50/30">
                  <td className="px-4 py-3">
                    <p className="font-medium text-slate-900">{r.contact_name}</p>
                    <p className="text-xs text-slate-500">{r.contact_title}</p>
                    <p className="text-xs text-slate-400 md:hidden">{r.contact_company}</p>
                  </td>
                  <td className="hidden px-4 py-3 text-slate-600 md:table-cell">{r.contact_company}</td>
                  <td className="px-3 py-3 text-center">
                    <MatchBadge score={r.combined_score} showScore />
                  </td>
                  <td className="hidden px-3 py-3 text-center sm:table-cell">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                      r.match_type === 'direct' ? 'bg-green-100 text-green-700' :
                      r.match_type === 'indirect' ? 'bg-amber-100 text-amber-700' :
                      'bg-slate-100 text-slate-600'
                    }`}>
                      {r.match_type}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => handleDraftIntro(r.contact_id)}
                      disabled={introLoading === r.contact_id}
                      className="whitespace-nowrap rounded-md bg-amber-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-600 disabled:opacity-50"
                    >
                      {introLoading === r.contact_id ? '...' : 'Draft Intro'}
                    </button>
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
          <p className="text-sm text-slate-500">
            Showing {results.length} of {meta.total_matches} matches (page {meta.page}/{meta.total_pages})
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => setFilters((f) => ({ ...f, page: f.page - 1 }))}
              disabled={filters.page <= 1}
              aria-label="Previous page"
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-50"
            >
              Prev
            </button>
            <button
              onClick={() => setFilters((f) => ({ ...f, page: f.page + 1 }))}
              disabled={filters.page >= meta.total_pages}
              aria-label="Next page"
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </nav>
      )}

      {introModal && <IntroModal intro={introModal} onClose={() => setIntroModal(null)} />}
    </div>
  );
}
