import type { Metadata } from "next";

export const metadata: Metadata = { title: "Solicitudes" };

// F0: solo el encabezado del mockup `solicitudes.html`. El listado lo construye F1.
export default function SolicitudesPage() {
  return (
    <div>
      <h1 className="m-0 text-3xl font-semibold tracking-tight">Solicitudes</h1>
      <p className="text-text-secondary mt-0.5 mb-0">
        Créditos de vivienda asignados a ti, desde el borrador hasta el desembolso.
      </p>
    </div>
  );
}
