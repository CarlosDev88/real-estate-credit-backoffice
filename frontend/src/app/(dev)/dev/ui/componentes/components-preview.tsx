"use client";

import { Button } from "antd";
import Link from "next/link";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";

import { CompletenessBar } from "@/components/ui/completeness-bar";
import { DocumentUploader, type UploadContext } from "@/components/ui/document-uploader";
import { DocumentViewer, type ViewerFile } from "@/components/ui/document-viewer";
import { EmptyState } from "@/components/ui/empty-state";
import { FilterChips } from "@/components/ui/filter-chips";
import { Money, MoneyInput } from "@/components/ui/money";
import { RelativeTime } from "@/components/ui/relative-time";
import { ScrollTabs } from "@/components/ui/scroll-tabs";
import { StatusBadge } from "@/components/ui/status-badge";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { useToast } from "@/providers/toast";

// Todo lo de esta página es de muestra: no llama a la API ni muestra datos de negocio.

/** PDF mínimo de 2 páginas armado en el navegador (PDF.js reconstruye la tabla xref). */
function samplePdfUrl(): string {
  const page = (n: number) =>
    `BT /F1 28 Tf 72 700 Td (Documento de muestra) Tj 0 -40 Td /F1 16 Tf (Pagina ${n} de 2) Tj ET`;
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R 5 0 R] /Count 2 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 7 0 R >> >> >>",
    `<< /Length ${page(1).length} >>\nstream\n${page(1)}\nendstream`,
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 6 0 R /Resources << /Font << /F1 7 0 R >> >> >>",
    `<< /Length ${page(2).length} >>\nstream\n${page(2)}\nendstream`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
  ];
  let body = "%PDF-1.4\n";
  const offsets: number[] = [];
  objects.forEach((obj, i) => {
    offsets.push(body.length);
    body += `${i + 1} 0 obj\n${obj}\nendobj\n`;
  });
  const xref = body.length;
  body += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  body += offsets.map((o) => `${String(o).padStart(10, "0")} 00000 n \n`).join("");
  body += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
  return URL.createObjectURL(new Blob([body], { type: "application/pdf" }));
}

function sampleImageUrl(): string {
  const canvas = document.createElement("canvas");
  canvas.width = 800;
  canvas.height = 500;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    ctx.fillStyle = "#e9edf1";
    ctx.fillRect(0, 0, 800, 500);
    ctx.fillStyle = "#1f4e91";
    ctx.font = "bold 40px sans-serif";
    ctx.fillText("Imagen de muestra", 60, 260);
  }
  return canvas.toDataURL("image/png");
}

/** Carga simulada: avanza el progreso y se puede cancelar. */
function fakeUpload(_file: File, { onProgress, signal }: UploadContext): Promise<void> {
  return new Promise((resolve, reject) => {
    let pct = 0;
    const timer = setInterval(() => {
      pct = Math.min(100, pct + 10);
      onProgress(pct);
      if (pct === 100) {
        clearInterval(timer);
        setTimeout(resolve, 600);
      }
    }, 150);
    signal.addEventListener("abort", () => {
      clearInterval(timer);
      reject(new DOMException("Cancelado", "AbortError"));
    });
  });
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="bg-bg-surface border-border-default grid gap-3 rounded-lg border p-4">
      <h2 className="text-text-secondary m-0 text-xs font-medium">{title}</h2>
      {children}
    </section>
  );
}

const TABS = Array.from({ length: 9 }, (_, i) => ({
  key: `t${i}`,
  label: `Pestaña de muestra ${i + 1}`,
  count: (i * 7) % 23,
}));

export function ComponentsPreview() {
  const toast = useToast();
  const [tab, setTab] = useState("t0");
  const [amount, setAmount] = useState<number | null>(294000000);
  const [chips, setChips] = useState([
    { key: "a", label: "Filtro A", value: "valor de muestra" },
    { key: "b", label: "Filtro B", value: "otro valor" },
  ]);
  const [viewer, setViewer] = useState<ViewerFile | null>(null);
  const [samples, setSamples] = useState<{ pdf: string; image: string } | null>(null);
  const [times, setTimes] = useState<string[]>([]);

  useEffect(() => {
    // Solo en el cliente: blobs y fechas relativas a "ahora".
    const now = Date.now();
    /* eslint-disable react-hooks/set-state-in-effect -- datos de muestra que solo existen en el navegador */
    setSamples({ pdf: samplePdfUrl(), image: sampleImageUrl() });
    setTimes(
      [0.2, 12, 65, 60 * 30, 60 * 60, 60 * 24 * 5].map((m) =>
        new Date(now - m * 60_000).toISOString(),
      ),
    );
    /* eslint-enable react-hooks/set-state-in-effect */
  }, []);

  return (
    <div className="bg-bg-canvas text-text-primary min-h-screen">
      <header className="bg-bg-surface border-border-default flex items-center gap-3 border-b px-6 py-3">
        <h1 className="m-0 mr-auto text-lg font-semibold">Componentes compartidos</h1>
        <Link href="/dev/ui" className="text-text-link text-sm">
          Design system
        </Link>
        <ThemeToggle />
      </header>

      <main className="grid max-w-5xl gap-4 p-6">
        <Section title="StatusBadge (el color sale del código; el texto, de la API)">
          <div className="flex flex-wrap gap-2">
            {[
              "DRAFT",
              "WAITING_DOCUMENTS",
              "DOCUMENTS_REVIEW",
              "READY_TO_FILE",
              "APPROVED",
              "REJECTED",
              "CÓDIGO_NUEVO",
            ].map((code) => (
              <StatusBadge key={code} kind="application" code={code} label={code} />
            ))}
          </div>
        </Section>

        <Section title="Money y MoneyInput">
          <p className="m-0">
            <Money value={amount} /> · <Money value={null} />
          </p>
          <div className="max-w-xs">
            <MoneyInput aria-label="Monto de muestra" value={amount} onChange={setAmount} />
          </div>
        </Section>

        <Section title="CompletenessBar">
          <div className="max-w-md">
            <CompletenessBar
              percentage={81}
              dataPercentage={100}
              documentsPercentage={62}
              documentsCompleted={10}
              documentsRequired={16}
            />
          </div>
          <CompletenessBar variant="mini" percentage={54} />
        </Section>

        <Section title="ScrollTabs (flechas, desvanecido y teclado)">
          <div className="max-w-xl">
            <ScrollTabs
              ariaLabel="Pestañas de muestra"
              items={TABS}
              value={tab}
              onChange={setTab}
            />
          </div>
          <p className="text-text-tertiary m-0 text-sm">Elegida: {tab}</p>
        </Section>

        <Section title="FilterChips">
          <FilterChips
            chips={chips}
            caption='Desde "Más filtros":'
            onRemove={(key) => setChips((c) => c.filter((x) => x.key !== key))}
            onClearAll={() => setChips([])}
          />
          {chips.length === 0 && (
            <p className="text-text-tertiary m-0 text-sm">Sin filtros activos.</p>
          )}
        </Section>

        <Section title="EmptyState">
          <EmptyState
            title="No hay resultados con estos filtros"
            description="Prueba con otro estado o limpia los filtros."
            action={
              <Button onClick={() => toast.info({ title: "Filtros limpios" })}>
                Limpiar filtros
              </Button>
            }
          />
        </Section>

        <Section title="RelativeTime (se actualiza cada minuto)">
          <ul className="m-0 grid gap-1 pl-5">
            {times.map((t) => (
              <li key={t}>
                <RelativeTime value={t} />
              </li>
            ))}
          </ul>
        </Section>

        <Section title="DocumentViewer">
          <div className="flex flex-wrap gap-2">
            <Button
              disabled={!samples}
              onClick={() =>
                samples &&
                setViewer({
                  name: "documento-de-muestra.pdf",
                  kind: "pdf",
                  url: samples.pdf,
                  size: "1 KB",
                })
              }
            >
              Ver PDF de muestra
            </Button>
            <Button
              disabled={!samples}
              onClick={() =>
                samples &&
                setViewer({ name: "imagen-de-muestra.png", kind: "image", url: samples.image })
              }
            >
              Ver imagen de muestra
            </Button>
          </div>
          <DocumentViewer
            open={!!viewer}
            file={viewer}
            onClose={() => setViewer(null)}
            note="Archivo generado en el navegador para la demo."
          />
        </Section>

        <Section title="DocumentUploader (carga simulada)">
          <div className="max-w-lg">
            <DocumentUploader
              accept={["application/pdf", "image/jpeg", "image/png"]}
              maxBytes={10 * 1024 * 1024}
              onUpload={async (file, ctx) => {
                await fakeUpload(file, ctx);
                toast.success({ title: "Documento recibido", message: file.name });
              }}
            />
          </div>
        </Section>
      </main>
    </div>
  );
}
