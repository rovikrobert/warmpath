import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { coach as coachApi, feed as feedApi } from '../api/client';
import FeedbackModal from '../components/FeedbackModal';
import FeedCard from '../components/FeedCard';
import KeevsAvatar from '../components/KeevsAvatar';
import OnboardingChecklist from '../components/OnboardingChecklist';
import Spinner from '../components/ui/Spinner';

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
          <Link key={i} to={href} className="font-medium text-amber-400 hover:text-amber-300 underline">
            {label}
          </Link>
        );
      }
      return (
        <a key={i} href={href} className="font-medium text-amber-400 hover:text-amber-300 underline" target="_blank" rel="noopener noreferrer">
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

export default function CoachPage() {
  const { user } = useAuth();
  const [messages, setMessages] = useState([]);
  const [contextSnapshot, setContextSnapshot] = useState(null);
  const [suggestedPrompts, setSuggestedPrompts] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [showFeedback, setShowFeedback] = useState(false);
  const [feedItems, setFeedItems] = useState([]);
  const [feedExpanded, setFeedExpanded] = useState(true);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, sending]);

  // Load feed items on mount
  useEffect(() => {
    let cancelled = false;
    feedApi.list({ limit: 5 })
      .then((res) => { if (!cancelled) setFeedItems(res.data || []); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  // Load briefing on mount
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const res = await coachApi.briefing();
        if (cancelled) return;
        const data = res.data;
        setMessages([{ role: 'keevs', content: data.briefing }]);
        setContextSnapshot(data.context_snapshot);
        setSuggestedPrompts(data.suggested_prompts || []);
      } catch {
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
    setMessages((prev) => [...prev, { role: 'keevs', content: '' }]);

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
            const { t } = JSON.parse(payload);
            if (t) {
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[keevsIdx];
                if (last && last.role === 'keevs') {
                  updated[keevsIdx] = { ...last, content: last.content + t };
                }
                return updated;
              });
            }
          } catch {
            // skip malformed SSE lines
          }
        }
      }
    } catch {
      setMessages((prev) => {
        const updated = [...prev];
        const last = updated[keevsIdx];
        if (last && last.role === 'keevs' && !last.content) {
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
    return (
      <div className="flex h-[calc(100vh-8rem)] items-center justify-center" role="main" aria-live="polite" aria-busy="true">
        <div className="text-center">
          <Spinner size="lg" className="mx-auto mb-3" />
          <p className="text-sm text-slate-400">Keevs is preparing your briefing...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col" role="main">
      {/* Onboarding checklist for new users */}
      <OnboardingChecklist />

      {/* Feed section */}
      {feedItems.length > 0 && (
        <div className="flex-none border-b border-slate-700/50">
          <button
            type="button"
            onClick={() => setFeedExpanded(!feedExpanded)}
            className="flex w-full items-center justify-between px-4 py-2.5 text-left"
          >
            <div className="flex items-center gap-2">
              <KeevsAvatar size="sm" />
              <span className="text-sm font-medium text-amber-400">
                {feedItems.filter((f) => !f.seen_at).length > 0
                  ? `${feedItems.filter((f) => !f.seen_at).length} new insights`
                  : 'Recent insights'}
              </span>
            </div>
            <svg className={`h-4 w-4 text-slate-500 transition-transform ${feedExpanded ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
            </svg>
          </button>
          {feedExpanded && (
            <div className="space-y-2 px-4 pb-3">
              {feedItems.map((item) => (
                <FeedCard
                  key={item.id}
                  item={item}
                  onDismiss={(id) => setFeedItems((prev) => prev.filter((f) => f.id !== id))}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Header */}
      <div className="flex-none border-b border-slate-700/50 px-4 py-3">
        <div className="flex items-center gap-2">
          <KeevsAvatar size={32} />
          <div>
            <h1 className="text-base font-semibold text-slate-50">Keevs</h1>
            <p className="text-xs text-slate-400">AI Career Coach</p>
          </div>
        </div>
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4" aria-live="polite" aria-label="Conversation messages">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[95%] rounded-2xl px-4 py-3 text-sm leading-relaxed sm:max-w-[85%] ${
                msg.role === 'user'
                  ? 'bg-amber-500 text-white'
                  : 'bg-slate-800 text-slate-200'
              }`}
            >
              {msg.role === 'keevs'
                ? msg.content.split('\n').map((line, j) => (
                    <p key={j} className={j > 0 ? 'mt-2' : ''}>
                      {renderWithLinks(line)}
                    </p>
                  ))
                : msg.content
              }
            </div>
          </div>
        ))}

        {/* Suggested prompts */}
        {suggestedPrompts.length > 0 && !sending && (
          <div className="flex flex-wrap gap-2">
            {suggestedPrompts.map((prompt) => (
              <button
                key={prompt}
                onClick={() => sendMessage(prompt)}
                className="rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs font-medium text-amber-400 hover:bg-amber-500/20 transition-colors"
              >
                {prompt}
              </button>
            ))}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="flex-none border-t border-slate-700/50 bg-slate-950 px-4 py-3">
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask Keevs anything about your job search..."
            aria-label="Message to Keevs"
            disabled={sending}
            rows={1}
            className="flex-1 resize-none rounded-xl border border-slate-700/50 bg-slate-800 px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500 disabled:opacity-50"
          />
          <button
            onClick={() => sendMessage(input)}
            disabled={!input.trim() || sending}
            aria-label="Send message"
            className="rounded-xl bg-amber-500 px-4 py-2.5 text-sm font-medium text-white hover:bg-amber-400 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
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
