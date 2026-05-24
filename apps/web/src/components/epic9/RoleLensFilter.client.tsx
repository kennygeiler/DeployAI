"use client";

import * as React from "react";

import { ROLE_LENS_VALUES, type RoleLens } from "@/lib/matrix/role-lens";

const LABEL: Record<RoleLens, string> = {
  all: "All roles",
  fde: "Forward-deployed engineer",
  deployment_strategist: "Deployment strategist",
  biz_dev: "Business development",
};

export function RoleLensFilter({
  value,
  onChange,
}: {
  value: RoleLens;
  onChange: (next: RoleLens) => void;
}) {
  const id = React.useId();
  return (
    <div className="flex items-center gap-2">
      <label className="text-ink-600 text-xs" htmlFor={id}>
        Role lens
      </label>
      <select
        id={id}
        className="border-border rounded-md border px-2 py-1 text-xs"
        value={value}
        onChange={(e) => onChange(e.target.value as RoleLens)}
        aria-label="Role lens"
      >
        {ROLE_LENS_VALUES.map((r) => (
          <option key={r} value={r}>
            {LABEL[r]}
          </option>
        ))}
      </select>
    </div>
  );
}
