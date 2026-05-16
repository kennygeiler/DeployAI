import { NextResponse } from "next/server";

export type StrategistBffCpErrorJson = {
  error: string;
  code: string;
  source: "cp_error";
  userMessage: string;
  detail?: string;
};

const DEGRADED_USER_MESSAGE =
  "This request could not be completed. Nothing was saved. The service may be temporarily unreachable—try again shortly, or contact support if this continues.";

const NOT_FOUND_USER_MESSAGE =
  "That queue item was not found or is no longer available.";

export function nextResponseFromStrategistCpFetchError(err: unknown): NextResponse {
  const message = err instanceof Error ? err.message : String(err);
  const parsed = message.match(/^cp .+ (\d{3}):\s*(.*)$/s);
  const upstreamStatus = parsed?.[1] != null ? Number.parseInt(parsed[1], 10) : NaN;
  const tail = parsed?.[2]?.trim() ?? "";
  const detail = tail.length > 0 ? tail.slice(0, 500) : undefined;

  const json = (body: Omit<StrategistBffCpErrorJson, "source">, httpStatus: number) =>
    NextResponse.json({ ...body, source: "cp_error" } satisfies StrategistBffCpErrorJson, {
      status: httpStatus,
    });

  if (upstreamStatus === 404) {
    return json({ error: "not_found", code: "cp_not_found", userMessage: NOT_FOUND_USER_MESSAGE, detail }, 404);
  }
  if (upstreamStatus === 400 || upstreamStatus === 422) {
    return json(
      {
        error: "bad_request",
        code: "cp_rejected",
        userMessage: "This update could not be applied. Refresh the page and try again.",
        detail,
      },
      400,
    );
  }
  if (!Number.isNaN(upstreamStatus) && upstreamStatus >= 400 && upstreamStatus < 500) {
    return json(
      {
        error: "upstream_client_error",
        code: "cp_4xx",
        userMessage: DEGRADED_USER_MESSAGE,
        detail,
      },
      502,
    );
  }
  if (!Number.isNaN(upstreamStatus) && upstreamStatus >= 500) {
    return json(
      { error: "upstream_server_error", code: "cp_5xx", userMessage: DEGRADED_USER_MESSAGE, detail },
      502,
    );
  }
  return json(
    {
      error: "upstream_unreachable",
      code: "cp_unreachable",
      userMessage: DEGRADED_USER_MESSAGE,
      detail: message.slice(0, 500) || undefined,
    },
    502,
  );
}
