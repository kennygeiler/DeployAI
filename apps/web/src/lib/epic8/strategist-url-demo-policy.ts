/** Gate URL-driven meeting overlays (`?inMeeting=1`) in production builds (Lane M — PS-M-*). */
export function shouldAllowStrategistMeetingUrlDemo(): boolean {
  if (process.env.NODE_ENV !== "production") {
    return true;
  }
  return process.env.NEXT_PUBLIC_DEPLOYAI_STRATEGIST_MEETING_URL_DEMO === "1";
}
