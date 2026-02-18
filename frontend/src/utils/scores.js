/**
 * Centralized score tier definitions for WarmPath.
 *
 * Single source of truth for all score thresholds, labels, and colors.
 * Every page that displays a score should import from here.
 */

// -- Match Strength (combined_score from search results) --------------------

export const MATCH_TIERS = [
  { min: 80, label: 'Excellent', color: 'bg-emerald-500/10 text-emerald-400', dot: 'bg-emerald-500' },
  { min: 60, label: 'Strong',    color: 'bg-emerald-500/10 text-emerald-400', dot: 'bg-emerald-500' },
  { min: 40, label: 'Good',      color: 'bg-amber-500/10 text-amber-400', dot: 'bg-amber-500' },
  { min: 0,  label: 'Fair',      color: 'bg-slate-700/50 text-slate-400', dot: 'bg-slate-400' },
];

// -- Warm Score (contact relationship warmth) --------------------------------

export const WARM_TIERS = [
  { min: 70, label: 'Strong',   color: 'bg-emerald-500/10 text-emerald-400', desc: 'Recent contact, strong relationship — ideal referral path' },
  { min: 40, label: 'Moderate', color: 'bg-amber-500/10 text-amber-400', desc: 'Some connection — may need a warm-up message first' },
  { min: 0,  label: 'Weak',     color: 'bg-slate-700/50 text-slate-400', desc: 'Distant or old connection — consider building rapport before asking' },
];

// -- Fit Score (job opening relevance to your profile) -----------------------

export const FIT_TIERS = [
  { min: 80, label: 'Great fit', color: 'bg-emerald-500/10 text-emerald-400' },
  { min: 50, label: 'Good fit',  color: 'bg-amber-500/10 text-amber-400' },
  { min: 0,  label: 'Possible',  color: 'bg-slate-700/50 text-slate-500' },
];

// -- Referral Likelihood (high / medium / low) -------------------------------

export const LIKELIHOOD_MAP = {
  high:   { label: 'Likely to refer', color: 'bg-emerald-500/10 text-emerald-400' },
  medium: { label: 'May refer',       color: 'bg-amber-500/10 text-amber-400' },
  low:    { label: 'Unlikely',        color: 'bg-slate-700/50 text-slate-400' },
};

// -- Helpers ----------------------------------------------------------------

export function getMatchTier(score) {
  return MATCH_TIERS.find((t) => score >= t.min) || MATCH_TIERS[MATCH_TIERS.length - 1];
}

export function getWarmTier(score) {
  return WARM_TIERS.find((t) => score >= t.min) || WARM_TIERS[WARM_TIERS.length - 1];
}

export function getFitTier(score) {
  return FIT_TIERS.find((t) => score >= t.min) || FIT_TIERS[FIT_TIERS.length - 1];
}

export function getLikelihood(level) {
  return LIKELIHOOD_MAP[level] || LIKELIHOOD_MAP.low;
}

// -- Glossary entries (used by /help/scores page) ---------------------------

export const SCORE_GLOSSARY = [
  {
    name: 'Match Strength',
    range: '0-100',
    description: 'Overall fit between you and a contact, combining role relevance (50%) and relationship warmth (50%).',
    tiers: MATCH_TIERS,
  },
  {
    name: 'Warm Score',
    range: '0-100',
    description: 'How likely this person is to respond to your referral request. Based on recency (35%), relationship strength (30%), role relevance (20%), and tenure (15%).',
    tiers: WARM_TIERS,
  },
  {
    name: 'Job Fit',
    range: '0-100',
    description: 'How well a specific job opening matches your target role and preferences (title, seniority, location).',
    tiers: FIT_TIERS,
  },
  {
    name: 'Referral Likelihood',
    range: 'High / Medium / Low',
    description: 'Estimate of whether this person would actually refer you, based on relationship type, tenure, and past behavior patterns.',
    tiers: null,
  },
];
