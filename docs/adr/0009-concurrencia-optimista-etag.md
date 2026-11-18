# ADR 0009 · Concurrencia optimista con `version`, `ETag` e `If-Match`

- **Estado:** aceptada.
- **Fecha:** módulo 8 (solicitudes); registrada el 2026-11-18.
- **Fuentes:** REQ §8.3 (principio 6); decisión 7 y Partes 2 y 3 de [`specs/TAREA-applications.md`](../../specs/TAREA-applications.md); decisión 6 de [`specs/TAREA-document-file.md`](../../specs/TAREA-document-file.md); `backend/apps/applications/concurrency.py`; `backend/tests/test_etag_contract.py`; [04 · System design §3.4](../guia/04-system-design.md#34-etag--if-match-no-pisar-la-edición-de-otro).

## Contexto

Asesor, admin y comprador pueden editar la misma solicitud a la vez. Sin control, el último en guardar borra en silencio lo que hizo el otro.

## Opciones consideradas

1. **Último que escribe gana.** Pérdida silenciosa de datos.
2. **Bloqueo pesimista** de la solicitud mientras alguien la edita en la pantalla. Bloqueos largos y abandonados.
3. **Concurrencia optimista:** un entero `version` que sube con cada cambio; el cliente manda la versión que vio y la API rechaza si cambió.

## Decisión

Opción 3. `credit_applications.version`; toda respuesta del expediente lleva `ETag: "<version>"`; todo `PUT`/`PATCH` exige `If-Match` (`428` sin él, `409 STALE_VERSION` si es viejo, con la versión actual en `details`); las acciones (transiciones, radicar, responder, desistir) mandan `expected_version` en el cuerpo. Un cambio sin diferencias reales no sube la versión. **Los documentos no tocan la versión** de la solicitud; los planes de comisión tienen su propia `version`. Dentro de la transacción, los servicios además bloquean las filas con `select_for_update`.

## Consecuencias

- **A favor:** nadie pierde trabajo en silencio; el front muestra "Alguien cambió esta solicitud" y ofrece recargar.
- **Por qué los documentos no la tocan:** si cada carga del comprador subiera la versión, el asesor no podría guardar la financiación mientras el comprador sube fotos. Para saber si el expediente documental cambió se usa la huella documental.
- **Consecuencia de eso:** una solicitud lista para radicar que deja de cumplir sigue en `READY_TO_FILE` (la guarda de la radicación la frena).
- **Contrato:** una prueba exige que toda operación con `If-Match` declare `ETag` en sus respuestas y en el `GET` del recurso.
