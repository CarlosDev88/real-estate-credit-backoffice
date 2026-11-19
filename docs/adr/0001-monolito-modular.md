# ADR 0001 · Monolito modular en Django + DRF

- **Estado:** aceptada.
- **Fecha:** decidida en los requerimientos (REQ §8.1, §14.1); registrada el 2026-11-18.
- **Fuentes:** [`docs/REQUERIMIENTOS_MVP_CREDITO.md`](../REQUERIMIENTOS_MVP_CREDITO.md) §8.1 a §8.3; `backend/config/settings/base.py` (`INSTALLED_APPS`); [03 · Arquitectura §3](../guia/03-arquitectura.md#3-el-monolito-modular).

## Contexto

El producto gestiona expedientes de crédito: un cambio de negocio (por ejemplo, registrar una devolución del banco) toca a la vez la radicación, la respuesta, las observaciones, los documentos, el estado de la solicitud y su historial. El riesgo principal es la **consistencia** de expedientes, permisos, documentos y auditoría, no el cómputo masivo. El equipo es pequeño y el alcance termina en la radicación manual: no hay conectores con bancos.

## Opciones consideradas

1. **Microservicios** (por ejemplo, documentos, radicación y notificaciones por separado). Escalan por partes, pero cada cambio de negocio cruzaría varias bases y exigiría sagas o compensaciones, más una red y un despliegue por servicio.
2. **Monolito sin fronteras** (una app con todos los modelos). Simple al principio, pero el acoplamiento crece y no hay dueño claro de cada tabla.
3. **Monolito modular**: una sola aplicación y una sola base, partida en apps con fronteras de dominio, cada una dueña de sus tablas.
4. **FastAPI** u otro framework: descartado en REQ §8.1; Django trae administración, migraciones, ORM con transacciones y un ecosistema (DRF, drf-spectacular) que cubre lo que el MVP necesita.

## Decisión

Monolito modular en **Django 5.2 + Django REST Framework** sobre **PostgreSQL 16**, con **16 apps** de dominio bajo `backend/apps/`. Cada tabla tiene un único dueño (DER §15). Los módulos se comunican con imports "hacia abajo" (de lo más específico a lo más básico) y con señales para los efectos laterales ([ADR 0007](0007-senales-despues-del-commit.md)).

## Consecuencias

- **A favor:** un cambio de negocio es un `transaction.atomic()`; los permisos y el alcance se calculan con las mismas funciones en todo el sistema; un PR cambia backend, contrato y tipos del front a la vez.
- **En contra:** todo se despliega junto y escala junto. Se mitiga con el trabajo asíncrono en un worker aparte (que ya existe en el modo completo).
- **Disciplina necesaria:** respetar las fronteras. Hay dos imports "hacia arriba" acotados y documentados (`applications` usa un archivo de `filings` que solo importa modelos; `documents` usa servicios de `applications`).
- **Salida, si hiciera falta:** el primer candidato a separarse es el trabajo asíncrono, que ya solo recibe ids.
