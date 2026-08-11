"use client";

/**
 * W1 — root fallback when the root layout itself throws. Must render its
 * own <html>/<body>; globals.css may not be applied at this point, so all
 * styling is inline with the Beautiful UI light-theme values hardcoded
 * (this is the only place in the app allowed to carry literal colors —
 * the token pipeline cannot be assumed alive here).
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#fafafb",
          color: "#1f2124",
          fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif",
        }}
      >
        <div
          style={{
            maxWidth: 420,
            width: "100%",
            margin: "0 16px",
            padding: 24,
            borderRadius: 10,
            background: "#ffffff",
            boxShadow:
              "0 0 0 1px #ecedef, 0 1px 2px rgba(16,24,40,0.04), 0 2px 6px rgba(16,24,40,0.03)",
            textAlign: "center",
          }}
        >
          <p style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>Something went wrong</p>
          <p style={{ margin: "8px 0 0", fontSize: 14, color: "#4b4e55" }}>
            The application hit an unrecoverable error. Reload to continue.
          </p>
          {error.digest ? (
            <p
              style={{ margin: "8px 0 0", fontSize: 11, color: "#6a6d74", fontFamily: "monospace" }}
            >
              ref {error.digest}
            </p>
          ) : null}
          {/* eslint-disable-next-line no-restricted-syntax -- global-error
              renders without the app shell or compiled CSS, so the shared
              <Button> primitive (Tailwind class-based) cannot be used here;
              this is the one sanctioned raw <button> (inline-styled). */}
          <button
            type="button"
            onClick={() => reset()}
            style={{
              marginTop: 16,
              height: 36,
              padding: "0 16px",
              borderRadius: 9999,
              border: "none",
              background: "#1f2124",
              color: "#ffffff",
              fontSize: 14,
              fontWeight: 500,
              cursor: "pointer",
              boxShadow: "0 0 0 1px #e0e2e5, 0 1px 2px rgba(16,24,40,0.05)",
            }}
          >
            Reload
          </button>
        </div>
      </body>
    </html>
  );
}
