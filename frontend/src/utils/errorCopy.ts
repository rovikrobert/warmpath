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

export function isCreditInsufficientError(err: any): boolean {
  const status = err?.status;
  const msg = String(err?.message || "").toLowerCase();
  return (
    status === 402
    || msg.includes("insufficient credits")
    || msg.includes("need 5 credits")
    || msg.includes("need 20 credits")
  );
}

export function getCreditInsufficientMessage(err: any, fallback: string): string {
  if (isCreditInsufficientError(err)) {
    return "You don't have enough credits for this action yet.";
  }
  return fallback;
}
