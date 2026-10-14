"use client";

import { Input, Label } from "@/components/ui/input";
import type { JsonSchemaProp } from "@/lib/types";

type Props = {
  schema: Record<string, JsonSchemaProp>;
  values: Record<string, unknown>;
  onChange: (values: Record<string, unknown>) => void;
};

/** Renders a form straight from a strategy's Pydantic JSON schema. */
export function ParamForm({ schema, values, onChange }: Props) {
  const set = (key: string, v: unknown) => onChange({ ...values, [key]: v });
  return (
    <div className="grid grid-cols-2 gap-3">
      {Object.entries(schema).map(([key, prop]) => {
        const value = values[key] ?? prop.default;
        const label = prop.title ?? key;
        if (prop.type === "boolean") {
          return (
            <label key={key} className="col-span-2 flex items-center gap-2 text-sm" title={prop.description}>
              <input type="checkbox" checked={!!value} onChange={(e) => set(key, e.target.checked)} />
              {label}
            </label>
          );
        }
        const min = prop.minimum ?? prop.exclusiveMinimum;
        const max = prop.maximum ?? prop.exclusiveMaximum;
        return (
          <div key={key} title={prop.description}>
            <Label>{label}</Label>
            <Input
              type="number"
              className="num"
              step={prop.type === "integer" ? 1 : "any"}
              min={min}
              max={max}
              value={value as number}
              onChange={(e) => set(key, prop.type === "integer" ? parseInt(e.target.value, 10) : parseFloat(e.target.value))}
            />
          </div>
        );
      })}
    </div>
  );
}
