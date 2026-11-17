"""Catálogo único de las acciones auditadas (API §24.1). La etiqueta es la que ve el
administrador en ``/audit-events``."""

from django.db import models


class AuditAction(models.TextChoices):
    # Autenticación interna.
    AUTH_LOGIN = "AUTH_LOGIN", "Inicio de sesión"
    AUTH_LOGIN_FAILED = "AUTH_LOGIN_FAILED", "Inicio de sesión fallido"
    AUTH_LOGOUT = "AUTH_LOGOUT", "Cierre de sesión"
    AUTH_REFRESH_REJECTED = "AUTH_REFRESH_REJECTED", "Renovación de sesión rechazada"
    AUTH_PASSWORD_RESET_REQUESTED = (
        "AUTH_PASSWORD_RESET_REQUESTED",
        "Restablecimiento de contraseña solicitado",
    )
    AUTH_PASSWORD_RESET_COMPLETED = (
        "AUTH_PASSWORD_RESET_COMPLETED",
        "Contraseña restablecida",
    )
    AUTH_RATE_LIMITED = "AUTH_RATE_LIMITED", "Bloqueo por límite de consumo"
    # Comprador.
    BUYER_LINK_CREATED = "BUYER_LINK_CREATED", "Enlace de acceso creado"
    BUYER_LINK_CONSUMED = "BUYER_LINK_CONSUMED", "Enlace de acceso usado"
    BUYER_LINK_FAILED = "BUYER_LINK_FAILED", "Enlace de acceso rechazado"
    BUYER_SESSION_CLOSED = "BUYER_SESSION_CLOSED", "Sesión del comprador cerrada"
    CONSENT_ACCEPTED = "CONSENT_ACCEPTED", "Consentimiento aceptado"
    CONSENT_WITHDRAWN = "CONSENT_WITHDRAWN", "Consentimiento retirado"
    # Archivos.
    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED", "Documento cargado"
    DOCUMENT_DOWNLOADED = "DOCUMENT_DOWNLOADED", "Documento descargado"
    PACKAGE_DOWNLOADED = "PACKAGE_DOWNLOADED", "Paquete descargado"
    EVIDENCE_DOWNLOADED = "EVIDENCE_DOWNLOADED", "Evidencia descargada"
    # Expediente.
    APPLICATION_STATUS_CHANGED = "APPLICATION_STATUS_CHANGED", "Cambio de estado"
    APPLICATION_WITHDRAWN = "APPLICATION_WITHDRAWN", "Desistimiento"
    APPLICATION_ASSIGNED = "APPLICATION_ASSIGNED", "Reasignación"
    DOCUMENT_REVIEWED = "DOCUMENT_REVIEWED", "Revisión de documento"
    DOCUMENT_WAIVED = "DOCUMENT_WAIVED", "Exoneración de documento"
    DOCUMENT_WAIVER_REOPENED = "DOCUMENT_WAIVER_REOPENED", "Reapertura de exoneración"
    # Radicación.
    FILING_CREATED = "FILING_CREATED", "Radicación creada"
    FILING_UPDATED = "FILING_UPDATED", "Radicación corregida"
    BANK_RESPONSE_RECORDED = "BANK_RESPONSE_RECORDED", "Respuesta del banco registrada"
    # Configuración.
    CATALOG_CHANGED = "CATALOG_CHANGED", "Cambio de catálogo"
    BANK_CHANGED = "BANK_CHANGED", "Cambio de banco"
    BANK_PRODUCT_CHANGED = "BANK_PRODUCT_CHANGED", "Cambio de producto bancario"
    BANK_RULE_CHANGED = "BANK_RULE_CHANGED", "Cambio de regla bancaria"
    DOCUMENT_TYPE_CHANGED = "DOCUMENT_TYPE_CHANGED", "Cambio de tipo documental"
    DOCUMENT_REQUIREMENT_CHANGED = (
        "DOCUMENT_REQUIREMENT_CHANGED",
        "Cambio de requisito documental",
    )
    WORKFLOW_TRANSITION_CHANGED = "WORKFLOW_TRANSITION_CHANGED", "Cambio de transición"
    USER_CHANGED = "USER_CHANGED", "Cambio de usuario"
    USER_ROLES_CHANGED = "USER_ROLES_CHANGED", "Cambio de roles"
    USER_STATUS_CHANGED = "USER_STATUS_CHANGED", "Cambio de estado de usuario"
    # Acceso.
    ACCESS_DENIED = "ACCESS_DENIED", "Acceso denegado"


class AuditResult(models.TextChoices):
    SUCCESS = "SUCCESS", "Correcto"
    DENIED = "DENIED", "Denegado"
    FAILED = "FAILED", "Fallido"
