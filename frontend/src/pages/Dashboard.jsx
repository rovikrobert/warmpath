import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { coach as coachApi } from '../api/client';

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
          <Link key={i} to={href} className="font-medium text-amber-600 hover:text-amber-700 underline">
            {label}
          </Link>
        );
      }
      return (
        <a key={i} href={href} className="font-medium text-amber-600 hover:text-amber-700 underline" target="_blank" rel="noopener noreferrer">
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

export default function Dashboard() {
  const { user } = useAuth();
  const [messages, setMessages] = useState([]);
  const [contextSnapshot, setContextSnapshot] = useState(null);
  const [suggestedPrompts, setSuggestedPrompts] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

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
        if (!cancelled) setLoading(false);
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

    try {
      // Build conversation history for the API (exclude the current message)
      const history = [...messages, userMsg].map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const res = await coachApi.chat({
        message: text.trim(),
        conversation_history: history,
        context_snapshot: contextSnapshot,
      });

      setMessages((prev) => [...prev, { role: 'keevs', content: res.data.response }]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: 'keevs', content: "Sorry, I couldn't process that. Try again in a moment." },
      ]);
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
      <div className="flex h-[calc(100vh-8rem)] items-center justify-center">
        <div className="text-center">
          <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-4 border-amber-500 border-t-transparent" />
          <p className="text-sm text-slate-500">Keevs is preparing your briefing...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col">
      {/* Header */}
      <div className="flex-none border-b border-slate-200 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-amber-500 text-sm font-bold text-white">~</span>
          <div>
            <h1 className="text-base font-semibold text-slate-900">Keevs</h1>
            <p className="text-xs text-slate-500">AI Career Coach</p>
          </div>
        </div>
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                msg.role === 'user'
                  ? 'bg-amber-500 text-white'
                  : 'bg-slate-100 text-slate-800'
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
                className="rounded-full border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700 hover:bg-amber-100 transition-colors"
              >
                {prompt}
              </button>
            ))}
          </div>
        )}

        {/* Typing indicator */}
        {sending && (
          <div className="flex justify-start">
            <div className="rounded-2xl bg-slate-100 px-4 py-3">
              <p className="animate-pulse text-sm text-slate-500">Keevs is thinking...</p>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="flex-none border-t border-slate-200 bg-white px-4 py-3">
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask Keevs anything about your job search..."
            disabled={sending}
            rows={1}
            className="flex-1 resize-none rounded-xl border border-slate-300 px-4 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500 disabled:opacity-50"
          />
          <button
            onClick={() => sendMessage(input)}
            disabled={!input.trim() || sending}
            className="rounded-xl bg-amber-500 px-4 py-2.5 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
