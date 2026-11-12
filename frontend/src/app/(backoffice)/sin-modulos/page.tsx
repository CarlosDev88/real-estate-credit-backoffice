import type { Metadata } from "next";

export const metadata: Metadata = { title: "Sin módulos" };

export default function SinModulosPage() {
  return (
    <div className="max-w-xl">
      <h1 className="m-0 text-3xl font-semibold tracking-tight">Sin módulos habilitados</h1>
      <p className="text-text-secondary mt-2 mb-0">
        Tu usuario todavía no tiene módulos habilitados. Pídele acceso a un administrador.
      </p>
    </div>
  );
}
