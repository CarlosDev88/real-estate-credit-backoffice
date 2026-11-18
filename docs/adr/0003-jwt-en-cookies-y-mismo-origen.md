# ADR 0003 · JWT en cookies `HttpOnly` con CSRF y proxy de mismo origen

- **Estado:** aceptada.
- **Fecha:** módulo 1 (identidad) y F0 del frontend; registrada el 2026-11-18.
- **Fuentes:** REQ §9.1 y §12 ("estrategia de cookies entre Next.js y API"); `backend/apps/identity/authentication.py`, `cookies.py`, `services.py`; `frontend/next.config.ts`, `frontend/src/lib/api/fetch.ts`; `backend/README.md` ("Internal Authentication"); [03 · Arquitectura §7](../guia/03-arquitectura.md#7-front--api-mismo-origen-por-el-proxy-de-next).

## Contexto

El equipo interno necesita sesiones que se puedan cortar al instante (desactivar a alguien) y que un script inyectado en la página no pueda robar. REQ §9.1 pide JWT de 15 minutos en cookie `HttpOnly`, `Secure`, `SameSite=Lax`, nunca en `localStorage`, y un refresh opaco, rotativo y de un solo uso. Además, frontend y API corren en puertos distintos.

## Opciones consideradas

1. **JWT en `localStorage` con cabecera `Authorization`.** Fácil, pero cualquier XSS lo lee.
2. **Sesión de Django clásica.** Válida, pero REQ pide JWT con claims verificables y refresh rotativo.
3. **JWT en cookie `HttpOnly` con CORS** entre el origen del front y el de la API. Funciona, pero exige CORS con credenciales y cookies entre sitios.
4. **JWT en cookie `HttpOnly` y un proxy de mismo origen**: Next.js reenvía `/api/v1/*` a Django, y el navegador solo ve un origen.

## Decisión

Opción 4. La API pone `app_access` (JWT HS256 de 15 min con `iss`, `aud`, `exp`, `nbf`, `jti` y `sid`), `app_refresh` (opaco, de un solo uso, solo su hash en `auth_sessions`, 8 h desde el login) y `app_csrf` (legible). Con HTTPS llevan el prefijo `__Host-`. Cada petición revisa que la sesión `sid` siga activa. Reutilizar un refresh rotado revoca toda la cadena. El front copia `app_csrf` en `X-CSRFToken` en cada escritura. `next.config.ts` reescribe `/api/v1/:path*` hacia `API_ORIGIN`.

## Consecuencias

- **A favor:** el JavaScript nunca ve el token; desactivar un usuario corta su acceso en la siguiente petición; sin CORS en la demo; las descargas del modo simple (rutas relativas firmadas) pasan por el mismo proxy.
- **En contra:** cada petición consulta `auth_sessions` (una consulta por petición, a cambio del corte inmediato); dos renovaciones simultáneas con el mismo refresh parecen un robo y cierran la sesión, así que el front serializa el refresh.
- **Pendiente para producción:** decidir el dominio final y si el proxy sigue siendo Next.js o un balanceador (REQ §12).
- `frontend/src/proxy.ts` solo redirige al login a quien no tiene cookie; no es un control de seguridad.
