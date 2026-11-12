import { NextResponse, type NextRequest } from "next/server";

// Solo experiencia de uso: si no hay ninguna cookie de sesión interna, se va al
// login sin pintar el backoffice. No mira permisos ni datos ni valida la cookie:
// la seguridad la pone la API.

// En local (AUTH_COOKIE_SECURE=false) las cookies no llevan el prefijo __Host-.
const ACCESS_COOKIES = (process.env.AUTH_ACCESS_COOKIE ?? "__Host-app_access,app_access").split(
  ",",
);
const REFRESH_COOKIES = (process.env.AUTH_REFRESH_COOKIE ?? "__Host-app_refresh,app_refresh").split(
  ",",
);

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  if (pathname === "/") return NextResponse.next();

  const names = [...ACCESS_COOKIES, ...REFRESH_COOKIES].map((n) => n.trim()).filter(Boolean);
  if (names.some((name) => request.cookies.has(name))) return NextResponse.next();

  const login = new URL("/login", request.url);
  login.searchParams.set("next", `${pathname}${search}`);
  return NextResponse.redirect(login);
}

export const config = {
  // Todo menos lo público: login, acceso del comprador, portal, páginas de desarrollo,
  // la API (rewrite), los recursos de Next.js y los archivos estáticos.
  matcher: ["/((?!login|acceso|portal|dev|api|_next|.*\\..*).*)"],
};
