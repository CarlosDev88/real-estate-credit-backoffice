# ADR 0005 · Alcance por rol con `404`

- **Estado:** aceptada.
- **Fecha:** módulo 5 (CRM) y siguientes; registrada el 2026-11-18.
- **Fuentes:** REQ §8.3 (principio 1), §8.4, §8.6, §9.2; docstring de `backend/apps/crm/services.py`; `backend/apps/applications/services.py` (`applications_visible_to`); `backend/apps/identity/permissions.py` (`HasPermissionCode`).

## Contexto

Un asesor solo debe ver sus solicitudes asignadas; un broker, lo que originó; un comprador, su expediente. El riesgo típico es BOLA/IDOR: cambiar el id de la URL y ver el expediente de otro. También importa no revelar que un recurso existe.

## Opciones consideradas

1. **Buscar por id y después comprobar** si el usuario puede verlo, respondiendo `403`. Fácil de olvidar en una vista y confirma que el recurso existe.
2. **Filtrar en el frontend.** No es seguridad.
3. **Consultas que nacen filtradas por el alcance** del actor, con `404` para lo que queda fuera, más un permiso por código en cada vista.

## Decisión

Opción 3, en dos capas:

- **Permiso por código**: cada vista declara `required_permissions` por método y `HasPermissionCode` lo exige; un método sin permiso declarado se niega. El front decide qué mostrar con los permisos de `/auth/me`, nunca con el nombre del rol.
- **Alcance**: la consulta empieza con `*_visible_to(user)`; si el recurso no está, `404 RESOURCE_NOT_FOUND`. La regla de las solicitudes vive en un solo lugar (`crm.services.application_scope_condition`) y la reutilizan el listado, los conteos y los reportes. Ningún id que mande el cliente amplía privilegios (la constructora se deriva de su membresía).

## Consecuencias

- **A favor:** una vista nueva hereda el alcance si usa la función del módulo; un atacante no distingue "no existe" de "no es tuyo".
- **Excepción deliberada:** un permiso que el rol no tiene responde `403` (por ejemplo, el broker en el expediente completo): ahí no se revela ningún recurso concreto. En reportes, un **filtro** fuera del alcance responde `403 FILTER_OUT_OF_SCOPE`, porque un resultado vacío haría creer que no hay datos.
- **Verificación:** 156 comprobaciones de `404` en `backend/tests/`; la auditoría de seguridad (fase A, #32) pidió las 235 operaciones como cada uno de 9 actores: 2.115 casos, **ninguna brecha de acceso** ([`docs/seguridad/03-matriz-acceso.md`](../seguridad/03-matriz-acceso.md)). Esa matriz quedó como prueba y corre en cada PR.
