# ADR 0008 · `Idempotency-Key` opcional por cabecera

- **Estado:** aceptada (se desvía de REQ §8.3 y §9.3, que la pedían obligatoria).
- **Fecha:** módulo 13; registrada el 2026-11-18.
- **Fuentes:** REQ §8.3 (principio 5), §9.3; Parte 3 de [`specs/TAREA-notificaciones.md`](../../specs/TAREA-notificaciones.md); `backend/apps/idempotency/` (`decorators.py`, `services.py`, `models.py`); `backend/tests/applications/idempotency/test_idempotency.py`.

## Contexto

La red puede fallar justo después de que el servidor radicó o registró una respuesta del banco; el cliente reintenta y se duplica. Los pasos anteriores al módulo 13 ya tenían defensas naturales (una solicitud abierta por oportunidad, un paquete se radica una vez, `expected_version`), pero no un mecanismo general. El frontend ya estaba en uso y no enviaba ninguna cabecera.

## Opciones consideradas

1. **Obligatoria** en los `POST` críticos, como pedía REQ. Rompía el front existente de inmediato.
2. **Solo idempotencia natural** (unicidades de la base). No cubre todos los casos ni devuelve la respuesta original.
3. **Opcional:** sin cabecera todo funciona igual; con ella, una repetición devuelve la respuesta original.

## Decisión

Opción 3, con un decorador único `@idempotent` en 9 `POST` (transición de estado, paquete, radicación, respuesta del banco, enlace mágico, liquidar, anular y pagar comisiones, exportación de reportes). Con la cabecera: misma clave y mismo cuerpo → la respuesta original (código, JSON, `ETag`, `Location`); otro cuerpo → `422 IDEMPOTENCY_CONFLICT`; una petición en curso → `409 IDEMPOTENCY_IN_PROGRESS` sin esperar. Solo se guardan las `2xx`; las claves vencen a las 24 h. La huella es el SHA-256 del JSON canónico. Únicos parciales por actor (usuario interno o sesión del comprador).

## Consecuencias

- **A favor:** no rompió nada; el front puede adoptarla de a poco; repetir es seguro y barato.
- **En contra:** sin cabecera, la protección vuelve a ser la natural de cada operación.
- **Excepción:** el enlace mágico no repite su respuesta (lleva el token en claro, que nunca se guarda): responde `409 IDEMPOTENCY_REPLAY_UNAVAILABLE`.
- **Límite conocido:** si el proceso muere a mitad, la clave queda "en curso" hasta que vence.
- **Corrección del SQL:** `UNIQUE NULLS NOT DISTINCT` hacía chocar a dos usuarios internos con la misma clave; quedaron únicos parciales.
