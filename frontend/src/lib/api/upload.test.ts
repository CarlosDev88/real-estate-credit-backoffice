import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/errors";
import {
  setAuthFailureHandler,
  setBuyerSessionExpiredHandler,
  setConsentRequiredHandler,
} from "@/lib/api/session";
import { uploadFile } from "@/lib/api/upload";
import { apiUrl, server } from "@/test/msw-server";

interface Reply {
  status: number;
  body?: unknown;
  headers?: Record<string, string>;
  progress?: [number, number][];
  fail?: boolean;
}

/** XMLHttpRequest falso: responde en orden lo que dice `replies` y guarda lo enviado. */
class FakeXHR {
  static replies: Reply[] = [];
  static sent: { url: string; headers: Record<string, string>; body: FormData }[] = [];

  url = "";
  status = 0;
  responseText = "";
  private headers: Record<string, string> = {};
  private responseHeaders: Record<string, string> = {};
  upload: {
    onprogress: ((e: { lengthComputable: boolean; loaded: number; total: number }) => void) | null;
  } = {
    onprogress: null,
  };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;
  private aborted = false;

  open(_method: string, url: string) {
    this.url = url;
  }
  setRequestHeader(name: string, value: string) {
    this.headers[name] = value;
  }
  getAllResponseHeaders() {
    return Object.entries(this.responseHeaders)
      .map(([k, v]) => `${k}: ${v}`)
      .join("\r\n");
  }
  abort() {
    this.aborted = true;
    this.onabort?.();
  }
  send(body: FormData) {
    FakeXHR.sent.push({ url: this.url, headers: { ...this.headers }, body });
    const reply = FakeXHR.replies.shift();
    queueMicrotask(() => {
      if (this.aborted || !reply) return;
      if (reply.fail) return this.onerror?.();
      for (const [loaded, total] of reply.progress ?? []) {
        this.upload.onprogress?.({ lengthComputable: true, loaded, total });
      }
      this.status = reply.status;
      this.responseText = reply.body === undefined ? "" : JSON.stringify(reply.body);
      this.responseHeaders = reply.headers ?? {};
      this.onload?.();
    });
  }
}

const file = new File(["%PDF-1.4"], "extracto.pdf", { type: "application/pdf" });
const err = (code: string) => ({ code, message: code, details: [], request_id: "req-1" });

beforeEach(() => {
  FakeXHR.replies = [];
  FakeXHR.sent = [];
  vi.stubGlobal("XMLHttpRequest", FakeXHR);
  setAuthFailureHandler(vi.fn());
});
afterEach(() => {
  setAuthFailureHandler(null);
  setBuyerSessionExpiredHandler(null);
  setConsentRequiredHandler(null);
});

describe("uploadFile", () => {
  it("envía multipart con CSRF e informa el progreso", async () => {
    document.cookie = "app_csrf=csrf-1; Path=/";
    FakeXHR.replies = [
      {
        status: 201,
        body: { id: "slot-1", status: "UPLOADED" },
        headers: { ETag: '"4"' },
        progress: [
          [50, 200],
          [200, 200],
        ],
      },
    ];
    const onProgress = vi.fn();

    const result = await uploadFile<{ id: string }>({
      path: "/api/v1/document-slots/slot-1/uploads",
      file,
      fields: { document_date: "2026-11-01" },
      onProgress,
    });

    expect(result.data).toEqual({ id: "slot-1", status: "UPLOADED" });
    expect(result.version).toBe(4);
    expect(onProgress.mock.calls).toEqual([[25], [100]]);
    const sent = FakeXHR.sent[0]!;
    expect(sent.url).toBe("http://localhost:3000/api/v1/document-slots/slot-1/uploads");
    expect(sent.headers["X-CSRFToken"]).toBe("csrf-1");
    expect(sent.headers["X-Request-ID"]).toMatch(/^[0-9a-f-]{36}$/);
    expect((sent.body.get("file") as File).name).toBe("extracto.pdf");
    expect(sent.body.get("document_date")).toBe("2026-11-01");
  });

  it("convierte los errores en ApiError", async () => {
    FakeXHR.replies = [{ status: 422, body: err("FILE_TOO_LARGE") }];
    const error = await uploadFile({ path: "/api/v1/document-slots/s/uploads", file }).catch(
      (e: unknown) => e,
    );
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 422, code: "FILE_TOO_LARGE" });
  });

  it("sin respuesta del servidor es un error de red", async () => {
    FakeXHR.replies = [{ status: 0, fail: true }];
    const error = await uploadFile({ path: "/api/v1/document-slots/s/uploads", file }).catch(
      (e: unknown) => e,
    );
    expect((error as ApiError).isNetworkError).toBe(true);
  });

  it("en rutas internas, un 401 renueva la sesión y reintenta una vez", async () => {
    let refreshes = 0;
    server.use(
      http.post(apiUrl("/auth/refresh"), () => {
        refreshes += 1;
        return HttpResponse.json({ session_expires_at: "2026-11-12T23:00:00Z" });
      }),
    );
    FakeXHR.replies = [
      { status: 401, body: err("NOT_AUTHENTICATED") },
      { status: 201, body: { id: "slot-1" } },
    ];
    const result = await uploadFile({ path: "/api/v1/document-slots/s/uploads", file });
    expect(result.data).toEqual({ id: "slot-1" });
    expect(refreshes).toBe(1);
    expect(FakeXHR.sent).toHaveLength(2);
  });

  it("en el portal no refresca: avisa la sesión vencida o el consentimiento", async () => {
    const onExpired = vi.fn();
    const onConsent = vi.fn();
    setBuyerSessionExpiredHandler(onExpired);
    setConsentRequiredHandler(onConsent);
    FakeXHR.replies = [
      { status: 401, body: err("SESSION_EXPIRED") },
      { status: 403, body: err("CONSENT_REQUIRED") },
    ];
    const path = "/api/v1/buyer/document-slots/s/uploads";
    await expect(uploadFile({ path, file })).rejects.toMatchObject({ code: "SESSION_EXPIRED" });
    await expect(uploadFile({ path, file })).rejects.toMatchObject({ code: "CONSENT_REQUIRED" });
    expect(onExpired).toHaveBeenCalledOnce();
    expect(onConsent).toHaveBeenCalledOnce();
    expect(FakeXHR.sent).toHaveLength(2);
  });

  it("se cancela con signal", async () => {
    FakeXHR.replies = [{ status: 201, body: {} }];
    const controller = new AbortController();
    const pending = uploadFile({
      path: "/api/v1/document-slots/s/uploads",
      file,
      signal: controller.signal,
    });
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });
});
