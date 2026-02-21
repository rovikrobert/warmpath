/**
 * Canonical source registry for all stats/claims cited in the frontend.
 * Import from here — never hardcode source text inline.
 */
export const SOURCES = {
  REFERRAL_CONVERSION: {
    claim: '10-40%',
    label: 'referral conversion rate',
    source: 'LinkedIn Talent Solutions, Jobvite Recruiter Nation Report',
  },
  REFERRAL_INTERVIEW_MULTIPLIER: {
    claim: 'up to 4x',
    label: 'more interviews via referrals',
    source: 'LinkedIn Talent Solutions, Glassdoor Employer Survey',
  },
  REFERRAL_BONUS_RANGE: {
    claim: '$2,000-$10,000',
    label: 'per referral hire (varies by employer)',
    source: 'CareerBuilder, Glassdoor Employer Survey (US tech sector)',
  },
  COLD_VS_REFERRAL: {
    claim: '10-40% vs 1-3%',
    label: 'referral vs cold application conversion',
    source: 'LinkedIn Talent Solutions, Jobvite Recruiter Nation Report',
  },
  REFERRAL_HIRE_SPEED: {
    claim: '29 days vs 39-55 days',
    label: 'referral vs non-referral time-to-hire',
    source: 'Jobvite Recruiter Nation Report',
  },
  REFERRAL_RETENTION: {
    claim: '46%',
    label: 'referral hires stay 1+ years',
    source: 'Jobvite Recruiter Nation Report',
  },
  HIDDEN_JOB_MARKET: {
    claim: 'up to 80%',
    label: 'jobs filled before public posting',
    source: 'CNBC, Bureau of Labor Statistics analysis',
  },
  NETWORKING_HIRES: {
    claim: '85%',
    label: 'jobs filled through networking',
    source: 'LinkedIn Workforce Report, HBS Working Knowledge',
  },
};
