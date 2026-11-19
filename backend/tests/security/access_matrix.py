"""Matriz de acceso de la API: qué espera cada actor en cada operación del contrato.

``specs/TAREA-seguridad.md``, Parte 3. La prueba es ``test_access_matrix.py`` y la tabla
legible para el portafolio la genera ``backend/security/render_matrix.py`` en
``docs/seguridad/03-matriz-acceso.md``.

Cada fila es ``"MÉTODO /ruta": PATRÓN``. El patrón tiene una letra por actor, siempre en
este orden (``ACTORS``)::

    anon  admin  advisor_owner  advisor_other  broker_owner  broker_other  partner
    buyer_owner  buyer_other

- ``A`` = ``ALLOW``: 2xx, o un 4xx de negocio que muestra que pasó la autorización (400,
  409, 412, 422, 428).
- ``U`` = ``DENY_401``: sin sesión válida para esa ruta (el comprador en una ruta interna y
  un usuario interno en una del portal también, porque cada una lee su propia cookie).
- ``F`` = ``DENY_403``: con sesión, pero el rol no tiene el permiso de la vista.
- ``H`` = ``HIDE_404``: con permiso, pero el recurso está fuera de su alcance; no confirma
  que existe.

Los parámetros de ruta son siempre los ids del lado A (``conftest.World.path_ids``): la
solicitud de ``asesora.lucia`` que originó ``broker``, con la sesión del comprador A.

Fuentes, en este orden: REQ §3 (actores; si choca con la API, manda REQ), API §3 (fuera
del alcance → 404), API §25 (matriz por módulo) y las secciones de cada módulo, y el
``required_permissions`` de cada vista con los permisos sembrados por rol. Donde la
documentación no define el caso se aplica la regla general del proyecto (sin sesión → 401;
sin el permiso del rol → 403; fuera del alcance → 404) y queda anotado en
``GENERAL_RULE_DECISIONS``.
"""

ACTORS = (
    "anon",
    "admin",
    "advisor_owner",
    "advisor_other",
    "broker_owner",
    "broker_other",
    "partner",
    "buyer_owner",
    "buyer_other",
)

ALLOW = "ALLOW"
DENY_401 = "DENY_401"
DENY_403 = "DENY_403"
HIDE_404 = "HIDE_404"
LETTERS = {"A": ALLOW, "U": DENY_401, "F": DENY_403, "H": HIDE_404}
# Estados que cuentan como cada resultado.
ALLOW_STATUSES = frozenset({400, 409, 412, 422, 428})
STATUS_FOR = {DENY_401: 401, DENY_403: 403, HIDE_404: 404}

# --- Patrones con nombre (la razón va en el comentario) ---------------------------------

# Sin sesión: login, recuperación, consumo del enlace, aceptar invitación y los cierres de
# sesión (API §3 `PUBLIC`). Cualquiera llega a la validación.
PUBLIC = "AAAAAAAAA"
# `POST /auth/refresh` sin cookie de refresh: 401 para todos (la matriz no manda la cookie
# de refresh; la rotación se prueba en la Parte 4).
NO_REFRESH_COOKIE = "UUUUUUUUU"
# Cualquier usuario interno con sesión (`IsAuthenticated` o permiso de los 4 roles):
# `/auth/me`, cambio de contraseña, metadatos, proyectos visibles.
ANY_INTERNAL = "UAAAAAAUU"
# Solo administración (API §25: usuarios y roles, catálogos, flujo, auditoría, planes,
# liquidación y pagos de comisiones, escrituras de bancos, reglas y requisitos).
ADMIN_ONLY = "UAFFFFFUU"
# Administrador y asesor, sin alcance por objeto: lectura de configuración (API §25: "solo
# la consultan ADMIN y ADVISOR"), reportes y dashboard de cartera, Mi día, tareas
# propias, validación de proyectos (REQ §3).
ADMIN_ADVISOR = "UAAAFFFUU"
# Además la constructora (API §11/§12: partners y proyectos de su partner).
ADMIN_ADVISOR_PARTNER = "UAAAFFAUU"
# Administrador y la constructora de esa membresía (API §11.2: "solo puede consultar su
# propia membresía y partner").
ADMIN_PARTNER = "UAFFFFAUU"
# Listados y creación con alcance: cada uno ve lo suyo (clientes, oportunidades,
# solicitudes, resumen del dashboard). La constructora no consulta expedientes (REQ §3).
INTERNAL_NO_PARTNER = "UAAAAAFUU"
# Expediente de una solicitud asignada: el asesor dueño sí, el otro asesor 404 (API §3).
# El broker y la constructora no tienen el permiso (REQ §3: "no ve archivos ni datos
# financieros detallados, no carga documentos, no radica"; API §25 Expediente: 403).
ASSIGNED = "UAAHFFFUU"
# Lo que el broker originador sí ve (REQ §3: "consulta el resumen de estado de sus
# expedientes"; API §25: solicitudes y enlaces originados, seguimiento de la radicación con
# tipo, fecha y mensaje público). El otro broker y el otro asesor: 404.
ASSIGNED_OR_ORIGINATED = "UAAHAHFUU"
# El broker tiene el permiso de lectura, pero la ruta entrega archivos o revoca un enlace
# que no emitió: el originador recibe 403 (REQ §3; API §25 "revoca los propios") y el
# otro broker, 404 (fuera de su alcance).
ORIGINATED_NO_FILES = "UAAHFHFUU"
# Solo brokers: su listado de oportunidades (`/broker/opportunities`).
BROKER_ONLY = "UFFFAAFUU"
# "Mis comisiones": asesor y broker ven solo su parte (API §25 Comisiones).
OWN_COMMISSIONS = "UFAAAAFUU"
# Portal: cualquier sesión de comprador sobre lo suyo (su sesión, sus procesos, sus
# notificaciones, catálogos públicos).
BUYER_SESSION = "UUUUUUUAA"
# Portal sobre un recurso del comprador A: el comprador B recibe 404 (API §8: "un ID
# válido de otro expediente responde 404").
BUYER_OWN = "UUUUUUUAH"

# Nombre y razón corta de cada patrón, para la tabla de ``render_matrix.py``.
PATTERN_NOTES: dict[str, tuple[str, str]] = {
    PUBLIC: ("PUBLIC", "Sin sesión: cualquiera llega a la validación (API §3 `PUBLIC`)."),
    NO_REFRESH_COOKIE: ("NO_REFRESH_COOKIE", "Sin cookie de refresh: 401 para todos."),
    ANY_INTERNAL: ("ANY_INTERNAL", "Cualquier usuario interno con sesión."),
    ADMIN_ONLY: ("ADMIN_ONLY", "Solo administración (API §25)."),
    ADMIN_ADVISOR: ("ADMIN_ADVISOR", "Administrador y asesor, sin alcance por objeto."),
    ADMIN_ADVISOR_PARTNER: (
        "ADMIN_ADVISOR_PARTNER",
        "Además la constructora sobre lo de su partner (API §11 y §12).",
    ),
    ADMIN_PARTNER: ("ADMIN_PARTNER", "Administrador y la constructora dueña (API §11.2)."),
    INTERNAL_NO_PARTNER: (
        "INTERNAL_NO_PARTNER",
        "Listados con alcance; la constructora no ve expedientes (REQ §3).",
    ),
    ASSIGNED: (
        "ASSIGNED",
        "Asesor asignado; otro asesor 404; broker y constructora 403 (REQ §3, API §25).",
    ),
    ASSIGNED_OR_ORIGINATED: (
        "ASSIGNED_OR_ORIGINATED",
        "Además el broker originador (resumen y seguimiento, REQ §3); los otros, 404.",
    ),
    ORIGINATED_NO_FILES: (
        "ORIGINATED_NO_FILES",
        "Archivos o enlace ajeno: broker originador 403, otro broker 404.",
    ),
    BROKER_ONLY: ("BROKER_ONLY", "Solo brokers, cada uno lo suyo."),
    OWN_COMMISSIONS: ("OWN_COMMISSIONS", "Asesor y broker, solo su parte (API §25)."),
    BUYER_SESSION: ("BUYER_SESSION", "Cualquier sesión de comprador, sobre lo suyo."),
    BUYER_OWN: ("BUYER_OWN", "Recurso del comprador A: el comprador B, 404 (API §8)."),
}

# --- La matriz: una fila por operación del contrato ---------------------------------

MATRIX: dict[str, str] = {
    # --- /application-participants ---
    "GET /api/v1/application-participants/{participant_id}": ASSIGNED,
    "PATCH /api/v1/application-participants/{participant_id}": ASSIGNED,
    "DELETE /api/v1/application-participants/{participant_id}": ASSIGNED,
    "GET /api/v1/application-participants/{participant_id}/financial-profile": ASSIGNED,
    "PUT /api/v1/application-participants/{participant_id}/financial-profile": ASSIGNED,
    # --- /applications ---
    "GET /api/v1/applications": INTERNAL_NO_PARTNER,
    "POST /api/v1/applications": ADMIN_ADVISOR,
    "GET /api/v1/applications/{application_id}": ASSIGNED_OR_ORIGINATED,
    "PATCH /api/v1/applications/{application_id}": ASSIGNED,
    "GET /api/v1/applications/{application_id}/activity": ASSIGNED_OR_ORIGINATED,
    "POST /api/v1/applications/{application_id}/assignments": ASSIGNED,
    "GET /api/v1/applications/{application_id}/available-actions": ASSIGNED,
    "POST /api/v1/applications/{application_id}/bank-rule-evaluations": ASSIGNED,
    "GET /api/v1/applications/{application_id}/bank-rule-evaluations/latest": ASSIGNED,
    "GET /api/v1/applications/{application_id}/buyer-access-links": ASSIGNED_OR_ORIGINATED,
    "POST /api/v1/applications/{application_id}/buyer-access-links": ASSIGNED_OR_ORIGINATED,
    "POST /api/v1/applications/{application_id}/commission-settlement": ADMIN_ONLY,
    "GET /api/v1/applications/{application_id}/completeness": ASSIGNED,
    "GET /api/v1/applications/{application_id}/consents": ASSIGNED,
    # Lista de paquetes de la solicitud (#31): mismo permiso (`filings.prepare`) y alcance
    # (`get_application`) que el POST.
    "GET /api/v1/applications/{application_id}/document-package-jobs": ASSIGNED,
    "POST /api/v1/applications/{application_id}/document-package-jobs": ASSIGNED,
    "GET /api/v1/applications/{application_id}/document-slots": ASSIGNED,
    "POST /api/v1/applications/{application_id}/document-slots/refresh": ASSIGNED,
    "GET /api/v1/applications/{application_id}/eligible-bank-products": ASSIGNED,
    "GET /api/v1/applications/{application_id}/filings": ASSIGNED_OR_ORIGINATED,
    "POST /api/v1/applications/{application_id}/filings": ASSIGNED,
    "GET /api/v1/applications/{application_id}/financing": ASSIGNED,
    "PUT /api/v1/applications/{application_id}/financing": ASSIGNED,
    "GET /api/v1/applications/{application_id}/notes": ASSIGNED,
    "POST /api/v1/applications/{application_id}/notes": ASSIGNED,
    "GET /api/v1/applications/{application_id}/notifications": ASSIGNED,
    "GET /api/v1/applications/{application_id}/participants": ASSIGNED,
    "POST /api/v1/applications/{application_id}/participants": ASSIGNED,
    "GET /api/v1/applications/{application_id}/property": ASSIGNED,
    "PUT /api/v1/applications/{application_id}/property": ASSIGNED,
    "GET /api/v1/applications/{application_id}/status-history": ASSIGNED,
    "POST /api/v1/applications/{application_id}/status-transitions": ASSIGNED,
    "GET /api/v1/applications/{application_id}/summary": ASSIGNED_OR_ORIGINATED,
    "POST /api/v1/applications/{application_id}/withdrawals": ASSIGNED,
    "GET /api/v1/applications/quick-filters": INTERNAL_NO_PARTNER,
    # --- /audit-events ---
    "GET /api/v1/audit-events": ADMIN_ONLY,
    "GET /api/v1/audit-events/{event_id}": ADMIN_ONLY,
    # --- /auth ---
    "POST /api/v1/auth/change-password": ANY_INTERNAL,
    "POST /api/v1/auth/login": PUBLIC,
    "POST /api/v1/auth/logout": PUBLIC,
    "GET /api/v1/auth/me": ANY_INTERNAL,
    "POST /api/v1/auth/password-reset-requests": PUBLIC,
    "POST /api/v1/auth/password-resets/confirm": PUBLIC,
    "POST /api/v1/auth/refresh": NO_REFRESH_COOKIE,
    # --- /bank-policy-rules ---
    "GET /api/v1/bank-policy-rules": ADMIN_ADVISOR,
    "POST /api/v1/bank-policy-rules": ADMIN_ONLY,
    "GET /api/v1/bank-policy-rules/fields": ADMIN_ADVISOR,
    "GET /api/v1/bank-policy-rules/{rule_id}": ADMIN_ADVISOR,
    "PATCH /api/v1/bank-policy-rules/{rule_id}": ADMIN_ONLY,
    "POST /api/v1/bank-policy-rules/{rule_id}/activate": ADMIN_ONLY,
    "POST /api/v1/bank-policy-rules/{rule_id}/deactivate": ADMIN_ONLY,
    "POST /api/v1/bank-policy-rules/{rule_id}/test": ADMIN_ONLY,
    "GET /api/v1/bank-policy-rules/{rule_id}/versions": ADMIN_ADVISOR,
    # --- /bank-products ---
    "GET /api/v1/bank-products": ADMIN_ADVISOR,
    "POST /api/v1/bank-products": ADMIN_ONLY,
    "GET /api/v1/bank-products/{product_id}": ADMIN_ADVISOR,
    "PATCH /api/v1/bank-products/{product_id}": ADMIN_ONLY,
    "POST /api/v1/bank-products/{product_id}/activate": ADMIN_ONLY,
    "POST /api/v1/bank-products/{product_id}/deactivate": ADMIN_ONLY,
    "PUT /api/v1/bank-products/{product_id}/purposes": ADMIN_ONLY,
    # --- /banks ---
    "GET /api/v1/banks": ADMIN_ADVISOR,
    "POST /api/v1/banks": ADMIN_ONLY,
    "GET /api/v1/banks/{bank_id}": ADMIN_ADVISOR,
    "PATCH /api/v1/banks/{bank_id}": ADMIN_ONLY,
    "POST /api/v1/banks/{bank_id}/activate": ADMIN_ONLY,
    "POST /api/v1/banks/{bank_id}/deactivate": ADMIN_ONLY,
    # --- /broker ---
    "GET /api/v1/broker/opportunities": BROKER_ONLY,
    # --- /buyer-access-links ---
    "DELETE /api/v1/buyer-access-links/{link_id}": ORIGINATED_NO_FILES,
    # --- /buyer-access ---
    "POST /api/v1/buyer-access/consume": PUBLIC,
    # --- /buyer ---
    "GET /api/v1/buyer/applications/{application_id}": BUYER_OWN,
    "GET /api/v1/buyer/applications/{application_id}/activity": BUYER_OWN,
    "GET /api/v1/buyer/applications/{application_id}/consents": BUYER_OWN,
    "POST /api/v1/buyer/applications/{application_id}/consents": BUYER_OWN,
    "GET /api/v1/buyer/applications/{application_id}/document-slots": BUYER_OWN,
    "GET /api/v1/buyer/applications/{application_id}/eligible-bank-products": BUYER_OWN,
    "GET /api/v1/buyer/applications/{application_id}/financing": BUYER_OWN,
    "PUT /api/v1/buyer/applications/{application_id}/financing": BUYER_OWN,
    "GET /api/v1/buyer/applications/{application_id}/participants": BUYER_OWN,
    "GET /api/v1/buyer/applications/{application_id}/profile": BUYER_OWN,
    "PATCH /api/v1/buyer/applications/{application_id}/profile": BUYER_OWN,
    "GET /api/v1/buyer/applications/{application_id}/property": BUYER_OWN,
    "PUT /api/v1/buyer/applications/{application_id}/property": BUYER_OWN,
    "POST /api/v1/buyer/applications/{application_id}/withdrawals": BUYER_OWN,
    "GET /api/v1/buyer/document-files/{file_id}/download": BUYER_OWN,
    "GET /api/v1/buyer/document-slots/{slot_id}": BUYER_OWN,
    "POST /api/v1/buyer/document-slots/{slot_id}/uploads": BUYER_OWN,
    "GET /api/v1/buyer/document-slots/{slot_id}/versions": BUYER_OWN,
    "GET /api/v1/buyer/financial-profiles/{profile_id}/income-sources": BUYER_OWN,
    "POST /api/v1/buyer/financial-profiles/{profile_id}/income-sources": BUYER_OWN,
    "PATCH /api/v1/buyer/income-sources/{income_source_id}": BUYER_OWN,
    "DELETE /api/v1/buyer/income-sources/{income_source_id}": BUYER_OWN,
    "GET /api/v1/buyer/metadata/catalogs/{catalog_code}": BUYER_SESSION,
    "GET /api/v1/buyer/notifications": BUYER_SESSION,
    "PATCH /api/v1/buyer/notifications/{notification_id}/read": BUYER_OWN,
    "POST /api/v1/buyer/notifications/read-all": BUYER_SESSION,
    "GET /api/v1/buyer/notifications/unread-count": BUYER_SESSION,
    "GET /api/v1/buyer/participants/{participant_id}/financial-profile": BUYER_OWN,
    "PUT /api/v1/buyer/participants/{participant_id}/financial-profile": BUYER_OWN,
    "POST /api/v1/buyer/participants/{participant_id}/financial-profile/confirmation": BUYER_OWN,
    "GET /api/v1/buyer/processes": BUYER_SESSION,
    "GET /api/v1/buyer/session": BUYER_SESSION,
    "POST /api/v1/buyer/session/logout": PUBLIC,
    # --- /catalog-items ---
    "GET /api/v1/catalog-items/{item_id}": ADMIN_ONLY,
    "PATCH /api/v1/catalog-items/{item_id}": ADMIN_ONLY,
    "POST /api/v1/catalog-items/{item_id}/activate": ADMIN_ONLY,
    "POST /api/v1/catalog-items/{item_id}/deactivate": ADMIN_ONLY,
    # --- /catalogs ---
    "GET /api/v1/catalogs": ADMIN_ONLY,
    "POST /api/v1/catalogs": ADMIN_ONLY,
    "GET /api/v1/catalogs/{catalog_id}": ADMIN_ONLY,
    "PATCH /api/v1/catalogs/{catalog_id}": ADMIN_ONLY,
    "GET /api/v1/catalogs/{catalog_id}/items": ADMIN_ONLY,
    "POST /api/v1/catalogs/{catalog_id}/items": ADMIN_ONLY,
    "PUT /api/v1/catalogs/{catalog_id}/items/order": ADMIN_ONLY,
    # --- /client-addresses ---
    "PATCH /api/v1/client-addresses/{address_id}": ASSIGNED,
    "DELETE /api/v1/client-addresses/{address_id}": ASSIGNED,
    # --- /clients ---
    "GET /api/v1/clients": INTERNAL_NO_PARTNER,
    "POST /api/v1/clients": INTERNAL_NO_PARTNER,
    "GET /api/v1/clients/{client_id}": ASSIGNED_OR_ORIGINATED,
    "PATCH /api/v1/clients/{client_id}": ASSIGNED_OR_ORIGINATED,
    "GET /api/v1/clients/{client_id}/addresses": ASSIGNED,
    "POST /api/v1/clients/{client_id}/addresses": ASSIGNED,
    "GET /api/v1/clients/{client_id}/applications": ASSIGNED_OR_ORIGINATED,
    "GET /api/v1/clients/{client_id}/opportunities": ASSIGNED_OR_ORIGINATED,
    # --- /commission-plans ---
    "GET /api/v1/commission-plans": ADMIN_ONLY,
    "POST /api/v1/commission-plans": ADMIN_ONLY,
    "GET /api/v1/commission-plans/{plan_id}": ADMIN_ONLY,
    "PATCH /api/v1/commission-plans/{plan_id}": ADMIN_ONLY,
    "POST /api/v1/commission-plans/{plan_id}/close": ADMIN_ONLY,
    # --- /commission-settlements ---
    "GET /api/v1/commission-settlements": ADMIN_ONLY,
    "GET /api/v1/commission-settlements/{settlement_id}": ADMIN_ONLY,
    "POST /api/v1/commission-settlements/{settlement_id}/void": ADMIN_ONLY,
    # --- /commission-shares ---
    "POST /api/v1/commission-shares/{share_id}/pay": ADMIN_ONLY,
    # --- /dashboard ---
    "GET /api/v1/dashboard/bank-results": ADMIN_ADVISOR,
    "GET /api/v1/dashboard/funnel": INTERNAL_NO_PARTNER,
    "GET /api/v1/dashboard/summary": INTERNAL_NO_PARTNER,
    "GET /api/v1/dashboard/workload": ADMIN_ADVISOR,
    # --- /document-files ---
    "GET /api/v1/document-files/{file_id}": ASSIGNED,
    "GET /api/v1/document-files/{file_id}/download": ASSIGNED,
    "GET /api/v1/document-files/{file_id}/scan-status": ASSIGNED,
    # --- /document-package-jobs ---
    "GET /api/v1/document-package-jobs/{job_id}": ASSIGNED,
    "GET /api/v1/document-package-jobs/{job_id}/download": ASSIGNED,
    # --- /document-requirements ---
    "GET /api/v1/document-requirements": ADMIN_ADVISOR,
    "POST /api/v1/document-requirements": ADMIN_ONLY,
    "GET /api/v1/document-requirements/{requirement_id}": ADMIN_ADVISOR,
    "PATCH /api/v1/document-requirements/{requirement_id}": ADMIN_ONLY,
    "POST /api/v1/document-requirements/{requirement_id}/activate": ADMIN_ONLY,
    "POST /api/v1/document-requirements/{requirement_id}/deactivate": ADMIN_ONLY,
    "POST /api/v1/document-requirements/preview": ADMIN_ADVISOR,
    # --- /document-slots ---
    "GET /api/v1/document-slots/{slot_id}": ASSIGNED,
    "PATCH /api/v1/document-slots/{slot_id}/review": ASSIGNED,
    "GET /api/v1/document-slots/{slot_id}/versions": ASSIGNED,
    # --- /document-types ---
    "GET /api/v1/document-types": ADMIN_ADVISOR,
    "POST /api/v1/document-types": ADMIN_ONLY,
    "GET /api/v1/document-types/{document_type_id}": ADMIN_ADVISOR,
    "PATCH /api/v1/document-types/{document_type_id}": ADMIN_ONLY,
    "POST /api/v1/document-types/{document_type_id}/activate": ADMIN_ONLY,
    "POST /api/v1/document-types/{document_type_id}/deactivate": ADMIN_ONLY,
    # --- /filing-responses ---
    "GET /api/v1/filing-responses/{response_id}": ASSIGNED_OR_ORIGINATED,
    "POST /api/v1/filing-responses/{response_id}/evidence": ASSIGNED,
    "GET /api/v1/filing-responses/{response_id}/evidence/download": ORIGINATED_NO_FILES,
    # --- /filings ---
    "GET /api/v1/filings/{filing_id}": ASSIGNED_OR_ORIGINATED,
    "PATCH /api/v1/filings/{filing_id}": ASSIGNED,
    "GET /api/v1/filings/{filing_id}/document-snapshots": ORIGINATED_NO_FILES,
    "GET /api/v1/filings/{filing_id}/responses": ASSIGNED_OR_ORIGINATED,
    "POST /api/v1/filings/{filing_id}/responses": ASSIGNED,
    # --- /financial-profiles ---
    "GET /api/v1/financial-profiles/{profile_id}/income-sources": ASSIGNED,
    "POST /api/v1/financial-profiles/{profile_id}/income-sources": ASSIGNED,
    # --- /income-sources ---
    "PATCH /api/v1/income-sources/{income_source_id}": ASSIGNED,
    "DELETE /api/v1/income-sources/{income_source_id}": ASSIGNED,
    # --- /invitations ---
    "GET /api/v1/invitations": ADMIN_ONLY,
    "POST /api/v1/invitations": ADMIN_ONLY,
    "DELETE /api/v1/invitations/{invitation_id}": ADMIN_ONLY,
    "POST /api/v1/invitations/{invitation_id}/resend": ADMIN_ONLY,
    "POST /api/v1/invitations/accept": PUBLIC,
    # --- /me ---
    "GET /api/v1/me/commissions": OWN_COMMISSIONS,
    # --- /metadata ---
    "GET /api/v1/metadata/bootstrap": ANY_INTERNAL,
    "GET /api/v1/metadata/catalogs/{catalog_code}": ANY_INTERNAL,
    # --- /opportunities ---
    "GET /api/v1/opportunities": INTERNAL_NO_PARTNER,
    "POST /api/v1/opportunities": INTERNAL_NO_PARTNER,
    "GET /api/v1/opportunities/{opportunity_id}": ASSIGNED_OR_ORIGINATED,
    "PATCH /api/v1/opportunities/{opportunity_id}": ASSIGNED_OR_ORIGINATED,
    "POST /api/v1/opportunities/{opportunity_id}/assignments": ASSIGNED,
    "POST /api/v1/opportunities/{opportunity_id}/transitions": ASSIGNED,
    # --- /partner-memberships ---
    "GET /api/v1/partner-memberships/{membership_id}": ADMIN_PARTNER,
    "PATCH /api/v1/partner-memberships/{membership_id}": ADMIN_ONLY,
    "DELETE /api/v1/partner-memberships/{membership_id}": ADMIN_ONLY,
    # --- /partners ---
    "GET /api/v1/partners": ADMIN_ADVISOR_PARTNER,
    "POST /api/v1/partners": ADMIN_ONLY,
    "GET /api/v1/partners/{partner_id}": ADMIN_ADVISOR_PARTNER,
    "PATCH /api/v1/partners/{partner_id}": ADMIN_ONLY,
    "POST /api/v1/partners/{partner_id}/activate": ADMIN_ONLY,
    "POST /api/v1/partners/{partner_id}/deactivate": ADMIN_ONLY,
    "GET /api/v1/partners/{partner_id}/members": ADMIN_PARTNER,
    "POST /api/v1/partners/{partner_id}/members": ADMIN_ONLY,
    # --- /projects ---
    "GET /api/v1/projects": ANY_INTERNAL,
    "POST /api/v1/projects": ADMIN_ADVISOR_PARTNER,
    "GET /api/v1/projects/{project_id}": ANY_INTERNAL,
    "PATCH /api/v1/projects/{project_id}": ADMIN_ADVISOR_PARTNER,
    "POST /api/v1/projects/{project_id}/activate": ADMIN_ADVISOR,
    "POST /api/v1/projects/{project_id}/archive": ADMIN_ONLY,
    "POST /api/v1/projects/{project_id}/reject": ADMIN_ADVISOR,
    "POST /api/v1/projects/{project_id}/submit": ADMIN_ADVISOR_PARTNER,
    # --- /report-export-jobs ---
    "GET /api/v1/report-export-jobs/{job_id}": ASSIGNED,
    "GET /api/v1/report-export-jobs/{job_id}/download": ASSIGNED,
    # --- /reports ---
    "GET /api/v1/reports/applications": ADMIN_ADVISOR,
    "GET /api/v1/reports/applications.csv": ADMIN_ADVISOR,
    "GET /api/v1/reports/applications/export-jobs": ADMIN_ADVISOR,
    "POST /api/v1/reports/applications/export-jobs": ADMIN_ADVISOR,
    "GET /api/v1/reports/funnel": ADMIN_ADVISOR,
    # --- /roles ---
    "GET /api/v1/roles": ADMIN_ONLY,
    # --- /tasks ---
    "GET /api/v1/tasks": ADMIN_ADVISOR,
    "POST /api/v1/tasks": ADMIN_ADVISOR,
    "GET /api/v1/tasks/{task_id}": ASSIGNED,
    "PATCH /api/v1/tasks/{task_id}": ASSIGNED,
    "POST /api/v1/tasks/{task_id}/cancel": ASSIGNED,
    "POST /api/v1/tasks/{task_id}/complete": ASSIGNED,
    # --- /users ---
    "GET /api/v1/users": ADMIN_ONLY,
    "POST /api/v1/users": ADMIN_ONLY,
    "GET /api/v1/users/{user_id}": ADMIN_ONLY,
    "PATCH /api/v1/users/{user_id}": ADMIN_ONLY,
    "POST /api/v1/users/{user_id}/activate": ADMIN_ONLY,
    "POST /api/v1/users/{user_id}/deactivate": ADMIN_ONLY,
    "PUT /api/v1/users/{user_id}/roles": ADMIN_ONLY,
    # --- /workday ---
    "GET /api/v1/workday/applications": ADMIN_ADVISOR,
    "GET /api/v1/workday/summary": ADMIN_ADVISOR,
    # --- /workflow-transitions ---
    "GET /api/v1/workflow-transitions": ADMIN_ONLY,
    "POST /api/v1/workflow-transitions": ADMIN_ONLY,
    "GET /api/v1/workflow-transitions/{transition_id}": ADMIN_ONLY,
    "PATCH /api/v1/workflow-transitions/{transition_id}": ADMIN_ONLY,
    "POST /api/v1/workflow-transitions/{transition_id}/activate": ADMIN_ONLY,
    "POST /api/v1/workflow-transitions/{transition_id}/deactivate": ADMIN_ONLY,
}

# Casos que la documentación no define y se decidieron con la regla general (o con una
# decisión ya tomada en el proyecto). Clave: operación; valor: el porqué.
GENERAL_RULE_DECISIONS: dict[str, str] = {
    "POST /api/v1/auth/logout": (
        "Público y sin cookie de acceso: responde 204 a cualquiera (cierra lo que traiga la "
        "cookie de refresh, si hay)."
    ),
    "POST /api/v1/buyer/session/logout": "Mismo criterio que el logout interno.",
    "DELETE /api/v1/buyer-access-links/{link_id}": (
        "API §25: el broker 'revoca los propios'. El enlace del lado A lo emitió la asesora: "
        "el broker originador lo ve en el listado, así que 403 (no 404)."
    ),
    "GET /api/v1/filing-responses/{response_id}/evidence/download": (
        "El broker tiene `filings.read`, pero REQ §3: 'no ve archivos'. 403 al originador; "
        "404 al otro broker, porque la radicación está fuera de su alcance."
    ),
    "GET /api/v1/filings/{filing_id}/document-snapshots": "Igual que la evidencia: son archivos.",
    "PATCH /api/v1/projects/{project_id}": (
        "API §25 dice 'lectura relacionada' para el asesor, pero API §12 (`projects.update`), "
        "los permisos sembrados, RF-17 (asesor o administrador aprueban) y `update_project` "
        "(el asesor corrige cualquier proyecto no archivado) lo permiten. Se toma §12."
    ),
    "GET /api/v1/clients/{client_id}/addresses": (
        "API §25 'Clientes: Propios' para el broker no detalla direcciones; la vista exige "
        "un permiso que el broker no tiene (403). Más restrictivo que la matriz: no es brecha."
    ),
    "GET /api/v1/me/commissions": (
        "El administrador no tiene `commissions.read_own` (no tiene 'su parte'): 403. Consulta "
        "las liquidaciones en `/commission-settlements`."
    ),
    "POST /api/v1/auth/change-password": (
        "Solo pide sesión interna; el cuerpo vacío da 400 a los cuatro roles."
    ),
}

# Casos de la matriz que hoy fallan (brecha real): operación -> {actor: "SEC-NN"}. La
# prueba los marca `xfail(strict=True)`; cuando la Fase B corrija, el xfail obliga a
# quitar la entrada.
KNOWN_GAPS: dict[str, dict[str, str]] = {}

# Campos que el broker y el comprador nunca deben recibir en sus respuestas `ALLOW`
# (spec §3.3; REQ §3: el broker "no ve archivos ni datos financieros detallados"; las
# notas y comentarios internos son del backoffice).
FINANCIAL_FIELDS = frozenset(
    {
        "monthly_income_cop",
        "monthly_expenses_cop",
        "assets_cop",
        "liabilities_cop",
        "income_sources_total_cop",
        "monthly_amount_cop",
        "income_share_cop",
        "requested_amount_cop",
        "own_resources_cop",
        "severance_funds_cop",
        "estimated_value_cop",
        "external_approved_amount_cop",
        "approved_amount_cop",
        "approved_term_months",
        "disbursed_amount_cop",
    }
)
FILE_FIELDS = frozenset(
    {
        "url",
        "download_url",
        "storage_key",
        "sha256",
        "current_file",
        "client_filename",
        "evidence",
        "evidence_file",
        "package_job_id",
    }
)
INTERNAL_FIELDS = frozenset({"internal_comment", "internal_notes", "notes", "body"})
FORBIDDEN_FIELDS_BY_ACTOR: dict[str, frozenset[str]] = {
    "broker_owner": FINANCIAL_FIELDS | FILE_FIELDS | INTERNAL_FIELDS,
    "broker_other": FINANCIAL_FIELDS | FILE_FIELDS | INTERNAL_FIELDS,
    # El comprador sí ve sus montos y sus archivos; nunca lo interno del backoffice, ni
    # claves de almacenamiento, ni el detalle de las reglas del banco (API §25: solo
    # `eligible`).
    "buyer_owner": INTERNAL_FIELDS | {"storage_key", "sha256", "rule_results", "outcome"},
    "buyer_other": INTERNAL_FIELDS | {"storage_key", "sha256", "rule_results", "outcome"},
}
# Respuestas donde un campo de la lista es legítimo para ese actor.
FIELD_EXCEPTIONS: dict[str, frozenset[str]] = {
    # El broker crea el enlace y lo comparte (API §27.1, paso 6): la respuesta trae `url`.
    "POST /api/v1/applications/{application_id}/buyer-access-links": frozenset({"url"}),
    # La radicación que ve el broker trae el id del paquete, no el paquete ni sus archivos.
    "GET /api/v1/applications/{application_id}/filings": frozenset({"package_job_id"}),
    "GET /api/v1/filings/{filing_id}": frozenset({"package_job_id"}),
    # Consentimientos: `body` es el texto legal que el comprador acepta.
    "GET /api/v1/buyer/applications/{application_id}/consents": frozenset({"body"}),
}
# El broker ve el documento del cliente enmascarado (`••••••1234`), nunca completo.
MASKED_FIELDS_BY_ACTOR: dict[str, frozenset[str]] = {
    "broker_owner": frozenset({"document_number", "client_document_number"}),
    "broker_other": frozenset({"document_number", "client_document_number"}),
}
MASK_PREFIX = "•"

# Lo único que el broker originador recibe en el detalle de la solicitud (spec §3.4: "solo
# el resumen permitido"): el mismo resumen del listado.
BROKER_APPLICATION_SUMMARY_FIELDS = frozenset(
    {
        "id",
        "code",
        "status",
        "status_label",
        "opportunity_id",
        "purpose",
        "client_name",
        "client_document_number",
        "bank_name",
        "product_name",
        "advisor_name",
        "current_stage_started_at",
        "days_in_stage",
        "created_at",
        "updated_at",
    }
)


def expected(operation: str, actor: str) -> str:
    """Resultado esperado (``ALLOW``, ``DENY_401``, ``DENY_403``, ``HIDE_404``)."""
    return LETTERS[MATRIX[operation][ACTORS.index(actor)]]


def status_matches(result: str, status_code: int) -> bool:
    if result == ALLOW:
        return 200 <= status_code < 300 or status_code in ALLOW_STATUSES
    return status_code == STATUS_FOR[result]
