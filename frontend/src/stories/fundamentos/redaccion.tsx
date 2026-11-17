// Ejemplos vivos de las reglas de redacción (design/README.md). Los formatos salen de
// lib/format, así que si cambian, los ejemplos cambian con ellos.

import { Button } from "antd";

import { StatusBadge } from "@/components/ui/status-badge";
import { formatCOP, formatDateTime, formatPercent } from "@/lib/format";

import { DoDont } from "./blocks";

// Fecha fija: el ejemplo no cambia con el día en que se abre Storybook.
const SAMPLE_DATE = "2026-08-24T20:45:00Z";

export function SentenceCaseExample() {
  return (
    <DoDont
      good={
        <div className="flex flex-wrap gap-2">
          <Button type="primary">Marcar lista para radicar</Button>
          <Button>Revisar 3 documentos</Button>
        </div>
      }
      goodNote="Títulos, botones, pestañas y mensajes en sentence case: solo la primera letra en mayúscula (y los nombres propios)."
      bad={
        <div className="flex flex-wrap gap-2">
          <Button type="primary">Marcar Lista Para Radicar</Button>
          <Button>REVISAR DOCUMENTOS</Button>
        </div>
      }
      badNote="Mayúscula en cada palabra o todo en mayúsculas: se lee peor y parece un grito."
    />
  );
}

export function LabelExample() {
  return (
    <DoDont
      good={
        <dl className="m-0 grid grid-cols-2 gap-3">
          <div>
            <dt className="text-text-secondary text-xs font-medium">monto solicitado</dt>
            <dd className="m-0 text-lg font-semibold tabular-nums">{formatCOP(294_000_000)}</dd>
          </div>
          <div>
            <dt className="text-text-secondary text-xs font-medium">completitud</dt>
            <dd className="m-0 text-lg font-semibold tabular-nums">{formatPercent(62)}</dd>
          </div>
        </dl>
      }
      goodNote="Encabezados de tabla, etiquetas de KPI y grupos del menú: minúscula inicial, text.xs (12 px), peso medio, text.secondary."
      bad={
        <dl className="m-0 grid grid-cols-2 gap-3">
          <div>
            <dt className="text-text-secondary text-xs font-medium tracking-widest uppercase">
              Monto solicitado
            </dt>
            <dd className="m-0 text-lg font-semibold">294000000</dd>
          </div>
          <div>
            <dt className="text-text-secondary text-xs font-medium tracking-widest uppercase">
              Completitud
            </dt>
            <dd className="m-0 text-lg font-semibold">62%</dd>
          </div>
        </dl>
      }
      badNote="Mayúsculas espaciadas, cifras sin formato ni cifras tabulares, porcentaje pegado al número."
    />
  );
}

export function LinkExample() {
  return (
    <DoDont
      good={
        <p className="m-0 text-sm">
          Si el comprador no recibió el correo, puedes{" "}
          <a href="#reenviar" className="text-text-link underline">
            reenviar el enlace de acceso
          </a>{" "}
          desde la ficha.
        </p>
      }
      goodNote="Un enlace dentro de un texto va subrayado siempre, no solo al pasar el mouse. Los del menú, las migas y los botones de texto no lo necesitan."
      bad={
        <p className="m-0 text-sm">
          Si el comprador no recibió el correo, puedes{" "}
          <a href="#reenviar" className="text-text-link no-underline">
            reenviar el enlace de acceso
          </a>{" "}
          desde la ficha.
        </p>
      }
      badNote="Solo el color lo distingue del texto que lo rodea (WCAG 1.4.1)."
    />
  );
}

export function DataFormatExample() {
  return (
    <DoDont
      good={
        <ul className="m-0 flex list-none flex-col gap-1 p-0 text-sm">
          <li>
            <span className="font-mono">SOL-000184</span> · creada el {formatDateTime(SAMPLE_DATE)}
          </li>
          <li className="tabular-nums">Monto: {formatCOP(294_000_000)}</li>
          <li>
            Estado:{" "}
            <StatusBadge kind="application" code="READY_TO_FILE" label="Lista para radicar" />
          </li>
        </ul>
      }
      goodNote="Códigos en mono, montos en COP con es-CO y cifras tabulares, fechas en 12 h y el estado con la etiqueta de la API."
      bad={
        <ul className="m-0 flex list-none flex-col gap-1 p-0 text-sm">
          <li>SOL-000184 · creada el 2026-08-24 20:45</li>
          <li>Monto: $294000000.00</li>
          <li>Estado: READY_TO_FILE</li>
        </ul>
      }
      badNote="Fecha ISO, monto sin separadores y con decimales, y el código del estado en vez de su etiqueta."
    />
  );
}

export function PrimaryActionExample() {
  return (
    <DoDont
      good={
        <div className="flex flex-col items-start gap-2">
          <div className="flex flex-wrap gap-2">
            <Button type="primary">Revisar 3 documentos</Button>
            <Button disabled aria-describedby="razon-bloqueo">
              Marcar lista para radicar
            </Button>
          </div>
          <p id="razon-bloqueo" className="text-text-secondary m-0 text-sm">
            Faltan 3 documentos por revisar.
          </p>
        </div>
      }
      goodNote="Una acción principal por vista, y que se pueda ejecutar. Si la natural está bloqueada, queda deshabilitada con la razón visible."
      bad={
        <div className="flex flex-wrap gap-2">
          <Button type="primary">Guardar</Button>
          <Button type="primary">Enviar</Button>
          <Button type="primary" disabled>
            Marcar lista para radicar
          </Button>
        </div>
      }
      badNote="Varios primarios compiten y el bloqueado no dice por qué."
    />
  );
}

export function DestructiveExample() {
  return (
    <DoDont
      good={
        <div className="flex flex-col items-start gap-2">
          <Button type="primary">Subir documentos</Button>
          <Button type="link" className="text-text-secondary px-0">
            Ya no quiero continuar
          </Button>
        </div>
      }
      goodNote="Lo destructivo no se destaca: va en text.secondary. danger solo en el botón que confirma (rechazar, revocar)."
      bad={
        <div className="flex flex-col items-start gap-2">
          <Button type="primary">Subir documentos</Button>
          <Button danger type="primary">
            Ya no quiero continuar
          </Button>
        </div>
      }
      badNote="La salida compite con la acción principal y empuja a tocarla por error."
    />
  );
}
