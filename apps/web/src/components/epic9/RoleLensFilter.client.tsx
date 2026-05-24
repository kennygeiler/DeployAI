"use client";

import * as React from "react";

import { isRoleLens, ROLE_LENS_VALUES, type RoleLens } from "@/lib/matrix/role-lens";

const BUILTIN_LABEL: Record<string, string> = {
  all: "All roles",
  fde: "Forward-deployed engineer",
  deployment_strategist: "Deployment strategist",
  biz_dev: "Business development",
};

export type CustomRoleOption = {
  name: string;
  label: string;
};

export function RoleLensFilter({
  value,
  onChange,
  customRoles,
}: {
  value: RoleLens;
  onChange: (next: RoleLens) => void;
  customRoles?: readonly CustomRoleOption[];
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
        onChange={(e) => {
          const next = e.target.value;
          if (isRoleLens(next)) {
            onChange(next);
          }
        }}
        aria-label="Role lens"
      >
        {ROLE_LENS_VALUES.map((r) => (
          <option key={r} value={r}>
            {BUILTIN_LABEL[r]}
          </option>
        ))}
        {customRoles?.map((r) => (
          <option key={r.name} value={r.name}>
            {r.label}
          </option>
        ))}
      </select>
    </div>
  );
}
