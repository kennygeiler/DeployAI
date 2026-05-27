/**
 * Liveness probe for cloud deploys (Fly health checks, k8s probes, etc.).
 * Deliberately not behind the strategist middleware: returns 200 immediately
 * as long as the Node server is up, so an orchestrator never confuses a
 * 403-auth-gate response with a dead app.
 */
export const dynamic = "force-static";

export function GET() {
  return new Response("ok", {
    status: 200,
    headers: { "content-type": "text/plain" },
  });
}
