import { describe, expect, it } from "vitest";

import {
  auditTypeForInMeetingAction,
  isNonLearningInMeetingAction,
} from "./in-meeting-alert-actions";

describe("in-meeting-alert-actions (FR37)", () => {
  it("maps correct to alert.corrected", () => {
    expect(auditTypeForInMeetingAction("correct")).toBe("alert.corrected");
    expect(isNonLearningInMeetingAction("correct")).toBe(false);
  });

  it("maps dismiss to alert.dismissed (non-learning)", () => {
    expect(auditTypeForInMeetingAction("dismiss")).toBe("alert.dismissed");
    expect(isNonLearningInMeetingAction("dismiss")).toBe(true);
  });

  it("protocol: 100 samples stay consistent", () => {
    for (let i = 0; i < 100; i++) {
      expect(auditTypeForInMeetingAction("correct")).toBe("alert.corrected");
      expect(auditTypeForInMeetingAction("dismiss")).toBe("alert.dismissed");
      expect(isNonLearningInMeetingAction("dismiss")).toBe(true);
      expect(isNonLearningInMeetingAction("correct")).toBe(false);
    }
  });
});
