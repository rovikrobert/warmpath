import { SOURCES } from './sources';

/** Trivia facts Keevs shares during CSV upload processing. */
export const KEEVS_TRIVIA = [
  {
    text: `Cold applications convert at 1-3%. Referrals convert at ${SOURCES.COLD_VS_REFERRAL.claim}. The same resume, a completely different outcome.`,
    source: SOURCES.COLD_VS_REFERRAL,
  },
  {
    text: `Up to 80% of jobs are filled before they're ever posted publicly. Your network is the only way into that market.`,
    source: SOURCES.HIDDEN_JOB_MARKET,
  },
  {
    text: `Referred candidates get ${SOURCES.REFERRAL_INTERVIEW_MULTIPLIER.claim} more interviews than cold applicants — not because they're better, but because someone vouched.`,
    source: SOURCES.REFERRAL_INTERVIEW_MULTIPLIER,
  },
  {
    text: `Referral hires close in ${SOURCES.REFERRAL_HIRE_SPEED.claim} for non-referral hires. Fewer rounds, faster offer.`,
    source: SOURCES.REFERRAL_HIRE_SPEED,
  },
  {
    text: `${SOURCES.NETWORKING_HIRES.claim} of jobs are filled through networking. Most people know this. Few people have a system for it — until now.`,
    source: SOURCES.NETWORKING_HIRES,
  },
  {
    text: `${SOURCES.REFERRAL_RETENTION.claim} of referral hires stay over a year. They land better-fit roles because someone who knew the culture vouched for them.`,
    source: SOURCES.REFERRAL_RETENTION,
  },
  {
    text: `Your contacts at target companies may earn ${SOURCES.REFERRAL_BONUS_RANGE.claim} for referring you. Helping you is literally good for them.`,
    source: SOURCES.REFERRAL_BONUS_RANGE,
  },
  {
    text: 'WarmPath scores every contact on recency, relationship strength, and referral likelihood — so you lead with your best path, not your closest friend.',
    source: null,
  },
];

/** Fisher-Yates shuffle (returns new array). */
export function shuffleArray<T>(arr: T[]): T[] {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}
