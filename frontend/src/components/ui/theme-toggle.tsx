"use client";

import { Button } from "antd";

import { MoonIcon, SunIcon } from "@/components/ui/icons";
import { useTheme } from "@/providers/theme-provider";

/** Botón de tema: muestra el ícono del tema al que se cambia (luna en claro, sol en oscuro). */
export function ThemeToggle({ className }: { className?: string }) {
  const { mode, toggle } = useTheme();
  const label = mode === "dark" ? "Cambiar a tema claro" : "Cambiar a tema oscuro";
  return (
    <Button
      type="text"
      className={className}
      icon={mode === "dark" ? <SunIcon /> : <MoonIcon />}
      aria-label={label}
      title={label}
      onClick={toggle}
    />
  );
}
