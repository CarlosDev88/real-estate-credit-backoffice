// Íconos de los mockups (design/screens/src). Decorativos: el texto accesible va en el control.
import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

const base = { viewBox: "0 0 20 20", "aria-hidden": true, focusable: false } as const;

export function MenuIcon(props: IconProps) {
  return (
    <svg {...base} fill="currentColor" width={16} height={16} {...props}>
      <path d="M3 5h14v2H3V5Zm0 4h14v2H3V9Zm0 4h14v2H3v-2Z" />
    </svg>
  );
}

export function CloseIcon(props: IconProps) {
  return (
    <svg {...base} fill="currentColor" width={16} height={16} {...props}>
      <path d="m5.4 4 4.6 4.6L14.6 4 16 5.4 11.4 10l4.6 4.6-1.4 1.4-4.6-4.6L5.4 16 4 14.6 8.6 10 4 5.4 5.4 4Z" />
    </svg>
  );
}

export function SunIcon(props: IconProps) {
  return (
    <svg
      {...base}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      width={16}
      height={16}
      {...props}
    >
      <circle cx="10" cy="10" r="3.4" fill="currentColor" stroke="none" />
      <path d="M10 1.5v2M10 16.5v2M1.5 10h2M16.5 10h2M4 4l1.4 1.4M14.6 14.6 16 16M4 16l1.4-1.4M14.6 5.4 16 4" />
    </svg>
  );
}

export function MoonIcon(props: IconProps) {
  return (
    <svg {...base} fill="currentColor" width={16} height={16} {...props}>
      <path d="M15.5 12.8A6.5 6.5 0 0 1 7.2 4.5a7 7 0 1 0 8.3 8.3Z" />
    </svg>
  );
}

export function HouseIcon(props: IconProps) {
  return (
    <svg {...base} fill="currentColor" width={16} height={16} {...props}>
      <path d="M10 2 2 8v10h5v-6h6v6h5V8l-8-6Z" />
    </svg>
  );
}

export function MailIcon(props: IconProps) {
  return (
    <svg {...base} fill="currentColor" width={16} height={16} {...props}>
      <path d="M2 4h16v12H2V4Zm2 2v.5l6 4 6-4V6H4Zm12 2.9-6 4-6-4V14h12V8.9Z" />
    </svg>
  );
}

export function LockIcon(props: IconProps) {
  return (
    <svg {...base} fill="currentColor" width={16} height={16} {...props}>
      <path d="M6 8V6a4 4 0 1 1 8 0v2h1a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1h1Zm2 0h4V6a2 2 0 1 0-4 0v2Zm1 3v3h2v-3H9Z" />
    </svg>
  );
}

export function EyeIcon(props: IconProps) {
  return (
    <svg {...base} fill="currentColor" width={16} height={16} {...props}>
      <path d="M10 4C5 4 1.7 8.1 1 10c.7 1.9 4 6 9 6s8.3-4.1 9-6c-.7-1.9-4-6-9-6Zm0 10a4 4 0 1 1 0-8 4 4 0 0 1 0 8Zm0-2a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z" />
    </svg>
  );
}

/** Marca de Umbral: el arco de la puerta sobre el umbral. */
export function LogoMark({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <rect width="32" height="32" rx="7" fill="#ffffff1f" />
      <path
        d="M10 25V15a6 6 0 0 1 12 0v10"
        fill="none"
        stroke="#fff"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
      <path
        d="M7 25.5h18"
        stroke="var(--um-color-teal-300)"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
    </svg>
  );
}
