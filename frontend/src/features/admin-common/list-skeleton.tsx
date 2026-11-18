/** Cargando un listado: filas grises con la forma de la tabla. */
export function ListSkeleton({ label, rows = 6 }: { label: string; rows?: number }) {
  return (
    <div role="status" aria-label={label} className="grid">
      {Array.from({ length: rows }, (_, i) => (
        <div
          key={i}
          className="border-border-default flex h-11 items-center gap-4 border-b px-3 last:border-b-0"
        >
          <span className="bg-bg-muted h-3 w-40 animate-pulse rounded-full motion-reduce:animate-none" />
          <span className="bg-bg-muted h-3 w-24 animate-pulse rounded-full motion-reduce:animate-none" />
          <span className="bg-bg-muted h-3 flex-1 animate-pulse rounded-full motion-reduce:animate-none" />
          <span className="bg-bg-muted h-3 w-20 animate-pulse rounded-full motion-reduce:animate-none" />
        </div>
      ))}
    </div>
  );
}
