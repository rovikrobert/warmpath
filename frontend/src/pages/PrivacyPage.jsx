import { useState } from 'react';
import { Link } from 'react-router-dom';
import useDocumentTitle from '../hooks/useDocumentTitle';

const SECTIONS = [
  { id: 'commitment', label: 'Our Privacy Commitment' },
  { id: 'four-parties', label: 'The Four Parties' },
  { id: 'collect', label: 'Information We Collect' },
  { id: 'use', label: 'How We Use Your Information' },
  { id: 'vault', label: 'Private Vault & Marketplace' },
  { id: 'sharing', label: 'Data Sharing' },
  { id: 'suppression', label: 'Suppression List' },
  { id: 'rights', label: 'Your Rights' },
  { id: 'ai', label: 'AI & Automated Processing' },
  { id: 'retention', label: 'Data Retention' },
  { id: 'contact', label: 'Contact Us' },
];

function SectionHeading({ id, children }) {
  return (
    <h2 id={id} className="scroll-mt-24 text-xl font-bold text-slate-50">
      {children}
    </h2>
  );
}

function Paragraph({ children }) {
  return <p className="text-sm leading-relaxed text-slate-300">{children}</p>;
}

function BulletList({ items }) {
  return (
    <ul className="space-y-1.5 pl-5">
      {items.map((item, i) => (
        <li key={i} className="list-disc text-sm leading-relaxed text-slate-300">
          {item}
        </li>
      ))}
    </ul>
  );
}

function InfoCard({ icon, title, children }) {
  return (
    <div className="rounded-lg border border-slate-700/50 bg-slate-800/50 p-4">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-lg" aria-hidden="true">{icon}</span>
        <h4 className="font-semibold text-slate-50">{title}</h4>
      </div>
      <div className="text-sm leading-relaxed text-slate-300">{children}</div>
    </div>
  );
}

export default function PrivacyPage() {
  useDocumentTitle('Privacy Policy');
  const [rightsTab, setRightsTab] = useState('gdpr');

  return (
    <div className="min-h-screen bg-slate-950">
      {/* Minimal nav bar */}
      <header className="border-b border-slate-700/50 bg-slate-900">
        <nav className="mx-auto flex max-w-3xl items-center justify-between px-4 py-3 sm:px-6" role="navigation" aria-label="Privacy page navigation">
          <Link to="/" className="flex items-center gap-2 text-xl font-bold text-slate-50" aria-label="WarmPath home">
            <span className="text-amber-500">~</span>
            <span>WarmPath</span>
          </Link>
          <Link to="/" className="text-sm text-amber-400 hover:text-amber-300">
            Back to app
          </Link>
        </nav>
      </header>

    <main className="mx-auto max-w-3xl space-y-8 px-4 py-8 pb-16 sm:px-6">
      {/* Header */}
      <div className="space-y-2">
        <h1 className="text-2xl font-bold text-slate-50">Privacy Policy</h1>
        <p className="text-sm text-slate-400">
          WarmPath &mdash; operated by Majiq Pte Ltd, Singapore
        </p>
        <p className="text-xs text-slate-400">
          Effective Date: 16 February 2026 &middot; Last Updated: 16 February 2026
        </p>
      </div>

      {/* Table of Contents */}
      <nav className="rounded-xl bg-slate-900 p-5 border border-slate-700/50" aria-label="Table of contents">
        <h3 className="mb-3 text-sm font-semibold text-slate-50">Contents</h3>
        <ol className="grid gap-1.5 sm:grid-cols-2">
          {SECTIONS.map((s, i) => (
            <li key={s.id}>
              <a
                href={`#${s.id}`}
                className="text-sm text-amber-400 hover:text-amber-300 hover:underline"
              >
                {i + 1}. {s.label}
              </a>
            </li>
          ))}
        </ol>
      </nav>

      {/* 1. Our Privacy Commitment */}
      <section className="space-y-4 rounded-xl bg-slate-900 p-6 border border-slate-700/50">
        <SectionHeading id="commitment">
          <span className="mr-2 inline-flex h-7 w-7 items-center justify-center rounded-full bg-amber-500/10 text-sm text-amber-400">1</span>
          Our Privacy Commitment
        </SectionHeading>
        <Paragraph>
          Privacy is not a feature of WarmPath &mdash; it is our foundational architecture.
          People exploring new opportunities need absolute confidence that their current employer
          cannot discover their search. Those sharing connections need assurance that their
          contacts are protected. Third-party contacts referenced in uploaded data need
          safeguards even though they have not created accounts.
        </Paragraph>
        <div className="grid gap-3 sm:grid-cols-2">
          <InfoCard icon={<svg className="h-5 w-5 text-emerald-400" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z" /></svg>} title="Private Vault">
            Your full contact data is visible only to you. We never share it without your explicit consent.
          </InfoCard>
          <InfoCard icon={<svg className="h-5 w-5 text-emerald-400" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z" /></svg>} title="Consent Gates">
            Contact identity is revealed only through the connection owner's explicit, active approval.
          </InfoCard>
          <InfoCard icon={<svg className="h-5 w-5 text-emerald-400" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M18.364 18.364A9 9 0 0 0 5.636 5.636m12.728 12.728A9 9 0 0 1 5.636 5.636m12.728 12.728L5.636 5.636" /></svg>} title="Never Sell Data">
            We never sell, rent, or trade your personal data or contact data to third parties.
          </InfoCard>
          <InfoCard icon={<svg className="h-5 w-5 text-emerald-400" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M15 12H9m12 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" /></svg>} title="Data Minimisation">
            We collect only what is necessary to deliver the service. CSV files are deleted after processing.
          </InfoCard>
        </div>
      </section>

      {/* 2. The Four Parties */}
      <section className="space-y-4 rounded-xl bg-slate-900 p-6 border border-slate-700/50">
        <SectionHeading id="four-parties">
          <span className="mr-2 inline-flex h-7 w-7 items-center justify-center rounded-full bg-amber-500/10 text-sm text-amber-400">2</span>
          The Four Parties
        </SectionHeading>
        <Paragraph>
          WarmPath's data model involves four categories of individuals, each with different
          privacy needs. These categories are not mutually exclusive &mdash; a single person may
          simultaneously occupy multiple roles.
        </Paragraph>
        <div className="space-y-3">
          <InfoCard icon={<svg className="h-5 w-5 text-blue-400" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" /></svg>} title="People Seeking Referrals">
            Your account, search activity, target companies, and application pipeline are private.
            You remain anonymous in the marketplace until you choose to request an introduction.
            No employer &mdash; including yours &mdash; can discover you're looking.
          </InfoCard>
          <InfoCard icon={<svg className="h-5 w-5 text-purple-400" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M7.217 10.907a2.25 2.25 0 1 0 0 2.186m0-2.186c.18.324.283.696.283 1.093s-.103.77-.283 1.093m0-2.186 9.566-5.314m-9.566 7.5 9.566 5.314m0 0a2.25 2.25 0 1 0 3.935 2.186 2.25 2.25 0 0 0-3.935-2.186Zm0-12.814a2.25 2.25 0 1 0 3.933-2.185 2.25 2.25 0 0 0-3.933 2.185Z" /></svg>} title="Connection Owners">
            Marketplace participation is entirely opt-in. Your identity as a facilitator is not
            disclosed to third parties. You retain granular controls over which contacts are
            shared and can pause or withdraw at any time.
          </InfoCard>
          <InfoCard icon={<svg className="h-5 w-5 text-amber-400" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 0 0 2.625.372 9.337 9.337 0 0 0 4.121-.952 4.125 4.125 0 0 0-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 0 1 8.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0 1 11.964-3.07M12 6.375a3.375 3.375 0 1 1-6.75 0 3.375 3.375 0 0 1 6.75 0Zm8.25 2.25a2.625 2.625 0 1 1-5.25 0 2.625 2.625 0 0 1 5.25 0Z" /></svg>} title="Contacts Referenced">
            Protected through anonymisation in the marketplace (no names or emails in listings),
            consent gates (identity revealed only when the connection owner approves), and the
            suppression list (any person may request permanent removal).
          </InfoCard>
          <InfoCard icon={<svg className="h-5 w-5 text-slate-400" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.375c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21" /></svg>} title="Companies">
            Employee directory information is aggregated to role level and department category
            in the marketplace &mdash; never specific titles, teams, or org charts.
          </InfoCard>
        </div>
        <Paragraph>
          Where roles overlap, the strongest privacy protection prevails. Referral-seeking
          activity stays invisible even if you also share connections. We never merge data
          across vaults.
        </Paragraph>
      </section>

      {/* 3. Information We Collect */}
      <section className="space-y-4 rounded-xl bg-slate-900 p-6 border border-slate-700/50">
        <SectionHeading id="collect">
          <span className="mr-2 inline-flex h-7 w-7 items-center justify-center rounded-full bg-amber-500/10 text-sm text-amber-400">3</span>
          Information We Collect
        </SectionHeading>
        <div className="space-y-3">
          <div>
            <h4 className="mb-1 font-semibold text-slate-200">Account Information</h4>
            <Paragraph>
              Name, email address, and password (hashed &mdash; we never store plaintext passwords).
              Optionally: job title, target roles, industries, and salary preferences.
            </Paragraph>
          </div>
          <div>
            <h4 className="mb-1 font-semibold text-slate-200">Contact Data (CSV Upload)</h4>
            <Paragraph>
              When you upload a LinkedIn connections CSV, we parse and store first name, last name,
              email address, company, position, and connection date. CSV files are deleted from
              our servers after processing.
            </Paragraph>
          </div>
          <div>
            <h4 className="mb-1 font-semibold text-slate-200">Usage Data</h4>
            <Paragraph>
              IP address, browser type, pages visited, feature usage, and diagnostic data.
              We track API calls, searches, and messages drafted to understand engagement and
              enforce rate limits.
            </Paragraph>
          </div>
          <div>
            <h4 className="mb-1 font-semibold text-slate-200">Cookies</h4>
            <Paragraph>
              Essential cookies for authentication and session management. Analytics cookies to
              understand service usage. We do not use advertising or remarketing cookies.
            </Paragraph>
          </div>
        </div>
      </section>

      {/* 4. How We Use Your Information */}
      <section className="space-y-4 rounded-xl bg-slate-900 p-6 border border-slate-700/50">
        <SectionHeading id="use">
          <span className="mr-2 inline-flex h-7 w-7 items-center justify-center rounded-full bg-amber-500/10 text-sm text-amber-400">4</span>
          How We Use Your Information
        </SectionHeading>
        <BulletList items={[
          'Provide referral path discovery, warm score computation, AI-powered message drafting, application tracking, and job opening alerts.',
          'Process AI features such as culturally-aware message drafting. Contact data sent to Anthropic\'s API is not retained beyond the request lifecycle.',
          'Compute warm scores using algorithmic analysis performed locally on our infrastructure, never shared externally.',
          'Operate the marketplace by generating anonymised listings from opted-in contacts and facilitating consent-gated introductions.',
          'Manage credits, billing, and subscription status.',
          'Enforce rate limits and prevent abuse (spam, scraping, misuse).',
          'Improve the service through aggregated, de-identified analytics.',
          'Comply with legal obligations and respond to lawful requests.',
        ]} />
      </section>

      {/* 5. Private Vault & Marketplace */}
      <section className="space-y-4 rounded-xl bg-slate-900 p-6 border border-slate-700/50">
        <SectionHeading id="vault">
          <span className="mr-2 inline-flex h-7 w-7 items-center justify-center rounded-full bg-amber-500/10 text-sm text-amber-400">5</span>
          Private Vault & Marketplace
        </SectionHeading>
        <Paragraph>
          WarmPath operates a two-tier data model designed to protect all parties:
        </Paragraph>
        <div className="space-y-4">
          <div className="rounded-lg border-l-4 border-amber-400 bg-amber-500/10 p-4">
            <h4 className="mb-1 font-semibold text-slate-50">Private Vault</h4>
            <p className="text-sm text-slate-300">
              All contact data you import is stored in your Private Vault &mdash; encrypted, scoped
              to your user account, and accessible only by you. We do not cross-reference data
              between users' vaults.
            </p>
          </div>
          <div className="rounded-lg border-l-4 border-emerald-400 bg-emerald-500/10 p-4">
            <h4 className="mb-1 font-semibold text-slate-50">Marketplace Index</h4>
            <p className="text-sm text-slate-300">
              If you opt in, an anonymised index is generated: company name, role level,
              department category, warm score range, and connection recency. No names, no
              emails, no specific titles cross the vault boundary.
            </p>
          </div>
        </div>
        <div>
          <h4 className="mb-2 font-semibold text-slate-200">Consent-Gated Disclosure Flow</h4>
          <ol className="space-y-2 pl-5">
            {[
              'The person seeking a referral sees an anonymous listing ("1 senior engineer at Stripe, strong connection").',
              'They request an introduction (spends credits).',
              'The connection owner reviews the request and the specific contact involved.',
              'The connection owner actively approves or declines.',
              'Only upon approval is the contact\'s identity revealed \u2014 through the connection owner\'s active choice.',
            ].map((step, i) => (
              <li key={i} className="list-decimal text-sm leading-relaxed text-slate-300">
                {step}
              </li>
            ))}
          </ol>
          <p className="mt-2 text-sm font-medium text-slate-300">
            At no point does WarmPath unilaterally reveal any contact's identity to another user.
          </p>
        </div>
      </section>

      {/* 6. Data Sharing */}
      <section className="space-y-4 rounded-xl bg-slate-900 p-6 border border-slate-700/50">
        <SectionHeading id="sharing">
          <span className="mr-2 inline-flex h-7 w-7 items-center justify-center rounded-full bg-amber-500/10 text-sm text-amber-400">6</span>
          Data Sharing
        </SectionHeading>
        <Paragraph>
          We do not sell, rent, or trade your personal data. We share information only with:
        </Paragraph>
        <BulletList items={[
          'Service providers who process data on our behalf under contractual agreements: cloud hosting (Railway), Stripe (payments), AI providers (Anthropic, Google, Groq, OpenAI), Resend (email delivery).',
          'Marketplace participants \u2014 only when a connection owner explicitly approves an introduction request.',
          'Legal authorities when required by law to comply with legal obligations or protect rights and safety.',
        ]} />
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4">
          <h4 className="mb-1 font-semibold text-red-400">What We Will Never Do</h4>
          <BulletList items={[
            'Sell your contact data to recruiters, advertisers, or data brokers.',
            'Share your referral-seeking activity with your current employer.',
            'Expose contact identities without explicit, active consent from the connection owner.',
            'Use your data to build profiles for advertising or promotional targeting by third parties.',
          ]} />
        </div>
      </section>

      {/* 7. Suppression List */}
      <section className="space-y-4 rounded-xl bg-slate-900 p-6 border border-slate-700/50">
        <SectionHeading id="suppression">
          <span className="mr-2 inline-flex h-7 w-7 items-center justify-center rounded-full bg-amber-500/10 text-sm text-amber-400">7</span>
          Suppression List
        </SectionHeading>
        <Paragraph>
          Any individual &mdash; whether or not they have a WarmPath account &mdash; may request removal
          from the platform.
        </Paragraph>
        <div className="space-y-2">
          <h4 className="font-semibold text-slate-200">How It Works</h4>
          <BulletList items={[
            'We match requests using SHA-256 hashing of normalised email addresses and/or name-plus-company combinations.',
            'Matching records are purged across all users\' private vaults.',
            'The individual is added to a permanent suppression list, blocking all future CSV imports.',
            'Connection owners are notified a contact was removed (but not who requested it).',
            'Removal is permanent unless the individual contacts us to be taken off.',
          ]} />
        </div>
        <Paragraph>
          To request suppression, email{' '}
          <a href="mailto:rovik@majiq.agency" className="font-medium text-amber-400 hover:text-amber-300">
            rovik@majiq.agency
          </a>{' '}
          with the subject line &ldquo;Suppression Request.&rdquo;
        </Paragraph>
      </section>

      {/* 8. Your Rights */}
      <section className="space-y-4 rounded-xl bg-slate-900 p-6 border border-slate-700/50">
        <SectionHeading id="rights">
          <span className="mr-2 inline-flex h-7 w-7 items-center justify-center rounded-full bg-amber-500/10 text-sm text-amber-400">8</span>
          Your Rights
        </SectionHeading>
        <Paragraph>
          Your rights depend on your jurisdiction. Select the applicable regulation below:
        </Paragraph>

        {/* Tabs */}
        <div className="flex gap-1 overflow-x-auto rounded-lg bg-slate-800 p-1" role="tablist" aria-label="Privacy rights by jurisdiction">
          {[
            { key: 'gdpr', label: 'GDPR (EU/EEA)' },
            { key: 'ccpa', label: 'CCPA (California)' },
            { key: 'pdpa', label: 'PDPA (Singapore)' },
          ].map((tab) => (
            <button
              key={tab.key}
              role="tab"
              aria-selected={rightsTab === tab.key}
              aria-controls={`tabpanel-${tab.key}`}
              id={`tab-${tab.key}`}
              onClick={() => setRightsTab(tab.key)}
              className={`flex-1 whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium transition ${
                rightsTab === tab.key
                  ? 'bg-slate-900 text-amber-400 shadow-sm'
                  : 'text-slate-400 hover:text-slate-300'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        {rightsTab === 'gdpr' && (
          <div className="space-y-3" role="tabpanel" id="tabpanel-gdpr" aria-labelledby="tab-gdpr">
            <Paragraph>
              If you are located in the European Economic Area, you have the following rights under the GDPR:
            </Paragraph>
            <BulletList items={[
              'Right of access \u2014 request a copy of the personal data we hold about you.',
              'Right to rectification \u2014 request correction of incomplete or inaccurate data.',
              'Right to erasure \u2014 request deletion of your personal data.',
              'Right to restrict processing \u2014 request that we limit how we use your data.',
              'Right to data portability \u2014 receive your data in a structured, machine-readable format.',
              'Right to object \u2014 object to processing based on legitimate interests or for direct marketing.',
              'Right to withdraw consent \u2014 withdraw consent at any time without affecting the lawfulness of prior processing.',
            ]} />
            <Paragraph>
              We will respond to all requests within 30 days. You also have the right to lodge
              a complaint with your local data protection authority.
            </Paragraph>
          </div>
        )}

        {rightsTab === 'ccpa' && (
          <div className="space-y-3" role="tabpanel" id="tabpanel-ccpa" aria-labelledby="tab-ccpa">
            <Paragraph>
              If you are a California resident, the CCPA provides you with specific rights:
            </Paragraph>
            <BulletList items={[
              'Right to know \u2014 request disclosure of what personal data we collect, use, and share.',
              'Right to delete \u2014 request deletion of your personal data.',
              'Right to opt-out of sale \u2014 we do not sell personal data, but if practices change, you can opt out.',
              'Right to non-discrimination \u2014 we will not discriminate against you for exercising your rights.',
            ]} />
            <Paragraph>
              We will verify your identity before processing requests and respond within 45 days.
            </Paragraph>
          </div>
        )}

        {rightsTab === 'pdpa' && (
          <div className="space-y-3" role="tabpanel" id="tabpanel-pdpa" aria-labelledby="tab-pdpa">
            <Paragraph>
              WarmPath is incorporated in Singapore and complies with the Personal Data Protection Act 2012:
            </Paragraph>
            <BulletList items={[
              'Consent \u2014 we collect, use, and disclose your personal data only with your consent or where PDPA exceptions apply.',
              'Purpose limitation \u2014 we use your data only for purposes a reasonable person would consider appropriate.',
              'Access and correction \u2014 you may request access to and correction of your personal data.',
              'Withdrawal of consent \u2014 you may withdraw consent at any time, subject to legal or contractual restrictions.',
              'Transfer limitation \u2014 overseas transfers meet the PDPA\u2019s requirements for adequate protection.',
              'Data breach notification \u2014 we will notify the PDPC and affected individuals of any notifiable data breach.',
            ]} />
          </div>
        )}

        <Paragraph>
          To exercise any of these rights, contact us at{' '}
          <a href="mailto:rovik@majiq.agency" className="font-medium text-amber-400 hover:text-amber-300">
            rovik@majiq.agency
          </a>.
        </Paragraph>
      </section>

      {/* 9. AI & Automated Processing */}
      <section className="space-y-4 rounded-xl bg-slate-900 p-6 border border-slate-700/50">
        <SectionHeading id="ai">
          <span className="mr-2 inline-flex h-7 w-7 items-center justify-center rounded-full bg-amber-500/10 text-sm text-amber-400">9</span>
          AI & Automated Processing
        </SectionHeading>
        <div className="space-y-3">
          <div>
            <h4 className="mb-1 font-semibold text-slate-200">Warm Score Computation</h4>
            <Paragraph>
              Our algorithm computes referral likelihood scores based on connection recency,
              relationship strength, role relevance, and company tenure. Scores are indicative
              recommendations, not deterministic outcomes. Processing is performed locally on our
              infrastructure &mdash; no data is sent to external AI providers.
            </Paragraph>
          </div>
          <div>
            <h4 className="mb-1 font-semibold text-slate-200">AI Coaching & Message Drafting</h4>
            <Paragraph>
              We use Anthropic Claude to power our AI coach (Keevs) and to draft personalised referral
              request messages. When you request an intro message, your contact&rsquo;s name and professional
              details are sent to Anthropic to generate a personalised draft. Anthropic does not retain
              data beyond the API call and does not train on API inputs. Generated messages are
              suggestions that you review, edit, and choose whether to send.
            </Paragraph>
          </div>
          <div>
            <h4 className="mb-1 font-semibold text-slate-200">CSV Data Normalisation</h4>
            <Paragraph>
              When you upload a LinkedIn CSV, we use AI (Groq and OpenAI) to normalise company names
              and job titles &mdash; for example, correcting &ldquo;GOOGLE LLC&rdquo; to
              &ldquo;Google&rdquo; or expanding &ldquo;sr. swe&rdquo; to &ldquo;Senior Software
              Engineer.&rdquo; Only company names and job titles are sent to these providers.
              Your contacts&rsquo; names and email addresses are never sent to any external AI
              provider &mdash; they are cleaned using deterministic rules on our own servers.
            </Paragraph>
          </div>
          <div>
            <h4 className="mb-1 font-semibold text-slate-200">Resume Parsing</h4>
            <Paragraph>
              If you upload a resume, we use Google Gemini to extract structured information (title,
              company, skills). This is your own data, sent at your request. Google does not retain
              API data beyond the processing call.
            </Paragraph>
          </div>
          <div>
            <h4 className="mb-1 font-semibold text-slate-200">Cultural Context Engine</h4>
            <Paragraph>
              Our system analyses location, company culture, and relationship type to recommend
              culturally appropriate communication approaches. This does not involve profiling
              individuals based on protected characteristics.
            </Paragraph>
          </div>
        </div>

        {/* AI Sub-Processors Table */}
        <div className="overflow-x-auto">
          <h4 className="mb-2 font-semibold text-slate-200">Our AI Providers</h4>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700/50 bg-slate-800 text-left">
                <th className="px-3 py-2 font-semibold text-slate-300">Provider</th>
                <th className="px-3 py-2 font-semibold text-slate-300">What It Does</th>
                <th className="px-3 py-2 font-semibold text-slate-300">Data Sent</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/50">
              {[
                ['Anthropic (Claude)', 'AI coaching, intro message drafting', 'Your profile, contact name + professional details (user-initiated only)'],
                ['Google (Gemini)', 'Resume parsing', 'Your resume text (your own data)'],
                ['Groq', 'Company & title normalisation', 'Company names and job titles only'],
                ['OpenAI', 'Company & title normalisation (fallback)', 'Company names and job titles only'],
              ].map(([provider, purpose, data], i) => (
                <tr key={i} className="hover:bg-slate-800">
                  <td className="px-3 py-2 font-medium text-slate-200">{provider}</td>
                  <td className="px-3 py-2 text-slate-400">{purpose}</td>
                  <td className="px-3 py-2 text-slate-400">{data}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="rounded-lg border border-sky-500/30 bg-sky-500/10 p-4">
          <p className="text-sm font-medium text-sky-400">
            Contact names and email addresses are never sent to any AI provider for bulk processing.
            Names are cleaned deterministically on our own servers. None of our AI providers retain
            or train on data submitted via their APIs.
          </p>
        </div>
        <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-4">
          <p className="text-sm font-medium text-emerald-400">
            WarmPath does not make automated decisions that produce legal effects or similarly
            significant effects concerning you. All AI outputs are advisory &mdash; you retain
            full control over all actions.
          </p>
        </div>
      </section>

      {/* 10. Data Retention */}
      <section className="space-y-4 rounded-xl bg-slate-900 p-6 border border-slate-700/50">
        <SectionHeading id="retention">
          <span className="mr-2 inline-flex h-7 w-7 items-center justify-center rounded-full bg-amber-500/10 text-sm text-amber-400">10</span>
          Data Retention
        </SectionHeading>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700/50 bg-slate-800 text-left">
                <th className="px-3 py-2 font-semibold text-slate-300">Data Type</th>
                <th className="px-3 py-2 font-semibold text-slate-300">Retention Period</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/50">
              {[
                ['Account data', 'While active. Deleted within 30 days of account deletion.'],
                ['Contact data (vault)', 'While active. Deleted on account deletion or contact removal.'],
                ['Marketplace listings', 'Removed immediately on withdrawal or account deletion.'],
                ['CSV upload files', 'Deleted immediately after processing.'],
                ['Credit transaction history', '24 months after account deletion (audit purposes).'],
                ['Usage data', 'Identifiable logs: 12 months max. Aggregated data: retained indefinitely.'],
                ['Suppression list entries', 'Indefinitely (by design, for ongoing protection).'],
              ].map(([type, period], i) => (
                <tr key={i} className="hover:bg-slate-800">
                  <td className="px-3 py-2 font-medium text-slate-200">{type}</td>
                  <td className="px-3 py-2 text-slate-400">{period}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* 11. Contact Us */}
      <section className="space-y-4 rounded-xl bg-slate-900 p-6 border border-slate-700/50">
        <SectionHeading id="contact">
          <span className="mr-2 inline-flex h-7 w-7 items-center justify-center rounded-full bg-amber-500/10 text-sm text-amber-400">11</span>
          Contact Us
        </SectionHeading>
        <div className="space-y-2">
          <div className="grid gap-3 sm:grid-cols-2">
            {[
              ['General privacy enquiries', 'privacy@warmpath.com'],
              ['Data Protection Officer', 'dpo@warmpath.com'],
              ['Suppression requests', 'privacy@warmpath.com'],
              ['Data Subject Access Requests', 'privacy@warmpath.com'],
            ].map(([label, email], i) => (
              <div key={i} className="rounded-lg border border-slate-700/50 p-3">
                <p className="text-xs font-medium text-slate-400">{label}</p>
                <p className="text-sm font-medium text-slate-50">{email}</p>
              </div>
            ))}
          </div>
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3">
            <p className="text-sm text-amber-400">
              During the beta period, all enquiries should be directed to{' '}
              <a href="mailto:rovik@majiq.agency" className="font-medium text-amber-300 hover:underline">
                rovik@majiq.agency
              </a>.
            </p>
          </div>
        </div>
        <p className="text-xs text-slate-400">
          Majiq Pte Ltd &middot; Registered in Singapore
        </p>
      </section>

      {/* Back to top */}
      <div className="text-center">
        <a href="#" className="text-sm text-amber-400 hover:text-amber-300" aria-label="Back to top of page">
          Back to top
        </a>
      </div>
    </main>
    </div>
  );
}
