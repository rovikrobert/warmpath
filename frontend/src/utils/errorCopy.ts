export function getRateLimitMessage(err: any, fallback: string): string {
  const status = err?.status;
  const msg = String(err?.message || "");
  if (status !== 429 && !msg.toLowerCase().includes("limit")) {
    return fallback;
  }

  const lower = msg.toLowerCase();
  if (lower.includes("intro request")) {
    return "You've reached today's intro request limit. Try again tomorrow or narrow your list to your highest-priority targets.";
  }
  if (lower.includes("intro approval")) {
    return "You've reached today's intro approval limit. Please try again tomorrow.";
  }
  if (lower.includes("manual intro confirmation")) {
    return "You've reached today's manual confirmation limit. Please try again tomorrow.";
  }
  if (lower.includes("search")) {
    return "You've reached today's search limit. Please try again tomorrow.";
  }
  if (lower.includes("credit purchase")) {
    return "Credit purchases are temporarily limited for today. Please try again tomorrow.";
  }

  return "You've hit a daily limit for this action. Please try again tomorrow.";
}
