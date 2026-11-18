# ADR 0004 · Enlace mágico sin cuenta para el comprador

- **Estado:** aceptada.
- **Fecha:** módulo 9 (acceso del comprador); registrada el 2026-11-18.
- **Fuentes:** RF-02, RNF-02, REQ §9.1; [`specs/TAREA-buyer-access.md`](../../specs/TAREA-buyer-access.md) (decisiones 1 a 18); `backend/apps/identity/buyer_access.py`, `buyer_sessions.py`, `buyer_authentication.py`.

## Contexto

El comprador entra pocas veces, casi siempre desde el celular y a pedido de su asesor. Una cuenta con contraseña sería una barrera y otro secreto que proteger. A la vez, lo que ve es su expediente: datos personales, ingresos y documentos.

## Opciones consideradas

1. **Cuenta con contraseña** para el comprador, como los usuarios internos. Más fricción y recuperación de contraseña para gente que entra tres veces.
2. **Código por SMS o correo (OTP)** en cada entrada. Exige un proveedor de SMS, fuera del MVP.
3. **Enlace mágico de un solo uso** emitido por el equipo interno, que abre una sesión temporal ligada a una sola solicitud.

## Decisión

Opción 3. El enlace lo emiten el admin, el asesor asignado o el broker que originó (nunca la constructora), siempre para el **titular** activo; vence en 72 h (1 a 168); en la base solo se guarda su hash; emitir uno nuevo revoca los pendientes. Al consumirlo, el front borra el token de la URL y la API abre una sesión de **24 h absolutas** (cookie `buyer_session`) que cierra las demás del mismo comprador y solicitud. Las rutas del comprador son exclusivas (`/buyer/*`), con DTO propios, y la cookie del comprador no sirve en las rutas internas ni al revés.

## Consecuencias

- **A favor:** cero contraseñas del comprador; el daño de un enlace reenviado se limita a una solicitud y 24 horas; límites de 5 consumos por hora por IP y 3 emisiones por hora.
- **En contra:** si el enlace vence, el comprador depende de su asesor para otro (que lo pida él mismo a su correo es una mejora futura); un enlace es por titular, no por participante.
- **Correos:** los avisos al comprador **no** llevan el enlace, para que un correo reenviado no dé acceso.
- **Idempotencia:** repetir la clave al emitir responde `409 IDEMPOTENCY_REPLAY_UNAVAILABLE`, porque la respuesta lleva el token en claro y nunca se guarda ([ADR 0008](0008-idempotencia-opcional.md)).
