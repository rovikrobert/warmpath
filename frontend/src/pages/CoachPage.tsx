import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { coach as coachApi } from '../api/client';
import ErrorBoundary from '../components/ErrorBoundary';
import FeedbackModal from '../components/FeedbackModal';
import KeevsAvatar from '../components/KeevsAvatar';
import TrebAvatar from '../components/TrebAvatar';
import ReferralJourney from '../components/ReferralJourney';
import CoachPageSkeleton from '../components/skeletons/CoachPageSkeleton';
import { useToast } from '../components/ui/Toast';
import useDocumentTitle from '../hooks/useDocumentTitle';

/**
 * Render text with markdown-style links [text](/path) as React Router <Link>s.
 * Also handles **bold** text.
 */
function renderWithLinks(text) {
  if (!text) return null;
  // Split on markdown links: [text](/path)
  const parts = text.split(/(\[[^\]]+\]\([^)]+\))/g);
  return parts.map((part, i) => {
    const linkMatch = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (linkMatch) {
      const [, label, href] = linkMatch;
      if (href.startsWith('/')) {
        return (
          <Link key={i} to={href} className="font-medium text-primary hover:text-primary underline">
            {label}
          </Link>
        );
      }
      return (
        <a key={i} href={href} className="font-medium text-primary hover:text-primary underline" target="_blank" rel="noopener noreferrer">
          {label}
        </a>
      );
    }
    // Handle **bold**
    const boldParts = part.split(/(\*\*[^*]+\*\*)/g);
    if (boldParts.length > 1) {
      return boldParts.map((bp, j) => {
        const boldMatch = bp.match(/^\*\*([^*]+)\*\*$/);
        if (boldMatch) return <strong key={`${i}-${j}`}>{boldMatch[1]}</strong>;
        return <span key={`${i}-${j}`}>{bp}</span>;
      });
    }
    return <span key={i}>{part}</span>;
  });
}

function chunkCoachLine(line) {
  const trimmed = line.trim();
  if (!trimmed) return [];
  if (/^(?:[-*]\s|\d+\.\s)/.test(trimmed)) return [trimmed];

  const sentences = trimmed.match(/[^.!?]+[.!?]+(?:\s|$)|[^.!?]+$/g);
  if (!sentences || sentences.length <= 2) return [trimmed];

  const chunks = [];
  for (let i = 0; i < sentences.length; i += 2) {
    chunks.push(sentences.slice(i, i + 2).join(' ').trim());
  }
  return chunks.filter(Boolean);
}

function chunkCoachMessage(text) {
  if (!text) return [];
  return text
    .split('\n')
    .flatMap((line) => chunkCoachLine(line))
    .filter(Boolean);
}

const KEEVS_QUICK_ACTIONS = [
  { label: 'Find referrals', prompt: 'Help me find referral paths at my target companies' },
  { label: 'Draft an intro', prompt: 'Help me draft a referral intro message' },
  { label: 'Review my network', prompt: 'Analyze my network and tell me my strongest connections' },
];

const TREB_QUICK_ACTIONS = [
  { label: 'Share my network', prompt: 'How do I share my network on WarmPath?' },
  { label: 'Check intro requests', prompt: 'Show me pending intro requests' },
  { label: 'Referral bonuses', prompt: 'How much are referral bonuses worth?' },
];

export default function CoachPage() {
  useDocumentTitle('Coach');
  const { user } = useAuth();
  const toast = useToast();
  const [messages, setMessages] = useState<any[]>([]);
  const [contextSnapshot, setContextSnapshot] = useState(null);
  const [suggestedPrompts, setSuggestedPrompts] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [showFeedback, setShowFeedback] = useState(false);
  const [persona, setPersona] = useState('keevs');
  const messagesEndRef = useRef(null);
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement>(null);
  const quickActionsRef = useRef(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, sending]);

  // Load briefing on mount
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const res = await coachApi.briefing();
        if (cancelled) return;
        const data = res.data;
        const p = data.persona || 'keevs';
        setPersona(p);
        setMessages([{ role: p, content: data.briefing }]);
        setContextSnapshot(data.context_snapshot);
        setSuggestedPrompts(data.suggested_prompts || []);
      } catch (err) {
        console.error('CoachPage: briefing load failed', err);
        if (cancelled) return;
        const firstName = user?.full_name?.split(' ')[0] || 'there';
        setMessages([{
          role: 'keevs',
          content: `Hey ${firstName}, I'm Keevs, your AI career coach. I had trouble loading your data — try refreshing. In the meantime, ask me anything about your job search.`,
        }]);
        setSuggestedPrompts(['How do I get started?', 'What should I focus on today?']);
      } finally {
        if (!cancelled) {
          setLoading(false);
          setTimeout(() => { if (!cancelled) setShowFeedback(true); }, 5000);
        }
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const sendMessage = async (text) => {
    if (!text.trim() || sending) return;

    const userMsg = { role: 'user', content: text.trim() };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setSuggestedPrompts([]);
    setSending(true);

    // Append an empty Keevs bubble that will fill progressively
    const keevsIdx = messages.length + 1; // index of the new keevs message
    setMessages((prev) => [...prev, { role: persona, content: '' }]);

    try {
      const history = [...messages, userMsg].map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const reader = await coachApi.chatStream({
        message: text.trim(),
        conversation_history: history,
        context_snapshot: contextSnapshot,
      });

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        // Parse SSE lines from buffer
        const lines = buffer.split('\n');
        buffer = lines.pop(); // keep incomplete line in buffer

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const payload = line.slice(6);
          if (payload === '[DONE]') continue;
          try {
            const parsed = JSON.parse(payload);
            // Handle persona event from SSE
            if (parsed.persona) {
              setPersona(parsed.persona);
              continue;
            }
            const { t } = parsed;
            if (t) {
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[keevsIdx];
                if (last && last.role !== 'user') {
                  updated[keevsIdx] = { ...last, content: last.content + t };
                }
                return updated;
              });
            }
          } catch (err) {
            console.error('CoachPage: failed to parse SSE line', err);
          }
        }
      }
    } catch (err) {
      console.error('CoachPage: stream failed', err);
      setMessages((prev) => {
        const updated = [...prev];
        const last = updated[keevsIdx];
        if (last && last.role !== 'user' && !last.content) {
          updated[keevsIdx] = { ...last, content: "Sorry, I couldn't process that. Try again in a moment." };
        }
        return updated;
      });
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  if (loading) {
    return <CoachPageSkeleton />;
  }

  return (
    <div className="flex h-[calc(100dvh-8rem)] lg:h-[calc(100vh-8rem)] flex-col" role="main">
      {/* Guided referral journey for new users */}
      <ReferralJourney variant="full" />

      {/* Header */}
      <div className="flex-none border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          {persona === 'treb' ? <TrebAvatar size={32} /> : <KeevsAvatar size={32} />}
          <div>
            <h1 className="page-title">{persona === 'treb' ? 'Treb' : 'Keevs'}</h1>
            <p className="text-xs text-muted-foreground">{persona === 'treb' ? 'Network Partner' : 'AI Career Coach'}</p>
          </div>
        </div>
      </div>

      {/* Quick Actions — only visible before user sends first message */}
      {messages.length <= 1 && (
        <div className="flex-none relative px-4 py-2">
          {/* Scroll-fade gradient to hint at horizontal overflow */}
          <div className="absolute right-4 top-0 bottom-0 w-8 bg-gradient-to-l from-background to-transparent pointer-events-none z-10" />
          <div
            ref={quickActionsRef}
            className="flex gap-2 overflow-x-auto scrollbar-none"
            role="toolbar"
            aria-label="Quick actions"
          >
            {suggestedPrompts.map((prompt) => (
              <button
                key={prompt}
                onClick={() => sendMessage(prompt)}
                disabled={sending}
                className="flex-shrink-0 rounded-full border border-primary/30 bg-primary/10 px-4 py-2 text-sm font-medium text-primary hover:bg-primary/20 transition-colors cursor-pointer whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {prompt}
              </button>
            ))}
            {(persona === 'treb' ? TREB_QUICK_ACTIONS : KEEVS_QUICK_ACTIONS).map((action) => (
              <button
                key={action.label}
                onClick={() => sendMessage(action.prompt)}
                disabled={sending}
                className="flex-shrink-0 bg-muted hover:bg-muted border border-border rounded-full px-4 py-2 text-sm text-secondary-foreground hover:text-foreground transition-colors cursor-pointer whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {action.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4" aria-live="polite" aria-label="Conversation messages">
        <ErrorBoundary>
        {messages.map((msg, i) => {
          const isBriefing = i === 0 && (msg.role === 'keevs' || msg.role === 'treb');
          return (
          <div
            key={i}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div>
              <div
                className={`rounded-2xl text-sm leading-relaxed ${
                  msg.role === 'user'
                    ? 'max-w-[95%] sm:max-w-[85%] px-4 py-3 bg-primary text-white'
                    : isBriefing
                      ? 'max-w-[98%] sm:max-w-[90%] px-5 py-4 border-l-2 border-primary/30 bg-muted text-foreground'
                      : 'max-w-[95%] sm:max-w-[85%] px-4 py-3 bg-muted text-foreground'
                }`}
              >
                {(msg.role === 'keevs' || msg.role === 'treb')
                  ? chunkCoachMessage(msg.content).map((line, j) => (
                      <p key={j} className={j > 0 ? 'mt-2' : ''}>
                        {renderWithLinks(line)}
                      </p>
                    ))
                  : msg.content
                }
              </div>
              {(msg.role === 'keevs' || msg.role === 'treb') && msg.content && (
                <button
                  onClick={() => navigator.clipboard.writeText(msg.content).then(() => toast.success('Copied to clipboard'))}
                  className="mt-1 text-xs text-muted-foreground hover:text-muted-foreground transition-colors"
                  aria-label="Copy message"
                >
                  Copy
                </button>
              )}
            </div>
          </div>
          );
        })}
        </ErrorBoundary>

        {/* Typing indicator */}
        {sending && (
          <div className="flex items-center gap-2 px-4 py-3">
            <div className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-primary animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="h-2 w-2 rounded-full bg-primary animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="h-2 w-2 rounded-full bg-primary animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
            <span className="text-xs text-muted-foreground">{persona === 'treb' ? 'Treb' : 'Keevs'} is thinking...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="flex-none border-t border-border bg-background px-4 py-3">
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={persona === "treb" ? "Ask Treb about sharing your network..." : "Ask Keevs anything about your job search..."}
            aria-label={`Message to ${persona === "treb" ? "Treb" : "Keevs"}`}
            disabled={sending}
            rows={1}
            className="flex-1 resize-none rounded-xl border border-border bg-muted px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50"
          />
          <button
            onClick={() => sendMessage(input)}
            disabled={!input.trim() || sending}
            aria-label="Send message"
            className="rounded-xl bg-primary px-4 py-2.5 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Send
          </button>
        </div>
      </div>

      {showFeedback && (
        <FeedbackModal
          feature="coach_briefing"
          onClose={() => setShowFeedback(false)}
        />
      )}
    </div>
  );
}
