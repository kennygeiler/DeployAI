import { useId, useState } from "react";

export type TwoPartyConsentDialogProps = {
  open: boolean;
  onAccept: (jurisdiction: string) => void;
  onDecline: () => void;
};

const JURIS_OPTIONS = [
  {
    value: "US-default",
    label: "United States — I am responsible for two-party consent rules in my state",
  },
  {
    value: "other",
    label: "Other jurisdiction — I have verified local recording consent requirements",
  },
] as const;

export function TwoPartyConsentDialog({ open, onAccept, onDecline }: TwoPartyConsentDialogProps) {
  const titleId = useId();
  const [jurisdiction, setJurisdiction] = useState<string>(JURIS_OPTIONS[0].value);
  const [confirmed, setConfirmed] = useState(false);

  if (!open) {
    return null;
  }

  return (
    <div className="consent-backdrop" role="dialog" aria-modal="true" aria-labelledby={titleId}>
      <div className="consent-sheet panel">
        <h2 id={titleId}>Recording consent</h2>
        <p className="consent-lead">
          DeployAI captures audio only after you confirm compliance with applicable consent laws
          (including two-party consent where required). This is a legal attestation — not legal
          advice.
        </p>
        <label className="consent-select-label">
          Jurisdiction
          <select
            className="consent-select"
            value={jurisdiction}
            onChange={(e) => setJurisdiction(e.target.value)}
            aria-label="Jurisdiction preset for consent attestation"
          >
            {JURIS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="consent-check">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
          />
          <span>
            I confirm all recorded parties have consented as required where this device is used.
          </span>
        </label>
        <div className="consent-actions">
          <button type="button" onClick={onDecline}>
            Decline
          </button>
          <button type="button" disabled={!confirmed} onClick={() => onAccept(jurisdiction)}>
            Accept and continue
          </button>
        </div>
      </div>
    </div>
  );
}
