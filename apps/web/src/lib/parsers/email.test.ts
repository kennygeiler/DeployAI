import { describe, expect, it } from "vitest";

import { parseEmail } from "./email";

describe("parseEmail", () => {
  it("extracts From / To / Subject / Date headers and the body", () => {
    const raw =
      "From: Dana Carter <dana@acme.gov>\n" +
      "To: Priya Raman <priya@acme.gov>\n" +
      "Subject: Pilot scope\n" +
      "Date: Mon, 23 Mar 2026 14:00:00 -0700\n" +
      "\n" +
      "Priya,\n\nLooks good. Confirming the 90-day scope.\n\nDana";
    const { parsed, headerCount } = parseEmail(raw);
    expect(headerCount).toBe(4);
    expect(parsed.from).toBe("Dana Carter <dana@acme.gov>");
    expect(parsed.to).toBe("Priya Raman <priya@acme.gov>");
    expect(parsed.subject).toBe("Pilot scope");
    expect(parsed.date).toContain("23 Mar 2026");
    expect(parsed.occurred_at).toBeDefined();
    expect(parsed.text.startsWith("Priya,")).toBe(true);
    expect(parsed.text).toContain("90-day scope");
  });

  it("treats a header-less paste as plain body text", () => {
    const raw = "Just some notes I jotted down.\nNothing structured here.";
    const { parsed, headerCount } = parseEmail(raw);
    expect(headerCount).toBe(0);
    expect(parsed.text).toBe(raw);
    expect(parsed.from).toBeUndefined();
  });

  it("handles header continuation lines (indent continues previous header)", () => {
    const raw =
      "From: Sam Lee <sam@deployai.com>\n" +
      "Subject: A very long subject that\n" +
      " happens to wrap across two lines\n" +
      "\n" +
      "body here";
    const { parsed } = parseEmail(raw);
    expect(parsed.subject).toBe("A very long subject that happens to wrap across two lines");
    expect(parsed.text).toBe("body here");
  });

  it("ignores unknown headers but stays in the header block until a blank line", () => {
    const raw =
      "X-Some-Header: ignore me\n" + "From: a@x.com\n" + "Subject: hi\n" + "\n" + "the body";
    const { parsed, headerCount } = parseEmail(raw);
    expect(headerCount).toBe(2);
    expect(parsed.from).toBe("a@x.com");
    expect(parsed.subject).toBe("hi");
    expect(parsed.text).toBe("the body");
  });

  it("populates occurred_at from a parseable Date header", () => {
    const raw = "Date: 2026-05-09T15:00:00Z\nFrom: x@y\nSubject: t\n\nb";
    const { parsed } = parseEmail(raw);
    expect(parsed.occurred_at).toBe("2026-05-09T15:00:00.000Z");
  });

  it("leaves occurred_at undefined when Date header is garbage", () => {
    const raw = "Date: not a date\nFrom: x@y\nSubject: t\n\nb";
    const { parsed } = parseEmail(raw);
    expect(parsed.date).toBe("not a date");
    expect(parsed.occurred_at).toBeUndefined();
  });

  it("strips BOM and tolerates CRLF line endings", () => {
    const raw = "﻿From: a@b\r\nSubject: x\r\n\r\nhello";
    const { parsed, headerCount } = parseEmail(raw);
    expect(headerCount).toBe(2);
    expect(parsed.subject).toBe("x");
    expect(parsed.text).toBe("hello");
  });
});
