# Real Estate Credit Backoffice

[![Backend CI](https://github.com/CarlosDev88/real-estate-credit-backoffice/actions/workflows/backend.yml/badge.svg)](https://github.com/CarlosDev88/real-estate-credit-backoffice/actions/workflows/backend.yml)
[![Frontend CI](https://github.com/CarlosDev88/real-estate-credit-backoffice/actions/workflows/frontend.yml/badge.svg)](https://github.com/CarlosDev88/real-estate-credit-backoffice/actions/workflows/frontend.yml)

MVP that manages Colombian real-estate credit applications. It has two faces: an internal operations backoffice and a buyer self-service portal, covering clients, opportunities, credit applications, documents, manual bank filings, bank responses, notifications, reports, and commissions.

This repository is a monorepo: the Django API, the frontend, the API contract between them, the design system, and the functional documentation live together.

## Project Status

> Last updated: November 17, 2026. The project runs locally and in CI; there is no deployment.

### Backend: 15 of 16 modules merged

Django 5.2 + DRF modular monolith on PostgreSQL 16, built in the dependency order of the data model.

| # | Module | What it does | Status |
| ---: | --- | --- | --- |
| 1 | `identity` (core) | Internal users, roles, permissions, JWT sessions in HTTP-only cookies, password reset | ✅ Merged |
| 2 | `catalogs` | Administrable catalogs and workflow transitions per role | ✅ Merged |
| 3 | `partners` | Construction partners, memberships, and projects | ✅ Merged |
| 4 | `identity` (invitations) | Internal invitations, including partner memberships | ✅ Merged |
| 5 | `crm` | Clients, addresses, opportunities, and advisor assignment | ✅ Merged |
| 6 | `banking` | Banks, products, purposes, and bank policy rules | ✅ Merged |
| 7 | `documents` (setup) | Document types and requirements per product and purpose | ✅ Merged |
| 8 | `applications` | Credit applications, participants, financial profile, property, financing, status history | ✅ Merged |
| 9 | `identity` (buyer access) | Expiring single-use magic links, buyer sessions, and consents | ✅ Merged |
| 10 | `documents` (dossier) | Document checklist, uploads with file validation and antivirus, review, signed downloads, filing package | ✅ Merged |
| 11 | `filings` | Manual bank filings, bank responses, returns with per-document observations, evidence | ✅ Merged |
| 12 | `tasks` / `workday` / `activity` | Advisor "My day", manual tasks, activity timeline, and internal notes | ✅ Merged |
| 13 | `notifications` / `idempotency` | Buyer notifications by portal and email with retries; `Idempotency-Key` on critical operations | ✅ Merged |
| 14 | `audit` | Immutable technical audit log (PostgreSQL trigger), admin search, and retention | ✅ Merged |
| 15 | `reporting` | Dashboard, cohort funnel, workload, bank results, applications report, CSV and async exports | ✅ Merged |
| 16 | `commissions` | Commission plans, automatic settlement on disbursement, advisor/broker split, payouts | 🚧 In progress (plans and settlement done; payouts and "my commissions" next) |

### Frontend: about half of the 22 views

Next.js 16, Ant Design 6, Tailwind 4, TanStack Query, React Hook Form + Zod, and types generated from the API contract.

| Area | Views | Status |
| --- | --- | --- |
| Base | Login, app shell, role-based navigation, light and dark themes | ✅ Merged |
| Backoffice | Applications list, application workspace (data, documents and review, history), manual filing and bank responses | ✅ Merged |
| Buyer portal | Magic-link access, consents, home, personal and financial data, property and financing, documents with mobile upload | ✅ Merged |
|

## Quality

Every pull request runs the backend and frontend CI. The backend job checks lint, types, migrations, the test suite with a 95 % coverage floor, and that the OpenAPI contract is up to date, plus four security checks: `pip-audit` (dependencies), `gitleaks` (secrets across the whole history), `bandit` (static analysis) and that the generated access-matrix document matches its test. The result is posted as a single comment on the PR.

The backend went through a security audit (November 2026): automated scans, dynamic testing against a local copy of the API, a role access matrix that requests every one of the 234 API operations as each of 9 actors, and a manual review. It found 20 issues, none critical or high, and left about 2,400 security tests in `backend/tests/security/`. The report, in Spanish: [`docs/SEGURIDAD.md`](docs/SEGURIDAD.md).

## Documentation

| Document | Content |
| --- | --- |
| [`docs/REQUERIMIENTOS_MVP_CREDITO.md`](docs/REQUERIMIENTOS_MVP_CREDITO.md) | Functional and non-functional requirements (Spanish) |
| [`docs/API_REST_MVP_CREDITO.md`](docs/API_REST_MVP_CREDITO.md) | REST API design, roles and access rules (Spanish) |
| [`contracts/openapi.json`](contracts/openapi.json) | The API contract the frontend types are generated from |
| [`docs/SEGURIDAD.md`](docs/SEGURIDAD.md) | Security audit report: method, threat model, controls, access matrix, findings (Spanish) |
| [`docs/seguridad/`](docs/seguridad/) | Detailed results of each audit phase and every finding |
| [`backend/security/README.md`](backend/security/README.md) | How to repeat the security audit locally |
| [`backend/README.md`](backend/README.md) | Running the backend locally |
