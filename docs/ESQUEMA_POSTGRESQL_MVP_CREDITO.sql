-- Esquema PostgreSQL del MVP de gestión de crédito de vivienda
-- PostgreSQL 16+
-- 55 tablas persistentes. No incluye tablas internas de Django.
-- Ejecutar sobre una base de datos vacía.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;

-- ================================================================
-- 1. IDENTIDAD, ROLES Y SEGURIDAD INTERNA
-- ================================================================

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    email CITEXT NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    phone VARCHAR(20),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ
);

CREATE TABLE roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    code VARCHAR(100) NOT NULL UNIQUE,
    module VARCHAR(50) NOT NULL,
    name VARCHAR(120) NOT NULL,
    description TEXT
);

CREATE TABLE user_roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
    assigned_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT uq_user_roles_user_role UNIQUE (user_id, role_id)
);

CREATE TABLE role_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id UUID NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    CONSTRAINT uq_role_permissions_role_permission UNIQUE (role_id, permission_id)
);

CREATE TABLE auth_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    refresh_token_hash CHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    rotated_from_id UUID UNIQUE REFERENCES auth_sessions(id) ON DELETE SET NULL,
    ip_address INET,
    user_agent_summary VARCHAR(255),
    CONSTRAINT ck_auth_sessions_expiry CHECK (expires_at > created_at)
);

CREATE TABLE password_reset_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash CHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    requested_ip INET,
    CONSTRAINT ck_password_reset_expiry CHECK (expires_at > created_at)
);

-- ================================================================
-- 2. CATÁLOGOS GENERALES
-- ================================================================

CREATE TABLE catalogs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(120) NOT NULL,
    description TEXT,
    is_manageable BOOLEAN NOT NULL DEFAULT TRUE,
    is_public BOOLEAN NOT NULL DEFAULT FALSE,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0)
);

CREATE TABLE catalog_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    catalog_id UUID NOT NULL REFERENCES catalogs(id) ON DELETE RESTRICT,
    code VARCHAR(50) NOT NULL,
    label VARCHAR(180) NOT NULL,
    description TEXT,
    parent_item_id UUID REFERENCES catalog_items(id) ON DELETE RESTRICT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    valid_from DATE,
    valid_to DATE,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    CONSTRAINT uq_catalog_items_catalog_code UNIQUE (catalog_id, code),
    CONSTRAINT ck_catalog_items_validity CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from),
    CONSTRAINT ck_catalog_items_not_own_parent CHECK (parent_item_id IS NULL OR parent_item_id <> id)
);

-- ================================================================
-- 3. PARTNERS, PROYECTOS Y CLIENTES
-- ================================================================

CREATE TABLE partners (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    legal_name VARCHAR(180) NOT NULL,
    trade_name VARCHAR(180),
    tax_id VARCHAR(30) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    contact_name VARCHAR(150),
    contact_email CITEXT,
    contact_phone VARCHAR(20),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT ck_partners_status CHECK (status IN ('ACTIVE', 'INACTIVE'))
);

CREATE TABLE internal_invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    email CITEXT NOT NULL,
    token_hash CHAR(64) NOT NULL UNIQUE,
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
    partner_id UUID REFERENCES partners(id) ON DELETE RESTRICT,
    invited_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    CONSTRAINT ck_internal_invitations_expiry CHECK (expires_at > created_at),
    CONSTRAINT ck_internal_invitations_terminal CHECK (consumed_at IS NULL OR revoked_at IS NULL)
);

CREATE TABLE partner_memberships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    partner_id UUID NOT NULL REFERENCES partners(id) ON DELETE RESTRICT,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    job_title VARCHAR(120),
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    started_at DATE NOT NULL,
    ended_at DATE,
    CONSTRAINT uq_partner_memberships_partner_user_start UNIQUE (partner_id, user_id, started_at),
    CONSTRAINT ck_partner_memberships_status CHECK (status IN ('ACTIVE', 'INACTIVE')),
    CONSTRAINT ck_partner_memberships_dates CHECK (ended_at IS NULL OR ended_at >= started_at)
);

CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    partner_id UUID NOT NULL REFERENCES partners(id) ON DELETE RESTRICT,
    name VARCHAR(180) NOT NULL,
    code VARCHAR(50),
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    city_item_id UUID NOT NULL REFERENCES catalog_items(id) ON DELETE RESTRICT,
    address VARCHAR(255) NOT NULL,
    description TEXT,
    estimated_delivery_date DATE,
    created_by_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    validated_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
    validated_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    CONSTRAINT uq_projects_partner_code UNIQUE (partner_id, code),
    CONSTRAINT ck_projects_status CHECK (status IN ('DRAFT', 'PENDING_REVIEW', 'ACTIVE', 'ARCHIVED')),
    CONSTRAINT ck_projects_validation CHECK ((validated_by_id IS NULL) = (validated_at IS NULL))
);

CREATE TABLE clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    document_type_item_id UUID NOT NULL REFERENCES catalog_items(id) ON DELETE RESTRICT,
    document_number VARCHAR(30) NOT NULL,
    first_names VARCHAR(120) NOT NULL,
    last_names VARCHAR(120) NOT NULL,
    birth_date DATE,
    email CITEXT,
    phone VARCHAR(20),
    origin_item_id UUID REFERENCES catalog_items(id) ON DELETE RESTRICT,
    created_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
    deleted_at TIMESTAMPTZ,
    CONSTRAINT uq_clients_document UNIQUE (document_type_item_id, document_number)
);

CREATE TABLE client_addresses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    address_type_item_id UUID NOT NULL REFERENCES catalog_items(id) ON DELETE RESTRICT,
    city_item_id UUID NOT NULL REFERENCES catalog_items(id) ON DELETE RESTRICT,
    line1 VARCHAR(255) NOT NULL,
    line2 VARCHAR(120),
    postal_code VARCHAR(12),
    is_primary BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE opportunities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    project_id UUID REFERENCES projects(id) ON DELETE RESTRICT,
    origin_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    assigned_advisor_id UUID REFERENCES users(id) ON DELETE SET NULL,
    origin_item_id UUID NOT NULL REFERENCES catalog_items(id) ON DELETE RESTRICT,
    status VARCHAR(30) NOT NULL DEFAULT 'NEW',
    converted_at TIMESTAMPTZ,
    lost_reason_item_id UUID REFERENCES catalog_items(id) ON DELETE RESTRICT,
    CONSTRAINT ck_opportunities_status CHECK (status IN ('NEW', 'ASSIGNED', 'CONTACTED', 'IN_PROGRESS', 'CONVERTED', 'LOST', 'CANCELLED')),
    CONSTRAINT ck_opportunities_lost_reason CHECK (status = 'LOST' OR lost_reason_item_id IS NULL)
);

CREATE TABLE opportunity_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    opportunity_id UUID NOT NULL REFERENCES opportunities(id) ON DELETE RESTRICT,
    advisor_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    assigned_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
    ended_at TIMESTAMPTZ,
    reason VARCHAR(255),
    CONSTRAINT ck_opportunity_assignments_dates CHECK (ended_at IS NULL OR ended_at >= created_at)
);

-- ================================================================
-- 4. BANCOS, PRODUCTOS, FLUJOS Y REQUISITOS
-- ================================================================

CREATE TABLE banks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(180) NOT NULL,
    tax_id VARCHAR(30),
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    operational_notes TEXT,
    CONSTRAINT ck_banks_status CHECK (status IN ('ACTIVE', 'INACTIVE'))
);

CREATE TABLE bank_products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    bank_id UUID NOT NULL REFERENCES banks(id) ON DELETE RESTRICT,
    code VARCHAR(50) NOT NULL,
    name VARCHAR(180) NOT NULL,
    product_type_item_id UUID NOT NULL REFERENCES catalog_items(id) ON DELETE RESTRICT,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    min_amount_cop BIGINT,
    max_amount_cop BIGINT,
    min_term_months SMALLINT,
    max_term_months SMALLINT,
    valid_from DATE NOT NULL,
    valid_to DATE,
    CONSTRAINT uq_bank_products_bank_code UNIQUE (bank_id, code),
    CONSTRAINT ck_bank_products_status CHECK (status IN ('ACTIVE', 'INACTIVE')),
    CONSTRAINT ck_bank_products_amounts CHECK (
        (min_amount_cop IS NULL OR min_amount_cop >= 0) AND
        (max_amount_cop IS NULL OR max_amount_cop >= 0) AND
        (min_amount_cop IS NULL OR max_amount_cop IS NULL OR max_amount_cop >= min_amount_cop)
    ),
    CONSTRAINT ck_bank_products_terms CHECK (
        (min_term_months IS NULL OR min_term_months > 0) AND
        (max_term_months IS NULL OR max_term_months > 0) AND
        (min_term_months IS NULL OR max_term_months IS NULL OR max_term_months >= min_term_months)
    ),
    CONSTRAINT ck_bank_products_validity CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE TABLE bank_product_purposes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    bank_product_id UUID NOT NULL REFERENCES bank_products(id) ON DELETE CASCADE,
    purpose_item_id UUID NOT NULL REFERENCES catalog_items(id) ON DELETE RESTRICT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT uq_bank_product_purposes_product_purpose UNIQUE (bank_product_id, purpose_item_id)
);

CREATE TABLE bank_policy_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    bank_product_id UUID NOT NULL REFERENCES bank_products(id) ON DELETE RESTRICT,
    purpose_item_id UUID REFERENCES catalog_items(id) ON DELETE RESTRICT,
    code VARCHAR(80) NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    severity VARCHAR(20) NOT NULL,
    condition JSONB NOT NULL,
    message TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    created_by_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    CONSTRAINT uq_bank_policy_rules_version UNIQUE (bank_product_id, code, version),
    CONSTRAINT ck_bank_policy_rules_severity CHECK (severity IN ('WARNING', 'BLOCKING')),
    CONSTRAINT ck_bank_policy_rules_status CHECK (status IN ('DRAFT', 'ACTIVE', 'INACTIVE')),
    CONSTRAINT ck_bank_policy_rules_validity CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE TABLE workflow_transitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    flow_type VARCHAR(30) NOT NULL,
    code VARCHAR(80) NOT NULL,
    from_status VARCHAR(40) NOT NULL,
    to_status VARCHAR(40) NOT NULL,
    label VARCHAR(120) NOT NULL,
    required_permission_id UUID REFERENCES permissions(id) ON DELETE RESTRICT,
    guard_code VARCHAR(80),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT uq_workflow_transitions_flow_code UNIQUE (flow_type, code),
    CONSTRAINT ck_workflow_transitions_flow CHECK (flow_type IN ('OPPORTUNITY', 'APPLICATION', 'PROJECT')),
    CONSTRAINT ck_workflow_transitions_states CHECK (from_status <> to_status)
);

CREATE TABLE workflow_transition_roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    transition_id UUID NOT NULL REFERENCES workflow_transitions(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    CONSTRAINT uq_workflow_transition_roles UNIQUE (transition_id, role_id)
);

CREATE TABLE document_types (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    code VARCHAR(80) NOT NULL UNIQUE,
    name VARCHAR(180) NOT NULL,
    description TEXT,
    allowed_mime_types TEXT[] NOT NULL,
    max_size_bytes BIGINT NOT NULL CHECK (max_size_bytes > 0),
    default_validity_days SMALLINT CHECK (default_validity_days IS NULL OR default_validity_days > 0),
    is_repeatable BOOLEAN NOT NULL DEFAULT FALSE,
    -- Desvío del DER original (paso 10): a quién pertenece el documento.
    -- PARTICIPANT se pide a cada participante; APPLICATION, una sola vez por solicitud.
    holder_scope VARCHAR(20) NOT NULL DEFAULT 'PARTICIPANT',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT ck_document_types_holder_scope CHECK (holder_scope IN ('PARTICIPANT', 'APPLICATION'))
);

CREATE TABLE document_requirements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    bank_product_id UUID REFERENCES bank_products(id) ON DELETE RESTRICT,
    document_type_id UUID NOT NULL REFERENCES document_types(id) ON DELETE RESTRICT,
    purpose_item_id UUID REFERENCES catalog_items(id) ON DELETE RESTRICT,
    employment_profile_item_id UUID REFERENCES catalog_items(id) ON DELETE RESTRICT,
    participant_role VARCHAR(30),
    property_condition_item_id UUID REFERENCES catalog_items(id) ON DELETE RESTRICT,
    version INTEGER NOT NULL CHECK (version > 0),
    is_required BOOLEAN NOT NULL DEFAULT TRUE,
    is_waivable BOOLEAN NOT NULL DEFAULT FALSE,
    minimum_files SMALLINT NOT NULL DEFAULT 1 CHECK (minimum_files > 0),
    alternative_group_code VARCHAR(50),
    validity_days SMALLINT CHECK (validity_days IS NULL OR validity_days > 0),
    sort_order INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    CONSTRAINT ck_document_requirements_role CHECK (participant_role IS NULL OR participant_role IN ('PRIMARY', 'CO_APPLICANT', 'SOLIDARY_DEBTOR')),
    CONSTRAINT ck_document_requirements_status CHECK (status IN ('DRAFT', 'ACTIVE', 'INACTIVE')),
    CONSTRAINT ck_document_requirements_validity CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE TABLE consent_definitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    code VARCHAR(50) NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    title VARCHAR(180) NOT NULL,
    body TEXT NOT NULL,
    content_hash CHAR(64) NOT NULL,
    effective_from TIMESTAMPTZ NOT NULL,
    retired_at TIMESTAMPTZ,
    CONSTRAINT uq_consent_definitions_version UNIQUE (code, version),
    CONSTRAINT ck_consent_definitions_dates CHECK (retired_at IS NULL OR retired_at >= effective_from)
);

-- ================================================================
-- 5. SOLICITUD DE CRÉDITO Y PERFIL FINANCIERO
-- ================================================================

CREATE TABLE credit_applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    code VARCHAR(30) NOT NULL UNIQUE,
    opportunity_id UUID NOT NULL REFERENCES opportunities(id) ON DELETE RESTRICT,
    purpose_item_id UUID NOT NULL REFERENCES catalog_items(id) ON DELETE RESTRICT,
    bank_product_id UUID REFERENCES bank_products(id) ON DELETE RESTRICT,
    assigned_advisor_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    status VARCHAR(40) NOT NULL DEFAULT 'DRAFT',
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    current_stage_started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ready_to_file_at TIMESTAMPTZ,
    withdrawn_at TIMESTAMPTZ,
    withdrawal_reason_item_id UUID REFERENCES catalog_items(id) ON DELETE RESTRICT,
    closed_at TIMESTAMPTZ,
    CONSTRAINT ck_credit_applications_withdrawal CHECK (
        (withdrawn_at IS NULL AND withdrawal_reason_item_id IS NULL) OR
        (withdrawn_at IS NOT NULL AND withdrawal_reason_item_id IS NOT NULL)
    )
);

CREATE TABLE application_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    application_id UUID NOT NULL REFERENCES credit_applications(id) ON DELETE RESTRICT,
    advisor_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    assigned_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
    ended_at TIMESTAMPTZ,
    reason VARCHAR(255),
    CONSTRAINT ck_application_assignments_dates CHECK (ended_at IS NULL OR ended_at >= created_at)
);

CREATE TABLE application_participants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    application_id UUID NOT NULL REFERENCES credit_applications(id) ON DELETE RESTRICT,
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    role VARCHAR(30) NOT NULL,
    contributes_income BOOLEAN NOT NULL DEFAULT TRUE,
    income_share_cop BIGINT CHECK (income_share_cop IS NULL OR income_share_cop >= 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT uq_application_participants_client UNIQUE (application_id, client_id),
    CONSTRAINT ck_application_participants_role CHECK (role IN ('PRIMARY', 'CO_APPLICANT', 'SOLIDARY_DEBTOR'))
);

CREATE TABLE financial_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    participant_id UUID NOT NULL UNIQUE REFERENCES application_participants(id) ON DELETE CASCADE,
    employment_profile_item_id UUID NOT NULL REFERENCES catalog_items(id) ON DELETE RESTRICT,
    contract_type_item_id UUID REFERENCES catalog_items(id) ON DELETE RESTRICT,
    employer_name VARCHAR(180),
    job_title VARCHAR(120),
    employment_start_date DATE,
    monthly_income_cop BIGINT NOT NULL DEFAULT 0 CHECK (monthly_income_cop >= 0),
    monthly_expenses_cop BIGINT NOT NULL DEFAULT 0 CHECK (monthly_expenses_cop >= 0),
    assets_cop BIGINT NOT NULL DEFAULT 0 CHECK (assets_cop >= 0),
    liabilities_cop BIGINT NOT NULL DEFAULT 0 CHECK (liabilities_cop >= 0),
    funds_origin_item_id UUID REFERENCES catalog_items(id) ON DELETE RESTRICT,
    data_confirmed_at TIMESTAMPTZ
);

CREATE TABLE income_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    financial_profile_id UUID NOT NULL REFERENCES financial_profiles(id) ON DELETE CASCADE,
    source_type_item_id UUID NOT NULL REFERENCES catalog_items(id) ON DELETE RESTRICT,
    payer_name VARCHAR(180),
    monthly_amount_cop BIGINT NOT NULL CHECK (monthly_amount_cop >= 0),
    start_date DATE,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    notes TEXT
);

CREATE TABLE properties (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    application_id UUID NOT NULL UNIQUE REFERENCES credit_applications(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(id) ON DELETE RESTRICT,
    property_type_item_id UUID NOT NULL REFERENCES catalog_items(id) ON DELETE RESTRICT,
    condition_item_id UUID NOT NULL REFERENCES catalog_items(id) ON DELETE RESTRICT,
    city_item_id UUID NOT NULL REFERENCES catalog_items(id) ON DELETE RESTRICT,
    address VARCHAR(255),
    unit_reference VARCHAR(100),
    estimated_value_cop BIGINT NOT NULL CHECK (estimated_value_cop >= 0),
    is_owned_by_applicant BOOLEAN,
    ownership_notes TEXT
);

CREATE TABLE financing_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    application_id UUID NOT NULL UNIQUE REFERENCES credit_applications(id) ON DELETE CASCADE,
    financing_mode_item_id UUID NOT NULL REFERENCES catalog_items(id) ON DELETE RESTRICT,
    requested_amount_cop BIGINT NOT NULL CHECK (requested_amount_cop >= 0),
    term_months SMALLINT CHECK (term_months IS NULL OR term_months > 0),
    currency_mode_item_id UUID REFERENCES catalog_items(id) ON DELETE RESTRICT,
    amortization_mode_item_id UUID REFERENCES catalog_items(id) ON DELETE RESTRICT,
    own_resources_cop BIGINT NOT NULL DEFAULT 0 CHECK (own_resources_cop >= 0),
    uses_severance_funds BOOLEAN NOT NULL DEFAULT FALSE,
    severance_funds_cop BIGINT NOT NULL DEFAULT 0 CHECK (severance_funds_cop >= 0),
    external_approved_amount_cop BIGINT CHECK (external_approved_amount_cop IS NULL OR external_approved_amount_cop >= 0),
    CONSTRAINT ck_financing_severance CHECK (uses_severance_funds OR severance_funds_cop = 0)
);

CREATE TABLE bank_rule_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    application_id UUID NOT NULL REFERENCES credit_applications(id) ON DELETE RESTRICT,
    bank_product_id UUID NOT NULL REFERENCES bank_products(id) ON DELETE RESTRICT,
    application_version INTEGER NOT NULL CHECK (application_version > 0),
    is_eligible BOOLEAN NOT NULL,
    blocking_count SMALLINT NOT NULL DEFAULT 0 CHECK (blocking_count >= 0),
    warning_count SMALLINT NOT NULL DEFAULT 0 CHECK (warning_count >= 0),
    result_snapshot JSONB NOT NULL,
    evaluated_by_id UUID REFERENCES users(id) ON DELETE SET NULL
);

-- ================================================================
-- 6. ACCESO PASSWORDLESS, CONSENTIMIENTOS Y OPERACIÓN
-- ================================================================

CREATE TABLE buyer_access_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    application_id UUID NOT NULL REFERENCES credit_applications(id) ON DELETE RESTRICT,
    token_hash CHAR(64) NOT NULL UNIQUE,
    created_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
    delivery_channel_item_id UUID REFERENCES catalog_items(id) ON DELETE RESTRICT,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    CONSTRAINT ck_buyer_access_links_expiry CHECK (expires_at > created_at),
    CONSTRAINT ck_buyer_access_links_terminal CHECK (consumed_at IS NULL OR revoked_at IS NULL)
);

CREATE TABLE buyer_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    access_link_id UUID NOT NULL UNIQUE REFERENCES buyer_access_links(id) ON DELETE RESTRICT,
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    application_id UUID NOT NULL REFERENCES credit_applications(id) ON DELETE RESTRICT,
    session_token_hash CHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    last_seen_at TIMESTAMPTZ,
    ip_address INET,
    user_agent_summary VARCHAR(255),
    CONSTRAINT ck_buyer_sessions_expiry CHECK (expires_at > created_at)
);

CREATE TABLE consent_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    consent_definition_id UUID NOT NULL REFERENCES consent_definitions(id) ON DELETE RESTRICT,
    client_id UUID REFERENCES clients(id) ON DELETE RESTRICT,
    user_id UUID REFERENCES users(id) ON DELETE RESTRICT,
    application_id UUID REFERENCES credit_applications(id) ON DELETE RESTRICT,
    action VARCHAR(20) NOT NULL,
    ip_address INET,
    user_agent_summary VARCHAR(255),
    buyer_session_id UUID REFERENCES buyer_sessions(id) ON DELETE SET NULL,
    CONSTRAINT ck_consent_records_actor CHECK (num_nonnulls(client_id, user_id) = 1),
    CONSTRAINT ck_consent_records_action CHECK (action IN ('ACCEPTED', 'WITHDRAWN')),
    CONSTRAINT ck_consent_records_buyer_session CHECK (buyer_session_id IS NULL OR client_id IS NOT NULL)
);

CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    opportunity_id UUID REFERENCES opportunities(id) ON DELETE RESTRICT,
    application_id UUID REFERENCES credit_applications(id) ON DELETE RESTRICT,
    assigned_to_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
    title VARCHAR(180) NOT NULL,
    description TEXT,
    priority_item_id UUID NOT NULL REFERENCES catalog_items(id) ON DELETE RESTRICT,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    source VARCHAR(20) NOT NULL DEFAULT 'MANUAL',
    due_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    CONSTRAINT ck_tasks_parent CHECK (num_nonnulls(opportunity_id, application_id) >= 1),
    CONSTRAINT ck_tasks_status CHECK (status IN ('PENDING', 'COMPLETED', 'CANCELLED')),
    CONSTRAINT ck_tasks_source CHECK (source IN ('MANUAL', 'AUTOMATIC')),
    CONSTRAINT ck_tasks_completion CHECK ((status = 'COMPLETED') = (completed_at IS NOT NULL))
);

CREATE TABLE application_status_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    application_id UUID NOT NULL REFERENCES credit_applications(id) ON DELETE RESTRICT,
    from_status VARCHAR(40),
    to_status VARCHAR(40) NOT NULL,
    transition_id UUID REFERENCES workflow_transitions(id) ON DELETE RESTRICT,
    reason_item_id UUID REFERENCES catalog_items(id) ON DELETE RESTRICT,
    comment TEXT,
    actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    actor_buyer_session_id UUID REFERENCES buyer_sessions(id) ON DELETE SET NULL,
    application_version INTEGER NOT NULL CHECK (application_version > 0),
    CONSTRAINT ck_application_status_actor CHECK (num_nonnulls(actor_user_id, actor_buyer_session_id) <= 1),
    CONSTRAINT ck_application_status_change CHECK (from_status IS NULL OR from_status <> to_status)
);

-- ================================================================
-- 7. ARCHIVOS Y EXPEDIENTE DOCUMENTAL
-- ================================================================

CREATE TABLE file_objects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    storage_provider VARCHAR(30) NOT NULL,
    bucket_name VARCHAR(100) NOT NULL,
    object_key VARCHAR(500) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    detected_mime_type VARCHAR(120) NOT NULL,
    size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
    sha256 CHAR(64) NOT NULL,
    scan_status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    scanned_at TIMESTAMPTZ,
    encryption_key_version VARCHAR(50),
    CONSTRAINT uq_file_objects_storage_key UNIQUE (bucket_name, object_key),
    CONSTRAINT ck_file_objects_scan_status CHECK (scan_status IN ('PENDING', 'CLEAN', 'INFECTED', 'INVALID')),
    CONSTRAINT ck_file_objects_scan_date CHECK (
        (scan_status = 'PENDING' AND scanned_at IS NULL) OR
        (scan_status <> 'PENDING' AND scanned_at IS NOT NULL)
    )
);

CREATE TABLE application_document_slots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    application_id UUID NOT NULL REFERENCES credit_applications(id) ON DELETE RESTRICT,
    participant_id UUID REFERENCES application_participants(id) ON DELETE RESTRICT,
    document_type_id UUID NOT NULL REFERENCES document_types(id) ON DELETE RESTRICT,
    requirement_id UUID REFERENCES document_requirements(id) ON DELETE RESTRICT,
    requirement_version INTEGER CHECK (requirement_version IS NULL OR requirement_version > 0),
    is_required BOOLEAN NOT NULL,
    is_waivable BOOLEAN NOT NULL,
    minimum_files SMALLINT NOT NULL DEFAULT 1 CHECK (minimum_files > 0),
    alternative_group_code VARCHAR(50),
    validity_days SMALLINT CHECK (validity_days IS NULL OR validity_days > 0),
    -- Desvío del DER original (paso 10): un requisito con minimum_files = n crea n slots,
    -- uno por archivo (1..n), que se cargan y revisan por separado.
    slot_index SMALLINT NOT NULL DEFAULT 1,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    sort_order INTEGER NOT NULL DEFAULT 0,
    waiver_reason_item_id UUID REFERENCES catalog_items(id) ON DELETE RESTRICT,
    current_file_id UUID UNIQUE,
    locked_at TIMESTAMPTZ,
    -- Desvío del DER original (paso 10): el slot que deja de aplicar al recalcular la lista
    -- se retira sin borrarse; conserva sus versiones y revive si vuelve a aplicar.
    retired_at TIMESTAMPTZ,
    CONSTRAINT ck_document_slots_status CHECK (status IN ('PENDING', 'UPLOADED', 'APPROVED', 'REJECTED', 'WAIVED')),
    CONSTRAINT ck_document_slots_waiver CHECK (status <> 'WAIVED' OR (is_waivable AND waiver_reason_item_id IS NOT NULL)),
    CONSTRAINT ck_document_slots_index CHECK (slot_index > 0 AND slot_index <= minimum_files)
);

CREATE TABLE document_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    slot_id UUID NOT NULL REFERENCES application_document_slots(id) ON DELETE RESTRICT,
    file_object_id UUID NOT NULL UNIQUE REFERENCES file_objects(id) ON DELETE RESTRICT,
    version_number INTEGER NOT NULL CHECK (version_number > 0),
    uploaded_by_buyer_session_id UUID NOT NULL REFERENCES buyer_sessions(id) ON DELETE RESTRICT,
    client_filename VARCHAR(255) NOT NULL,
    document_date DATE,
    expires_at DATE,
    status VARCHAR(20) NOT NULL DEFAULT 'UPLOADED',
    CONSTRAINT uq_document_files_slot_version UNIQUE (slot_id, version_number),
    CONSTRAINT ck_document_files_status CHECK (status IN ('UPLOADED', 'IN_REVIEW', 'APPROVED', 'REJECTED')),
    -- Paso 10: la vigencia es document_date + validity_days del slot.
    CONSTRAINT ck_document_files_expiry CHECK (
        expires_at IS NULL OR (document_date IS NOT NULL AND expires_at > document_date)
    )
);

ALTER TABLE application_document_slots
    ADD CONSTRAINT fk_document_slots_current_file
    FOREIGN KEY (current_file_id)
    REFERENCES document_files(id)
    ON DELETE SET NULL
    DEFERRABLE INITIALLY DEFERRED;

-- Desvío del DER original (paso 10, Parte 5): la tabla guarda también las exoneraciones
-- (`WAIVED`) y sus reaperturas (`REOPENED`), que son decisiones del slot. `slot_id` es
-- nuevo, `document_file_id` pasa a ser nulable y `decision_batch_id` agrupa las filas de
-- una misma exoneración o reapertura.
CREATE TABLE document_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    slot_id UUID NOT NULL REFERENCES application_document_slots(id) ON DELETE RESTRICT,
    document_file_id UUID REFERENCES document_files(id) ON DELETE RESTRICT,
    reviewer_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    decision VARCHAR(20) NOT NULL,
    reason_item_id UUID REFERENCES catalog_items(id) ON DELETE RESTRICT,
    buyer_comment TEXT,
    internal_comment TEXT,
    decision_batch_id UUID,
    CONSTRAINT ck_document_reviews_decision CHECK (
        decision IN ('APPROVED', 'REJECTED', 'WAIVED', 'REOPENED')
    ),
    CONSTRAINT ck_document_reviews_rejection CHECK (
        decision <> 'REJECTED' OR (reason_item_id IS NOT NULL AND buyer_comment IS NOT NULL)
    ),
    CONSTRAINT ck_document_reviews_file CHECK (
        decision NOT IN ('APPROVED', 'REJECTED')
        OR (document_file_id IS NOT NULL AND decision_batch_id IS NULL)
    ),
    CONSTRAINT ck_document_reviews_batch CHECK (
        decision NOT IN ('WAIVED', 'REOPENED') OR decision_batch_id IS NOT NULL
    ),
    CONSTRAINT ck_document_reviews_waiver CHECK (
        decision <> 'WAIVED' OR reason_item_id IS NOT NULL
    ),
    CONSTRAINT ck_document_reviews_reopen CHECK (
        decision <> 'REOPENED' OR (internal_comment IS NOT NULL AND internal_comment <> '')
    )
);

CREATE TABLE document_package_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    application_id UUID NOT NULL REFERENCES credit_applications(id) ON DELETE RESTRICT,
    requested_by_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    -- Versión de la solicitud al pedir el paquete; solo informativa.
    application_version INTEGER NOT NULL CHECK (application_version > 0),
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    -- El ZIP no pasa por el antivirus: se arma con versiones CLEAN cuyo SHA-256 se
    -- verifica al empaquetar, y su file_objects se guarda CLEAN al terminar.
    output_file_object_id UUID UNIQUE REFERENCES file_objects(id) ON DELETE RESTRICT,
    -- Manifiesto interno fijado al pedir el paquete: huella documental y versiones.
    manifest JSONB,
    -- CHECKSUM_MISMATCH o STORAGE_UNAVAILABLE.
    error_code VARCHAR(80),
    -- Inicio del intento en curso; marca qué worker tiene el trabajo.
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    CONSTRAINT ck_document_package_jobs_status CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'EXPIRED')),
    CONSTRAINT ck_document_package_jobs_dates CHECK (
        (completed_at IS NULL OR started_at IS NOT NULL) AND
        (completed_at IS NULL OR completed_at >= started_at) AND
        (expires_at IS NULL OR completed_at IS NULL OR expires_at >= completed_at)
    )
);

-- ================================================================
-- 8. RADICACIÓN MANUAL Y RESPUESTAS DEL BANCO
-- ================================================================

CREATE TABLE filings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    application_id UUID NOT NULL REFERENCES credit_applications(id) ON DELETE RESTRICT,
    bank_product_id UUID NOT NULL REFERENCES bank_products(id) ON DELETE RESTRICT,
    package_job_id UUID NOT NULL UNIQUE REFERENCES document_package_jobs(id) ON DELETE RESTRICT,
    sequence_number INTEGER NOT NULL CHECK (sequence_number > 0),
    channel_item_id UUID NOT NULL REFERENCES catalog_items(id) ON DELETE RESTRICT,
    external_reference VARCHAR(100),
    status VARCHAR(30) NOT NULL DEFAULT 'FILED',
    filed_by_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    filed_at TIMESTAMPTZ NOT NULL,
    target_response_at TIMESTAMPTZ,
    comment TEXT,
    CONSTRAINT uq_filings_application_sequence UNIQUE (application_id, sequence_number),
    CONSTRAINT ck_filings_target CHECK (target_response_at IS NULL OR target_response_at >= filed_at)
);

CREATE TABLE filing_document_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    filing_id UUID NOT NULL REFERENCES filings(id) ON DELETE RESTRICT,
    document_file_id UUID NOT NULL REFERENCES document_files(id) ON DELETE RESTRICT,
    file_object_id UUID NOT NULL REFERENCES file_objects(id) ON DELETE RESTRICT,
    sha256 CHAR(64) NOT NULL,
    document_type_code VARCHAR(80) NOT NULL,
    CONSTRAINT uq_filing_document_snapshots_file UNIQUE (filing_id, document_file_id)
);

CREATE TABLE filing_responses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    filing_id UUID NOT NULL REFERENCES filings(id) ON DELETE RESTRICT,
    response_type_item_id UUID NOT NULL REFERENCES catalog_items(id) ON DELETE RESTRICT,
    reason_item_id UUID REFERENCES catalog_items(id) ON DELETE RESTRICT,
    received_at TIMESTAMPTZ NOT NULL,
    external_reference VARCHAR(100),
    public_message TEXT,
    internal_comment TEXT,
    evidence_file_object_id UUID REFERENCES file_objects(id) ON DELETE RESTRICT,
    approved_amount_cop BIGINT CHECK (approved_amount_cop IS NULL OR approved_amount_cop >= 0),
    approved_term_months SMALLINT CHECK (approved_term_months IS NULL OR approved_term_months > 0),
    valid_until DATE,
    disbursed_amount_cop BIGINT CHECK (disbursed_amount_cop IS NULL OR disbursed_amount_cop >= 0),
    recorded_by_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    corrects_response_id UUID UNIQUE REFERENCES filing_responses(id) ON DELETE RESTRICT,
    CONSTRAINT ck_filing_responses_not_self_correction CHECK (corrects_response_id IS NULL OR corrects_response_id <> id)
);

CREATE TABLE filing_response_observations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    filing_response_id UUID NOT NULL REFERENCES filing_responses(id) ON DELETE CASCADE,
    document_slot_id UUID NOT NULL REFERENCES application_document_slots(id) ON DELETE RESTRICT,
    reason_item_id UUID NOT NULL REFERENCES catalog_items(id) ON DELETE RESTRICT,
    buyer_message TEXT NOT NULL,
    resolved_by_file_id UUID REFERENCES document_files(id) ON DELETE RESTRICT,
    resolved_at TIMESTAMPTZ,
    CONSTRAINT uq_filing_response_observations_slot UNIQUE (filing_response_id, document_slot_id),
    CONSTRAINT ck_filing_response_observations_resolution CHECK (
        (resolved_by_file_id IS NULL AND resolved_at IS NULL) OR
        (resolved_by_file_id IS NOT NULL AND resolved_at IS NOT NULL)
    )
);

-- ================================================================
-- 9. ACTIVIDAD, NOTIFICACIONES Y PLATAFORMA
-- ================================================================

CREATE TABLE activity_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    client_id UUID REFERENCES clients(id) ON DELETE RESTRICT,
    opportunity_id UUID REFERENCES opportunities(id) ON DELETE RESTRICT,
    application_id UUID REFERENCES credit_applications(id) ON DELETE RESTRICT,
    event_type VARCHAR(80) NOT NULL,
    visibility VARCHAR(20) NOT NULL DEFAULT 'INTERNAL',
    title VARCHAR(180) NOT NULL,
    message TEXT,
    actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    actor_buyer_session_id UUID REFERENCES buyer_sessions(id) ON DELETE SET NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    CONSTRAINT ck_activity_logs_resource CHECK (num_nonnulls(client_id, opportunity_id, application_id) >= 1),
    CONSTRAINT ck_activity_logs_actor CHECK (num_nonnulls(actor_user_id, actor_buyer_session_id) <= 1),
    CONSTRAINT ck_activity_logs_visibility CHECK (visibility IN ('INTERNAL', 'BUYER'))
);

CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    client_id UUID REFERENCES clients(id) ON DELETE RESTRICT,
    user_id UUID REFERENCES users(id) ON DELETE RESTRICT,
    application_id UUID REFERENCES credit_applications(id) ON DELETE RESTRICT,
    notification_type VARCHAR(80) NOT NULL,
    title VARCHAR(180) NOT NULL,
    message TEXT NOT NULL,
    read_at TIMESTAMPTZ,
    deduplication_key VARCHAR(180) NOT NULL UNIQUE,
    CONSTRAINT ck_notifications_recipient CHECK (num_nonnulls(client_id, user_id) = 1)
);

CREATE TABLE notification_deliveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notification_id UUID NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
    channel VARCHAR(20) NOT NULL,
    destination VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempt_count SMALLINT NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    next_attempt_at TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    provider_message_id VARCHAR(180),
    last_error_code VARCHAR(80),
    CONSTRAINT ck_notification_deliveries_channel CHECK (channel IN ('EMAIL', 'PORTAL')),
    CONSTRAINT ck_notification_deliveries_status CHECK (status IN ('PENDING', 'SENT', 'FAILED')),
    CONSTRAINT ck_notification_deliveries_sent CHECK (status <> 'SENT' OR sent_at IS NOT NULL)
);

CREATE TABLE idempotency_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    buyer_session_id UUID REFERENCES buyer_sessions(id) ON DELETE CASCADE,
    key VARCHAR(100) NOT NULL,
    method VARCHAR(10) NOT NULL,
    route_fingerprint VARCHAR(180) NOT NULL,
    request_hash CHAR(64) NOT NULL,
    response_status SMALLINT,
    response_body JSONB,
    resource_id UUID,
    expires_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_idempotency_keys_actor CHECK (num_nonnulls(user_id, buyer_session_id) = 1),
    CONSTRAINT ck_idempotency_keys_expiry CHECK (expires_at > created_at),
    CONSTRAINT uq_idempotency_keys_user UNIQUE NULLS NOT DISTINCT (user_id, key, method, route_fingerprint),
    CONSTRAINT uq_idempotency_keys_buyer UNIQUE NULLS NOT DISTINCT (buyer_session_id, key, method, route_fingerprint)
);

CREATE TABLE audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    actor_buyer_session_id UUID REFERENCES buyer_sessions(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(80) NOT NULL,
    resource_id UUID,
    result VARCHAR(20) NOT NULL,
    request_id UUID NOT NULL,
    ip_address INET,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    CONSTRAINT ck_audit_events_actor CHECK (num_nonnulls(actor_user_id, actor_buyer_session_id) <= 1),
    CONSTRAINT ck_audit_events_result CHECK (result IN ('SUCCESS', 'DENIED', 'FAILED'))
);

CREATE TABLE outbox_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type VARCHAR(100) NOT NULL,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id UUID NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempt_count SMALLINT NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    last_error_code VARCHAR(80),
    CONSTRAINT ck_outbox_events_status CHECK (status IN ('PENDING', 'PROCESSING', 'DONE', 'FAILED')),
    CONSTRAINT ck_outbox_events_processed CHECK (status <> 'DONE' OR processed_at IS NOT NULL)
);

CREATE TABLE report_export_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    requested_by_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    report_type VARCHAR(50) NOT NULL,
    filters JSONB NOT NULL DEFAULT '{}'::JSONB,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    output_file_object_id UUID UNIQUE REFERENCES file_objects(id) ON DELETE RESTRICT,
    row_count INTEGER CHECK (row_count IS NULL OR row_count >= 0),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    error_code VARCHAR(80),
    CONSTRAINT ck_report_export_jobs_status CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'EXPIRED')),
    CONSTRAINT ck_report_export_jobs_dates CHECK (
        (completed_at IS NULL OR started_at IS NOT NULL) AND
        (completed_at IS NULL OR completed_at >= started_at) AND
        (expires_at IS NULL OR completed_at IS NULL OR expires_at >= completed_at)
    )
);

-- ================================================================
-- 10. ÍNDICES DE UNICIDAD PARCIAL Y CONSULTA
-- ================================================================

CREATE UNIQUE INDEX uq_partner_memberships_active_user
    ON partner_memberships (user_id)
    WHERE status = 'ACTIVE' AND ended_at IS NULL;

CREATE UNIQUE INDEX uq_client_addresses_primary
    ON client_addresses (client_id)
    WHERE is_primary = TRUE;

CREATE UNIQUE INDEX uq_opportunity_assignments_active
    ON opportunity_assignments (opportunity_id)
    WHERE ended_at IS NULL;

CREATE UNIQUE INDEX uq_application_participants_primary
    ON application_participants (application_id)
    WHERE role = 'PRIMARY' AND is_active = TRUE;

CREATE UNIQUE INDEX uq_application_assignments_active
    ON application_assignments (application_id)
    WHERE ended_at IS NULL;

CREATE UNIQUE INDEX uq_projects_partner_name_open
    ON projects (partner_id, LOWER(name))
    WHERE deleted_at IS NULL AND status <> 'ARCHIVED';

-- Un solo borrador y una sola versión publicada por regla (producto + código).
CREATE UNIQUE INDEX uq_bank_policy_rules_one_draft
    ON bank_policy_rules (bank_product_id, code)
    WHERE status = 'DRAFT';

CREATE UNIQUE INDEX uq_bank_policy_rules_one_active
    ON bank_policy_rules (bank_product_id, code)
    WHERE status = 'ACTIVE';

CREATE UNIQUE INDEX uq_filings_external_reference
    ON filings (bank_product_id, external_reference)
    WHERE external_reference IS NOT NULL;

CREATE INDEX ix_users_active ON users (is_active) WHERE deleted_at IS NULL;
CREATE INDEX ix_auth_sessions_user_active ON auth_sessions (user_id, expires_at) WHERE revoked_at IS NULL;
CREATE INDEX ix_catalog_items_active ON catalog_items (catalog_id, is_active, sort_order);
CREATE INDEX ix_catalog_items_parent ON catalog_items (parent_item_id);
CREATE INDEX ix_projects_partner_status ON projects (partner_id, status);
CREATE INDEX ix_opportunities_advisor_status ON opportunities (assigned_advisor_id, status, updated_at DESC);
CREATE INDEX ix_opportunities_origin_status ON opportunities (origin_user_id, status);
CREATE INDEX ix_opportunities_project_status ON opportunities (project_id, status);
CREATE INDEX ix_opportunity_assignments_history ON opportunity_assignments (opportunity_id, created_at DESC);
CREATE INDEX ix_bank_products_bank_status ON bank_products (bank_id, status);
CREATE INDEX ix_bank_policy_rules_active ON bank_policy_rules (bank_product_id, purpose_item_id, valid_from) WHERE status = 'ACTIVE';
CREATE INDEX ix_document_requirements_active ON document_requirements (bank_product_id, purpose_item_id, employment_profile_item_id, valid_from) WHERE status = 'ACTIVE';
CREATE INDEX ix_applications_workday ON credit_applications (assigned_advisor_id, status, updated_at DESC)
    INCLUDE (code, bank_product_id, purpose_item_id, current_stage_started_at);
CREATE INDEX ix_applications_bank_status ON credit_applications (bank_product_id, status, created_at);
CREATE INDEX ix_applications_opportunity ON credit_applications (opportunity_id, created_at DESC);
CREATE INDEX ix_application_assignments_history ON application_assignments (application_id, created_at DESC);
CREATE INDEX ix_bank_rule_evaluations_latest ON bank_rule_evaluations (application_id, created_at DESC);
CREATE INDEX ix_buyer_access_links_pending ON buyer_access_links (application_id, expires_at)
    WHERE consumed_at IS NULL AND revoked_at IS NULL;
CREATE INDEX ix_tasks_pending_assignee ON tasks (assigned_to_id, due_at) WHERE status = 'PENDING';
CREATE INDEX ix_application_status_history ON application_status_history (application_id, created_at DESC);
CREATE INDEX ix_file_objects_scan_queue ON file_objects (scan_status, created_at) WHERE scan_status = 'PENDING';
-- Paso 10: los índices de slots solo cubren los vigentes (retired_at IS NULL). En Django se
-- llaman ix_doc_slots_app_status e ix_doc_slots_pending (límite de 30 caracteres).
CREATE INDEX ix_document_slots_application_status ON application_document_slots (application_id, status, is_required)
    WHERE retired_at IS NULL;
CREATE INDEX ix_document_slots_pending ON application_document_slots (application_id, sort_order)
    INCLUDE (document_type_id, participant_id, status, current_file_id)
    WHERE is_required = TRUE AND retired_at IS NULL AND status NOT IN ('APPROVED', 'WAIVED');
-- Desvío del DER original (paso 10): la "UQ funcional según tipo/participante/periodo".
CREATE UNIQUE INDEX uq_document_slots_active
    ON application_document_slots (application_id, participant_id, document_type_id, slot_index)
    NULLS NOT DISTINCT
    WHERE retired_at IS NULL;
CREATE INDEX ix_document_files_versions ON document_files (slot_id, version_number DESC);
CREATE INDEX ix_document_reviews_latest ON document_reviews (document_file_id, created_at DESC);
-- Paso 10, Parte 5: historial del slot y lotes de exoneración.
CREATE INDEX ix_document_reviews_slot ON document_reviews (slot_id, created_at DESC);
CREATE INDEX ix_document_reviews_batch ON document_reviews (decision_batch_id) WHERE decision_batch_id IS NOT NULL;
CREATE INDEX ix_document_package_jobs_application ON document_package_jobs (application_id, created_at DESC);
CREATE INDEX ix_document_package_jobs_queue ON document_package_jobs (status, created_at) WHERE status IN ('PENDING', 'RUNNING');
CREATE INDEX ix_filings_application ON filings (application_id, sequence_number DESC);
CREATE INDEX ix_filings_pending_response ON filings (status, target_response_at);
CREATE INDEX ix_filing_responses_history ON filing_responses (filing_id, received_at DESC);
CREATE INDEX ix_filing_observations_open ON filing_response_observations (document_slot_id) WHERE resolved_at IS NULL;
CREATE INDEX ix_activity_application ON activity_logs (application_id, created_at DESC);
CREATE INDEX ix_activity_opportunity ON activity_logs (opportunity_id, created_at DESC);
CREATE INDEX ix_activity_client ON activity_logs (client_id, created_at DESC);
CREATE INDEX ix_notifications_client_unread ON notifications (client_id, created_at DESC) WHERE read_at IS NULL;
CREATE INDEX ix_notifications_user_unread ON notifications (user_id, created_at DESC) WHERE read_at IS NULL;
CREATE INDEX ix_notification_deliveries_queue ON notification_deliveries (status, next_attempt_at) WHERE status IN ('PENDING', 'FAILED');
CREATE INDEX ix_audit_resource ON audit_events (resource_type, resource_id, created_at DESC);
CREATE INDEX ix_audit_user ON audit_events (actor_user_id, created_at DESC);
CREATE INDEX ix_audit_request ON audit_events (request_id);
CREATE INDEX ix_outbox_queue ON outbox_events (available_at, created_at) WHERE status IN ('PENDING', 'FAILED');
CREATE INDEX ix_report_exports_user ON report_export_jobs (requested_by_id, created_at DESC);
CREATE INDEX ix_report_exports_queue ON report_export_jobs (status, created_at) WHERE status IN ('PENDING', 'RUNNING');

-- ============================================================
-- Comisiones (módulo commissions, paso 16)
-- ============================================================

CREATE TABLE commission_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    bank_product_id UUID NOT NULL REFERENCES bank_products(id) ON DELETE RESTRICT,
    rate_pct NUMERIC(8,4) NOT NULL CHECK (rate_pct > 0 AND rate_pct <= 100),
    advisor_share_pct NUMERIC(8,4) NOT NULL,
    broker_share_pct NUMERIC(8,4) NOT NULL,
    valid_from DATE NOT NULL,
    valid_until DATE,
    notes VARCHAR(255),
    created_by_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    CONSTRAINT ck_commission_plans_shares_sum CHECK (advisor_share_pct + broker_share_pct = 100),
    CONSTRAINT ck_commission_plans_advisor_major CHECK (advisor_share_pct > broker_share_pct AND broker_share_pct >= 0),
    CONSTRAINT ck_commission_plans_validity CHECK (valid_until IS NULL OR valid_until > valid_from)
);

CREATE TABLE commission_settlements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    application_id UUID NOT NULL REFERENCES credit_applications(id) ON DELETE RESTRICT,
    filing_response_id UUID NOT NULL UNIQUE REFERENCES filing_responses(id) ON DELETE RESTRICT,
    plan_id UUID NOT NULL REFERENCES commission_plans(id) ON DELETE RESTRICT,
    lead_origin_code VARCHAR(50) NOT NULL,
    base_amount_cop BIGINT NOT NULL CHECK (base_amount_cop > 0),
    rate_pct NUMERIC(8,4) NOT NULL CHECK (rate_pct > 0 AND rate_pct <= 100),
    total_amount_cop BIGINT NOT NULL CHECK (total_amount_cop >= 0),
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'VOIDED')),
    needs_review BOOLEAN NOT NULL DEFAULT FALSE,
    voided_at TIMESTAMPTZ,
    voided_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
    void_reason VARCHAR(255),
    CONSTRAINT ck_commission_settlements_void CHECK (
        status <> 'VOIDED' OR (voided_at IS NOT NULL AND void_reason IS NOT NULL)
    )
);

CREATE TABLE commission_shares (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    settlement_id UUID NOT NULL REFERENCES commission_settlements(id) ON DELETE CASCADE,
    beneficiary_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    beneficiary_role VARCHAR(40) NOT NULL CHECK (beneficiary_role IN ('ADVISOR', 'INDEPENDENT_BROKER')),
    share_pct NUMERIC(8,4) NOT NULL CHECK (share_pct > 0 AND share_pct <= 100),
    amount_cop BIGINT NOT NULL CHECK (amount_cop >= 0),
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'PAID', 'VOIDED')),
    paid_at DATE,
    paid_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
    payment_reference VARCHAR(100),
    CONSTRAINT uq_commission_shares_role UNIQUE (settlement_id, beneficiary_role),
    CONSTRAINT ck_commission_shares_paid CHECK (status <> 'PAID' OR paid_at IS NOT NULL)
);

CREATE INDEX ix_commission_plans_product ON commission_plans (bank_product_id, valid_from DESC);
CREATE UNIQUE INDEX uq_commission_settlements_active ON commission_settlements (application_id) WHERE status = 'ACTIVE';
CREATE INDEX ix_commission_settlements_status ON commission_settlements (status, created_at DESC);
CREATE INDEX ix_commission_shares_beneficiary ON commission_shares (beneficiary_user_id, status, created_at DESC);

COMMIT;

-- Reglas que requieren servicio transaccional o trigger controlado:
-- 1. La sesión/link debe pertenecer al mismo cliente y solicitud.
-- 2. participant_id de un slot debe pertenecer a la misma solicitud.
-- 3. current_file_id debe pertenecer al mismo slot.
-- 4. Solo un archivo CLEAN y aprobado puede entrar a un snapshot.
-- 5. Una radicación exige todos los slots obligatorios APPROVED/WAIVED.
-- 6. Los catalog_items usados por cada FK deben pertenecer al catálogo esperado.
-- 7. Las vigencias de commission_plans no se solapan por producto (servicio con bloqueo).
-- 8. Las partes de una liquidación suman total_amount_cop y el beneficiario corresponde al origen.
