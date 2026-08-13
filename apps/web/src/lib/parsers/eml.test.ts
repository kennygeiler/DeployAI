import { describe, expect, it } from "vitest";

import { emlToText } from "./eml";

describe("emlToText", () => {
  it("keeps Subject/From/Date as a prefix and strips the rest of the headers", () => {
    const raw = [
      "Return-Path: <dana@acme.com>",
      "Received: from mx.example (mx.example [10.0.0.1])",
      "\tby in.example with SMTP id abc123",
      "From: Dana <dana@acme.com>",
      "To: team@deploy.example",
      "Subject: Kickoff",
      "Date: Tue, 11 Aug 2026 09:00:00 +0000",
      "Content-Type: text/plain; charset=utf-8",
      "",
      "We agreed to start with the pilot cell.",
      "",
      "Second paragraph.",
    ].join("\n");
    expect(emlToText(raw)).toBe(
      [
        "Subject: Kickoff",
        "From: Dana <dana@acme.com>",
        "Date: Tue, 11 Aug 2026 09:00:00 +0000",
        "",
        "We agreed to start with the pilot cell.",
        "",
        "Second paragraph.",
      ].join("\n"),
    );
  });

  it("folds header continuation lines into the kept header", () => {
    const raw = ["Subject: A very", " long subject line", "", "body"].join("\n");
    expect(emlToText(raw)).toBe("Subject: A very long subject line\n\nbody");
  });

  it("returns the file untouched when it has no header block", () => {
    const raw = "Just some notes.\n\nWith a blank line.";
    expect(emlToText(raw)).toBe(raw);
  });

  it("handles CRLF and a headers-only file", () => {
    const raw = "Subject: Ping\r\nFrom: a@b\r\n\r\n";
    expect(emlToText(raw)).toBe("Subject: Ping\nFrom: a@b");
  });
});
