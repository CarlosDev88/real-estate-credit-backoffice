# ADR 0015 · Modo local simple (3 contenedores) y modo completo (perfil `full`)

- **Estado:** aceptada.
- **Fecha:** tarea `TAREA-local-simple.md`; registrada el 2026-11-18.
- **Fuentes:** [`specs/TAREA-local-simple.md`](../../specs/TAREA-local-simple.md); `backend/docker-compose.yml`; `backend/config/settings/base.py`, `backend/config/runtime_services.py`; Anexo A de [`specs/TAREA-documentacion.md`](../../specs/TAREA-documentacion.md); [03 · Arquitectura §8](../guia/03-arquitectura.md#8-los-dos-modos-locales).

## Contexto

El proyecto no tiene despliegue: se entrega para correr en local y en CI (Anexo A). Quien lo revisa necesita verlo funcionar rápido y en una máquina normal; a la vez, la arquitectura asíncrona real (almacenamiento S3, Redis, worker, antivirus) tiene que poder mostrarse.

## Opciones consideradas

1. **Solo el modo completo** (8 contenedores, ClamAV descarga firmas por varios minutos al arrancar).
2. **Solo un modo simplificado**, borrando la arquitectura asíncrona. Se perdería lo que la demuestra.
3. **Dos modos con el mismo código**: el `.env` decide la implementación de cada servicio y el perfil de compose decide qué contenedores se levantan.

## Decisión

Opción 3. Sin perfil: `postgres`, `backend` y `frontend`, con almacenamiento en disco, caché de límites en PostgreSQL (`DatabaseCache`, tabla `django_cache`), tareas en el mismo proceso y escáner de prueba. Con `--profile full`: además `redis`, `seaweedfs`, `storage-init`, `worker` y `clamav`. Las dependencias del backend hacia los servicios del perfil se declaran con `required: false`. El backend corre al arrancar `migrate`, `createcachetable`, `refresh_application_completeness` y `describe_local_services` (que escribe una línea con el modo de cada servicio).

## Consecuencias

- **A favor:** la demo arranca con 3 contenedores; la arquitectura completa está a un perfil de distancia; el código de dominio no sabe en qué modo corre.
- **Seguridad:** los servicios del modo simple (disco, memoria, escáner falso) **exigen `DEBUG`**; sin él, la app no arranca.
- **En contra:** los archivos de un modo no se ven en el otro; el modo simple no prueba el antivirus real.
- **Siguiente paso:** la demo con un solo comando (Parte 4 de la documentación) encadena estos pasos sobre el modo simple.
