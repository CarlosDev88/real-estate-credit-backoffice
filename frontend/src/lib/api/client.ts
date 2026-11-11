import createClient from "openapi-fetch";

import { toApiError } from "@/lib/api/errors";
import { apiFetch } from "@/lib/api/fetch";
import type { paths } from "@/lib/api/schema";
import { versionOf } from "@/lib/api/version";

/**
 * Cliente tipado desde `contracts/openapi.json`. Mismo origen: Next.js reescribe
 * `/api/v1/*` hacia la API, así que el navegador nunca habla con otro origen.
 */
export const api = createClient<paths>({
  baseUrl: typeof window === "undefined" ? "" : window.location.origin,
  fetch: apiFetch,
});

export interface ApiResult<T> {
  data: T;
  /** Versión del expediente (`ETag`), si la respuesta la trae; también en los `204`. */
  version: number | null;
  response: Response;
}

/**
 * Desenvuelve una llamada de `api`: devuelve `{ data, version }` o lanza `ApiError`.
 *
 * ```ts
 * const { data, version } = await call(api.GET("/api/v1/auth/me"));
 * ```
 */
export async function call<T>(
  request: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<ApiResult<T>> {
  const { data, error, response } = await request;
  if (!response.ok) throw toApiError(response, error);
  return { data: data as T, version: versionOf(response), response };
}
