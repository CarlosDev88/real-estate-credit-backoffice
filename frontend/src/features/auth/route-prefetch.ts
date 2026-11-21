import type { QueryClient } from "@tanstack/react-query";

import {
  applicationDetailQuery,
  participantsQuery,
  propertyQuery,
} from "@/features/applications/workspace-queries";
import { DOSSIER } from "@/features/auth/route-paths";

/**
 * Lo que una ruta necesita para su primera pintura, pedido a la vez que `/auth/me` (PERF-01):
 * la guarda no monta la página hasta tener la sesión, y sin esto esas consultas salían un
 * viaje de red después. Las mismas claves que usa la página, que las encuentra en curso o
 * resueltas. Solo lee: los permisos los aplica la API; si la ruta está prohibida, la guarda
 * redirige igual.
 */
export function prefetchRoute(client: QueryClient, pathname: string): void {
  const dossier = DOSSIER.exec(pathname);
  if (dossier) {
    const id = dossier[1]!;
    // El título y el subtítulo del expediente (su LCP) salen de estas tres.
    void client.prefetchQuery(applicationDetailQuery(id));
    void client.prefetchQuery(participantsQuery(id));
    void client.prefetchQuery(propertyQuery(id));
  }
}
