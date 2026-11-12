"use client";

import { darkTheme, lightTheme } from "@design/antd-theme";
import type { Tone } from "@design/status-tones";
import {
  Alert,
  Button,
  Checkbox,
  ConfigProvider,
  Input,
  InputNumber,
  Progress,
  Select,
  Space,
  Table,
} from "antd";
import { useMutation } from "@tanstack/react-query";
import Link from "next/link";

import { TONE_CLASS } from "@/components/ui/status-badge";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { ApiError, networkError } from "@/lib/api/errors";
import { useToast } from "@/providers/toast";

type Mode = "light" | "dark";

const TONES: Tone[] = ["neutral", "info", "accent", "success", "warning", "danger"];

const SURFACES = [
  { name: "bg-canvas", className: "bg-bg-canvas" },
  { name: "bg-surface", className: "bg-bg-surface" },
  { name: "bg-subtle", className: "bg-bg-subtle" },
  { name: "bg-muted", className: "bg-bg-muted" },
  { name: "bg-sidebar", className: "bg-bg-sidebar" },
  { name: "brand-primary", className: "bg-brand-primary" },
  { name: "brand-subtle", className: "bg-brand-subtle" },
  { name: "accent-default", className: "bg-accent-default" },
];

// Datos de muestra genéricos: esta página no muestra datos de negocio.
const SAMPLE_OPTIONS = [
  { value: "a", label: "Opción A" },
  { value: "b", label: "Opción B" },
];
const SAMPLE_ROWS = [
  { key: "1", code: "COD-000001", name: "Fila de ejemplo uno", amount: 294000000 },
  { key: "2", code: "COD-000002", name: "Fila de ejemplo dos", amount: 180500000 },
];

const cop = new Intl.NumberFormat("es-CO", {
  style: "currency",
  currency: "COP",
  maximumFractionDigits: 0,
});

function Section({ mode }: { mode: Mode }) {
  const label = mode === "light" ? "Tema claro" : "Tema oscuro";
  return (
    <ConfigProvider theme={mode === "light" ? lightTheme : darkTheme}>
      <section
        data-theme={mode}
        aria-label={label}
        className="bg-bg-canvas text-text-primary grid content-start gap-6 p-6"
      >
        <h2 className="m-0 text-xl font-semibold">{label}</h2>

        <div className="grid gap-2">
          <h3 className="text-text-secondary m-0 text-xs font-medium">Superficies y marca</h3>
          <div className="flex flex-wrap gap-2">
            {SURFACES.map((s) => (
              <div key={s.name} className="grid w-24 gap-1">
                <div className={`border-border-default h-10 rounded-md border ${s.className}`} />
                <span className="text-text-tertiary font-mono text-xs">{s.name}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="grid gap-1">
          <h3 className="text-text-secondary m-0 text-xs font-medium">Texto</h3>
          <p className="m-0">Texto principal sobre el fondo de la página.</p>
          <p className="text-text-secondary m-0">Texto secundario.</p>
          <p className="text-text-tertiary m-0 text-sm">Texto terciario.</p>
          <p className="m-0">
            <a className="text-text-link underline" href="#enlace">
              Enlace
            </a>{" "}
            · <span className="font-mono text-sm">COD-000184</span> ·{" "}
            <span className="tabular-nums">{cop.format(294000000)}</span>
          </p>
        </div>

        <div className="grid gap-2">
          <h3 className="text-text-secondary m-0 text-xs font-medium">Tonos de estado</h3>
          <div className="flex flex-wrap gap-2">
            {TONES.map((tone) => (
              <span
                key={tone}
                className={`inline-flex h-[22px] items-center gap-1.5 rounded-full border px-2 text-xs font-medium whitespace-nowrap ${TONE_CLASS[tone]}`}
              >
                <span aria-hidden="true" className="size-1.5 rounded-full bg-current" />
                {tone}
              </span>
            ))}
          </div>
        </div>

        <div className="grid gap-2">
          <h3 className="text-text-secondary m-0 text-xs font-medium">Botones</h3>
          <Space wrap>
            <Button type="primary">Primario</Button>
            <Button>Por defecto</Button>
            <Button type="text">Texto</Button>
            <Button danger>Peligro</Button>
            <Button disabled>Deshabilitado</Button>
          </Space>
        </div>

        <div className="grid max-w-md gap-3">
          <h3 className="text-text-secondary m-0 text-xs font-medium">Campos</h3>
          <Input placeholder="Campo de texto" aria-label={`Campo de texto (${label})`} />
          <Input.Password placeholder="Contraseña" aria-label={`Contraseña (${label})`} />
          <InputNumber<number>
            className="w-full"
            prefix="COP"
            defaultValue={294000000}
            formatter={(v) => (v == null ? "" : new Intl.NumberFormat("es-CO").format(Number(v)))}
            parser={(v) => Number((v ?? "").replace(/\D/g, ""))}
            aria-label={`Monto (${label})`}
          />
          <Select
            placeholder="Selecciona una opción"
            options={SAMPLE_OPTIONS}
            aria-label={`Selector (${label})`}
          />
          <Checkbox>Casilla</Checkbox>
        </div>

        <div className="grid max-w-xl gap-2">
          <h3 className="text-text-secondary m-0 text-xs font-medium">Alertas y progreso</h3>
          <Alert type="warning" showIcon title="Faltan datos para evaluar una regla" />
          <Alert type="error" showIcon title="Una regla bloqueante no se cumple" />
          <Progress percent={62} aria-label={`Progreso de ejemplo (${label})`} />
        </div>

        <div className="grid gap-2">
          <h3 className="text-text-secondary m-0 text-xs font-medium">Tabla</h3>
          <Table
            size="middle"
            pagination={false}
            dataSource={SAMPLE_ROWS}
            columns={[
              {
                title: "Código",
                dataIndex: "code",
                render: (v: string) => (
                  <span className="text-text-link font-mono text-sm">{v}</span>
                ),
              },
              { title: "Nombre", dataIndex: "name" },
              {
                title: "Monto",
                dataIndex: "amount",
                align: "right",
                render: (v: number) => <span className="tabular-nums">{cop.format(v)}</span>,
              },
            ]}
          />
        </div>
      </section>
    </ConfigProvider>
  );
}

/** Barra con el tema global, los toasts y el enlace a la demo del shell. */
// Errores de ejemplo para ver el manejador global de escrituras (sin llamar a la API).
const SAMPLE_ERRORS = {
  generic: () =>
    new ApiError(
      422,
      "APPLICATION_NOT_READY",
      "La solicitud todavía no cumple los requisitos.",
      [{ field: "documents", code: "DOCUMENT_PENDING", message: "Falta 1 documento obligatorio." }],
      "d1f98a64-bf42-4b93-a952-754eb5cb98a2",
    ),
  stale: () =>
    new ApiError(
      409,
      "STALE_VERSION",
      "La versión cambió.",
      [],
      "a2c4e6f8-0000-4000-8000-000000000001",
    ),
  network: () => networkError(),
};

function Toolbar() {
  const toast = useToast();
  const failing = useMutation({
    mutationFn: (kind: keyof typeof SAMPLE_ERRORS) => Promise.reject(SAMPLE_ERRORS[kind]()),
  });
  return (
    <header className="bg-bg-surface border-border-default text-text-primary flex flex-wrap items-center gap-2 border-b px-6 py-3">
      <h1 className="m-0 mr-auto text-lg font-semibold">Componentes del design system</h1>
      <Space wrap>
        <Button
          onClick={() =>
            toast.success({
              title: "Cambios guardados",
              message: "El aviso se cierra solo en 5 s.",
            })
          }
        >
          Toast de éxito
        </Button>
        <Button onClick={() => toast.info({ title: "Información", message: "Se cierra en 5 s." })}>
          Toast de información
        </Button>
        <Button onClick={() => toast.warning({ title: "Advertencia" })}>
          Toast de advertencia
        </Button>
        <Button
          danger
          onClick={() =>
            toast.error({
              title: "No pudimos guardar",
              message: "Este aviso se queda hasta cerrarlo.",
              action: { label: "Reintentar", onClick: () => toast.info({ title: "Reintentando" }) },
            })
          }
        >
          Toast de error
        </Button>
        <Button onClick={() => failing.mutate("generic")}>Escritura fallida</Button>
        <Button onClick={() => failing.mutate("stale")}>Versión obsoleta</Button>
        <Button onClick={() => failing.mutate("network")}>Sin conexión</Button>
        <Link href="/dev/ui/shell" className="text-text-link px-2 text-sm">
          Ver el shell
        </Link>
        <ThemeToggle />
      </Space>
    </header>
  );
}

export function UiPreview() {
  return (
    <div className="min-h-screen">
      <Toolbar />
      <main className="grid grid-cols-1 xl:grid-cols-2">
        <Section mode="light" />
        <Section mode="dark" />
      </main>
    </div>
  );
}
