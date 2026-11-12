import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { api, call } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { ifMatch } from "@/lib/api/version";
import { apiUrl, server } from "@/test/msw-server";

describe("call", () => {
  it("devuelve { data, version } con la versión del ETag", async () => {
    server.use(
      http.get(apiUrl("/auth/me"), () =>
        HttpResponse.json({ id: "u-1", name: "Ana" }, { headers: { ETag: '"3"' } }),
      ),
    );
    const result = await call(api.GET("/api/v1/auth/me"));
    expect(result.data).toMatchObject({ id: "u-1", name: "Ana" });
    expect(result.version).toBe(3);
  });

  it("envía If-Match y toma la versión nueva del ETag de un 204", async () => {
    let sentIfMatch: string | null = null;
    server.use(
      http.put(apiUrl("/applications/a-1/property"), ({ request }) => {
        sentIfMatch = request.headers.get("If-Match");
        return new HttpResponse(null, { status: 204, headers: { ETag: '"8"' } });
      }),
    );

    const result = await call(
      api.PUT("/api/v1/applications/{application_id}/property", {
        params: { path: { application_id: "a-1" }, header: { "If-Match": ifMatch(7) } },
        body: {} as never,
      }),
    );

    expect(sentIfMatch).toBe('"7"');
    expect(result.version).toBe(8);
  });

  it("lanza ApiError con el formato de la API", async () => {
    server.use(
      http.patch(apiUrl("/applications/a-1"), () =>
        HttpResponse.json(
          {
            code: "STALE_VERSION",
            message: "La versión cambió.",
            details: [{ field: null, code: "STALE_VERSION", message: "x", current_version: 9 }],
            request_id: "req-9",
          },
          { status: 409 },
        ),
      ),
    );

    const error = await call(
      api.PATCH("/api/v1/applications/{application_id}", {
        params: { path: { application_id: "a-1" }, header: { "If-Match": ifMatch(7) } },
        body: {},
      }),
    ).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 409, code: "STALE_VERSION", requestId: "req-9" });
    expect((error as ApiError).details[0]?.current_version).toBe(9);
  });
});
