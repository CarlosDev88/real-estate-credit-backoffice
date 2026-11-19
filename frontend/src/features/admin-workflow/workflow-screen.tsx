"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Alert, Button, Checkbox, Input } from "antd";
import { useEffect, useId, useMemo, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { ActionModal } from "@/components/ui/action-modal";
import { DataList, Datum } from "@/components/ui/card";
import { CardList, DataTable, dataColumns } from "@/components/ui/data-table";
import { EmptyState } from "@/components/ui/empty-state";
import { FormField, useFormErrorHandler } from "@/components/ui/form-field";
import { ListPagination } from "@/components/ui/list-pagination";
import { PageHeader } from "@/components/ui/page-header";
import { ScrollTabs } from "@/components/ui/scroll-tabs";
import { SidePanel } from "@/components/ui/side-panel";
import { ErrorState } from "@/components/ui/state-views";
import { ToneBadge } from "@/components/ui/status-badge";
import { ActiveStatusBadge } from "@/features/admin-common/active-status";
import { labelOf, useCatalog, type MetadataItem } from "@/features/admin-common/catalogs";
import { changedFields } from "@/features/admin-common/changes";
import { AdminListFilters, type FilterOption } from "@/features/admin-common/list-filters";
import {
  DEFAULT_PAGE_SIZE,
  formatOrdering,
  MOBILE_QUERY,
  parseOrdering,
  parsePageSize,
  positiveInt,
  useListParams,
  type ListParamsConfig,
} from "@/features/admin-common/list-params";
import { ListSkeleton } from "@/features/admin-common/list-skeleton";
import { roleName, useRoles, type Role } from "@/features/admin-users/queries";
import {
  FLOWS,
  useSetTransitionActive,
  useTransitions,
  useUpdateTransition,
  type FlowType,
  type Transition,
  type TransitionsParams,
} from "@/features/admin-workflow/queries";
import { useMe } from "@/features/auth/queries";
import { isApiError } from "@/lib/api/errors";
import { useMediaQuery } from "@/lib/hooks/use-media-query";
import { useApiErrorToast } from "@/providers/api-error-toast";
import { useToast } from "@/providers/toast";

const SORT_FIELDS = ["code", "from_status", "to_status", "created_at"] as const;
const DEFAULT_ORDERING = "from_status";
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const DEFAULTS: TransitionsParams = {
  flujo: "APPLICATION",
  search: "",
  active: "",
  ordering: DEFAULT_ORDERING,
  page: 1,
  page_size: DEFAULT_PAGE_SIZE,
  abierta: "",
};

export function parseTransitionsParams(search: URLSearchParams): TransitionsParams {
  const flow = search.get("flujo");
  const active = search.get("active") ?? "";
  const open = search.get("abierta") ?? "";
  return {
    flujo: FLOWS.some((f) => f.code === flow) ? (flow as FlowType) : "APPLICATION",
    search: (search.get("search") ?? "").trim(),
    active: active === "true" || active === "false" ? active : "",
    ordering: formatOrdering(parseOrdering(search.get("ordering"), SORT_FIELDS, DEFAULT_ORDERING)),
    page: positiveInt(search.get("page")) ?? 1,
    page_size: parsePageSize(search),
    abierta: UUID.test(open) ? open : "",
  };
}

const CONFIG: ListParamsConfig<TransitionsParams> = {
  defaults: DEFAULTS,
  order: ["flujo", "search", "active", "ordering", "page", "page_size", "abierta"],
  parse: parseTransitionsParams,
  keepPage: ["abierta"],
};

const ACTIVE_OPTIONS: FilterOption[] = [
  { value: "true", label: "Activas" },
  { value: "false", label: "Inactivas" },
];

const statusOf = (transition: Transition) => (transition.is_active ? "ACTIVE" : "INACTIVE");

function StatusBadge({ transition }: { transition: Transition }) {
  return <ToneBadge tone="neutral">{transition.is_active ? "Activa" : "Inactiva"}</ToneBadge>;
}

function rolesText(transition: Transition, roles: readonly Role[] | undefined) {
  return transition.roles.map((code) => roleName(roles, code)).join(", ");
}

// ---------- editar ----------

const schema = z.object({
  label: z
    .string()
    .trim()
    .min(1, { error: "Escribe la etiqueta." })
    .max(120, { error: "Máximo 120 caracteres." }),
  roles: z.array(z.string()),
});
type TransitionValues = z.infer<typeof schema>;
const FIELDS = ["label", "roles"] as const;

function EditModal({
  transition,
  roles,
  onClose,
}: {
  transition: Transition;
  roles: readonly Role[] | undefined;
  onClose: () => void;
}) {
  const ids = useId();
  const toast = useToast();
  const update = useUpdateTransition(transition.id);
  const initial = { label: transition.label, roles: transition.roles };
  const { control, handleSubmit, setError, formState } = useForm<TransitionValues>({
    resolver: zodResolver(schema),
    defaultValues: initial,
  });
  const onError = useFormErrorHandler<TransitionValues>(setError, FIELDS);

  const submit = handleSubmit((values) => {
    const body = changedFields(values, initial, ["label", "roles"]);
    if (Object.keys(body).length === 0) return onClose();
    update.mutate(body, {
      onSuccess: () => {
        toast.success({ title: "Transición guardada" });
        onClose();
      },
      onError,
    });
  });

  return (
    <ActionModal
      open
      title={`Editar ${transition.code}`}
      description="La etiqueta es el texto del botón que ven los usuarios; los roles, quién puede usarla."
      okText="Guardar"
      loading={update.isPending}
      onSubmit={submit}
      onCancel={onClose}
    >
      <FormField id={`${ids}-label`} label="Etiqueta" error={formState.errors.label?.message}>
        {(ctl) => (
          <Controller
            control={control}
            name="label"
            render={({ field }) => <Input {...field} {...ctl} maxLength={120} />}
          />
        )}
      </FormField>
      <Controller
        control={control}
        name="roles"
        render={({ field }) => (
          <fieldset
            className="m-0 grid gap-2 border-0 p-0"
            aria-describedby={formState.errors.roles ? `${ids}-roles-error` : undefined}
          >
            <legend className="mb-1.5 p-0 text-sm font-medium">Roles</legend>
            {(roles ?? []).map((role) => (
              <Checkbox
                key={role.code}
                checked={field.value.includes(role.code)}
                onChange={(event) =>
                  field.onChange(
                    event.target.checked
                      ? [...field.value, role.code]
                      : field.value.filter((code) => code !== role.code),
                  )
                }
              >
                {role.name}
              </Checkbox>
            ))}
            {formState.errors.roles && (
              <p id={`${ids}-roles-error`} className="text-tone-danger-fg m-0 text-sm">
                {formState.errors.roles.message}
              </p>
            )}
          </fieldset>
        )}
      />
    </ActionModal>
  );
}

// ---------- panel ----------

function TransitionPanel({
  transition,
  statuses,
  roles,
  permissions,
  onClose,
}: {
  transition: Transition;
  statuses: readonly MetadataItem[];
  roles: readonly Role[] | undefined;
  permissions: { canUpdate: boolean; canPublish: boolean };
  onClose: () => void;
}) {
  const toast = useToast();
  const showError = useApiErrorToast();
  const setActive = useSetTransitionActive();
  const [modal, setModal] = useState<"edit" | "status" | null>(null);
  const activate = !transition.is_active;

  const runStatus = () =>
    setActive.mutate(
      { id: transition.id, active: activate },
      {
        onSuccess: () => {
          toast.success({ title: activate ? "Transición activada" : "Transición desactivada" });
          setModal(null);
        },
        onError: (error) => {
          setModal(null);
          showError(error);
        },
      },
    );

  const footer = (permissions.canUpdate || permissions.canPublish) && (
    <div className="flex flex-wrap gap-2">
      {permissions.canPublish && (
        <Button danger={!activate} onClick={() => setModal("status")}>
          {activate ? "Activar" : "Desactivar"}
        </Button>
      )}
      <div className="flex-1" />
      {permissions.canUpdate && (
        <Button type="primary" disabled={transition.is_active} onClick={() => setModal("edit")}>
          Editar
        </Button>
      )}
    </div>
  );

  return (
    <>
      <SidePanel
        open
        onClose={onClose}
        eyebrow="Transición"
        title={transition.label}
        footer={footer || undefined}
      >
        <div className="grid gap-4">
          {transition.is_active && permissions.canUpdate && (
            <Alert
              type="info"
              showIcon
              title="Para editarla, desactívala primero"
              description="La API solo deja editar transiciones inactivas, para no cambiar un flujo en uso."
            />
          )}
          <DataList layout="inline">
            <Datum label="Código">
              <span className="font-mono">{transition.code}</span>
            </Datum>
            <Datum label="Estado">
              <StatusBadge transition={transition} />
            </Datum>
            <Datum label="De">{labelOf(statuses, transition.from_status)}</Datum>
            <Datum label="A">{labelOf(statuses, transition.to_status)}</Datum>
            <Datum label="Roles">{rolesText(transition, roles)}</Datum>
            <Datum label="Permiso">
              {transition.required_permission && (
                <span className="font-mono text-xs">{transition.required_permission}</span>
              )}
            </Datum>
            <Datum label="Regla previa">
              {transition.guard_code && (
                <span className="font-mono text-xs">{transition.guard_code}</span>
              )}
            </Datum>
            <Datum label="Quién la ejecuta">
              {transition.system_only
                ? "Solo el sistema (radicación o respuesta del banco): no sale como botón."
                : "Los usuarios, con su rol y permiso."}
            </Datum>
          </DataList>
        </div>
      </SidePanel>
      {modal === "edit" && (
        <EditModal transition={transition} roles={roles} onClose={() => setModal(null)} />
      )}
      <ActionModal
        open={modal === "status"}
        title={`${activate ? "Activar" : "Desactivar"} ${transition.label}`}
        description={
          activate
            ? "Vuelve a ofrecerse a los roles que la tienen."
            : "Deja de ofrecerse como acción: si no hay otra transición activa entre esos estados, ese paso no se puede dar."
        }
        okText={activate ? "Activar" : "Desactivar"}
        danger={!activate}
        loading={setActive.isPending}
        onSubmit={runStatus}
        onCancel={() => setModal(null)}
      />
    </>
  );
}

// ---------- pantalla ----------

const helper = dataColumns<Transition>();

/** `/admin/flujos` (REQ §6 vista 14): transiciones de estado de cada flujo. */
export function WorkflowScreen() {
  const { params, update, replace } = useListParams(CONFIG);
  const mobile = useMediaQuery(MOBILE_QUERY);
  const me = useMe();
  const permissions = me.data?.permissions ?? [];
  const has = (code: string) => permissions.includes(code);
  const flow = FLOWS.find((f) => f.code === params.flujo)!;
  const statuses = useCatalog(flow.statusCatalog);
  const roles = useRoles(has("roles.read"));
  const list = useTransitions(params);
  const rows = list.data?.items ?? [];
  const busy = list.isFetching && list.isPlaceholderData;
  const open = rows.find((t) => t.id === params.abierta);
  const clear = () => update({ search: "", active: "" });
  const filtered = params.search !== "" || params.active !== "";

  const pageGone = isApiError(list.error) && list.error.status === 404 && params.page > 1;
  useEffect(() => {
    if (pageGone) update({ page: 1 });
  }, [pageGone, update]);

  const columns = useMemo(
    () =>
      helper.columns([
        helper.accessor((row) => row.code, {
          id: "code",
          header: "Transición",
          cell: ({ row }) => (
            <div className="grid max-w-[260px]">
              <button
                type="button"
                onClick={() => update({ abierta: row.original.id })}
                className="text-text-link cursor-pointer truncate border-0 bg-transparent p-0 text-left font-medium hover:underline"
              >
                {row.original.label}
              </button>
              <span className="text-text-tertiary truncate font-mono text-xs">
                {row.original.code}
              </span>
            </div>
          ),
        }),
        helper.accessor((row) => row.from_status, {
          id: "from_status",
          header: "De",
          cell: ({ row }) => (
            <span className="text-sm">{labelOf(statuses.items, row.original.from_status)}</span>
          ),
        }),
        helper.accessor((row) => row.to_status, {
          id: "to_status",
          header: "A",
          cell: ({ row }) => (
            <span className="text-sm">{labelOf(statuses.items, row.original.to_status)}</span>
          ),
        }),
        helper.display({
          id: "roles",
          header: "Roles",
          cell: ({ row }) => (
            <span className="block max-w-[220px] truncate text-sm">
              {rolesText(row.original, roles.data)}
            </span>
          ),
        }),
        helper.display({
          id: "system",
          header: "Ejecuta",
          cell: ({ row }) => (
            <span className="text-text-secondary text-sm">
              {row.original.system_only ? "Sistema" : "Usuarios"}
            </span>
          ),
        }),
        helper.display({
          id: "status",
          header: "Estado",
          cell: ({ row }) => <StatusBadge transition={row.original} />,
        }),
      ]),
    [roles.data, statuses.items, update],
  );

  let body;
  if (list.isPending) {
    body = <ListSkeleton label="Cargando transiciones" />;
  } else if (list.isError) {
    body = (
      <div className="p-3">
        <ErrorState
          title="No pudimos cargar las transiciones"
          message={list.error.message}
          onRetry={() => void list.refetch()}
          retrying={list.isFetching}
        />
      </div>
    );
  } else if (rows.length === 0) {
    body = filtered ? (
      <EmptyState
        title="No hay transiciones con estos filtros"
        action={
          <Button size="small" onClick={clear}>
            Limpiar filtros
          </Button>
        }
      />
    ) : (
      <EmptyState title="Este flujo no tiene transiciones" />
    );
  } else if (mobile) {
    body = (
      <CardList
        ariaLabel="Transiciones"
        rows={rows}
        getRowId={(t) => t.id}
        onOpen={(t) => update({ abierta: t.id })}
        busy={busy}
        renderCard={(t) => (
          <>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => update({ abierta: t.id })}
                className="text-text-link min-w-0 cursor-pointer truncate border-0 bg-transparent p-0 text-left font-medium"
              >
                {t.label}
              </button>
              <span className="ml-auto shrink-0">
                <ActiveStatusBadge status={statusOf(t)} />
              </span>
            </div>
            <span className="text-text-secondary text-sm">
              {labelOf(statuses.items, t.from_status)} → {labelOf(statuses.items, t.to_status)}
            </span>
          </>
        )}
      />
    );
  } else {
    body = (
      <DataTable
        ariaLabel="Transiciones"
        columns={columns}
        rows={rows}
        getRowId={(t) => t.id}
        sorting={parseOrdering(params.ordering, SORT_FIELDS, DEFAULT_ORDERING)}
        sortableFields={SORT_FIELDS}
        onSort={(sorting) => update({ ordering: formatOrdering(sorting) })}
        onOpen={(t) => update({ abierta: t.id })}
        busy={busy}
        stickyColumn="code"
        minWidth={960}
      />
    );
  }

  return (
    <div className="grid content-start gap-4">
      <PageHeader
        title="Flujos"
        description="Los pasos entre estados de solicitudes, oportunidades y proyectos, quién puede darlos y con qué texto."
      />
      <ScrollTabs
        ariaLabel="Flujos"
        value={params.flujo}
        onChange={(key) => replace({ flujo: key as FlowType })}
        items={FLOWS.map((f) => ({ key: f.code, label: f.label }))}
      />
      <div role="tabpanel" aria-label={flow.label} className="grid gap-4">
        <section
          aria-label="Listado de transiciones"
          className="bg-bg-surface border-border-default overflow-hidden rounded-lg border"
        >
          <AdminListFilters
            search={{
              value: params.search,
              placeholder: "Código o etiqueta",
              ariaLabel: "Buscar transiciones por código o etiqueta",
            }}
            onSearch={(search) => update({ search })}
            selects={[
              { key: "active", label: "Estado", value: params.active, options: ACTIVE_OPTIONS },
            ]}
            onSelect={(key, value) => update({ [key]: value })}
            onClear={clear}
            mobile={mobile}
          />
          {body}
          {list.data && rows.length > 0 && (
            <ListPagination
              page={params.page}
              pageSize={params.page_size}
              total={list.data.total}
              itemsLabel="Transiciones"
              onPage={(page) => update({ page })}
              onPageSize={(page_size) => update({ page_size })}
              compact={mobile}
            />
          )}
        </section>
      </div>
      {open && (
        <TransitionPanel
          key={open.id}
          transition={open}
          statuses={statuses.items}
          roles={roles.data}
          permissions={{ canUpdate: has("workflow.update"), canPublish: has("workflow.publish") }}
          onClose={() => update({ abierta: "" })}
        />
      )}
    </div>
  );
}
