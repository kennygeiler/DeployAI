export async function readStrategistBffErrorDescription(res: Response): Promise<string> {
  const text = await res.text();
  try {
    const j = JSON.parse(text) as { userMessage?: unknown; error?: unknown };
    if (typeof j.userMessage === "string" && j.userMessage.trim()) {
      return j.userMessage;
    }
    if (typeof j.error === "string" && j.error.trim()) {
      return j.error.slice(0, 500);
    }
  } catch {
    // not JSON
  }
  const t = text.trim();
  return t.length > 0 ? t.slice(0, 500) : `Request failed (${res.status})`;
}
