import type { ComponentPropsWithRef, ReactNode } from "react";
import { FieldError } from "./primitives";
type FieldProps = {
  id: string;
  label: string;
  help?: ReactNode;
  error?: string;
};
export function TextAreaField({
  id,
  label,
  error,
  inputProps = {},
}: FieldProps & { inputProps?: ComponentPropsWithRef<"textarea"> }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <textarea
        {...inputProps}
        id={id}
        rows={3}
        aria-invalid={!!error}
        aria-describedby={error ? `${id}-error` : undefined}
      />
      <FieldError id={`${id}-error`}>{error}</FieldError>
    </div>
  );
}
export function TextField({
  id,
  label,
  help,
  error,
  inputProps = {},
}: FieldProps & { inputProps?: ComponentPropsWithRef<"input"> }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        {...inputProps}
        id={id}
        aria-invalid={!!error}
        aria-describedby={
          [help ? `${id}-help` : null, error ? `${id}-error` : null]
            .filter(Boolean)
            .join(" ") || undefined
        }
      />
      {help && <small id={`${id}-help`}>{help}</small>}
      <FieldError id={`${id}-error`}>{error}</FieldError>
    </div>
  );
}
export function SelectField({
  id,
  label,
  help,
  error,
  options,
  selectProps = {},
}: FieldProps & {
  options: ReadonlyArray<{ value: string; label: string }>;
  selectProps?: ComponentPropsWithRef<"select">;
}) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select
        {...selectProps}
        id={id}
        aria-invalid={!!error}
        aria-describedby={
          [help ? `${id}-help` : null, error ? `${id}-error` : null]
            .filter(Boolean)
            .join(" ") || undefined
        }
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {help && <small id={`${id}-help`}>{help}</small>}
      <FieldError id={`${id}-error`}>{error}</FieldError>
    </div>
  );
}
