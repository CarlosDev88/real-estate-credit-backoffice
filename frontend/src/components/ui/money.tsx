"use client";

import { InputNumber, type InputNumberProps } from "antd";

import { formatCOP, formatInteger, parseInteger } from "@/lib/format";

/** Monto COP entero, con cifras tabulares. Sin valor muestra "—" (o `empty`). */
export function Money({
  value,
  empty = "—",
  className = "",
}: {
  value: number | null | undefined;
  empty?: string;
  className?: string;
}) {
  const text = formatCOP(value);
  return text ? (
    <span className={`whitespace-nowrap tabular-nums ${className}`}>{text}</span>
  ) : (
    <span className={`text-text-tertiary ${className}`}>{empty}</span>
  );
}

type MoneyInputProps = Omit<
  InputNumberProps<number>,
  "value" | "onChange" | "formatter" | "parser" | "precision" | "min" | "prefix"
> & {
  value?: number | null;
  onChange?: (value: number | null) => void;
};

/**
 * Campo de monto COP: entero, sin negativos, con separador de miles, prefijo "COP"
 * y alineado a la derecha (design/README.md, componentes base).
 */
export function MoneyInput({ value, onChange, className = "", ...rest }: MoneyInputProps) {
  return (
    <InputNumber<number>
      {...rest}
      value={value ?? null}
      onChange={(v) => onChange?.(v ?? null)}
      prefix="COP"
      min={0}
      precision={0}
      controls={false}
      inputMode="numeric"
      formatter={(v) => formatInteger(v === undefined || v === null ? null : Number(v))}
      parser={(text) => parseInteger(text) ?? 0}
      className={`w-full tabular-nums [&_input]:text-right ${className}`}
    />
  );
}
