/**
 * Canonical source registry for all stats/claims cited in the frontend.
 * Import from here — never hardcode source text inline.
 */
export const SOURCES = {
  REFERRAL_CONVERSION: {
    claim: '10-40%',
    label: 'Referral conversion rate',
    source: 'LinkedIn Talent Solutions, Jobvite Recruiter Nation Report',
  },
  REFERRAL_INTERVIEW_MULTIPLIER: {
    claim: 'up to 4x',
    label: 'More interviews via referrals',
    source: 'LinkedIn Talent Solutions, Glassdoor Employer Survey',
  },
  REFERRAL_BONUS_RANGE: {
    claim: '$2,000-$10,000',
    label: 'Per referral hire (varies by employer)',
    source: 'CareerBuilder, Glassdoor Employer Survey (US tech sector)',
  },
  COLD_VS_REFERRAL: {
    claim: '10-40% vs 1-3%',
    label: 'Referral vs cold application conversion',
    source: 'LinkedIn Talent Solutions, Jobvite Recruiter Nation Report',
  },
  REFERRAL_HIRE_SPEED: {
    claim: '29 days vs 39-55 days',
    label: 'Referral vs non-referral time-to-hire',
    source: 'Jobvite Recruiter Nation Report',
  },
  REFERRAL_RETENTION: {
    claim: '46%',
    label: 'Referral hires stay 1+ years',
    source: 'Jobvite Recruiter Nation Report',
  },
  HIDDEN_JOB_MARKET: {
    claim: 'up to 80%',
    label: 'Jobs filled before public posting',
    source: 'CNBC, Bureau of Labor Statistics analysis',
  },
  NETWORKING_HIRES: {
    claim: '85%',
    label: 'Jobs filled through networking',
    source: 'LinkedIn Workforce Report, HBS Working Knowledge',
  },
};
