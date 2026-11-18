"use client";

import { Button } from "antd";
import { useState } from "react";

import { ActionModal } from "@/components/ui/action-modal";
import { DataList, Datum } from "@/components/ui/card";
import { SidePanel } from "@/components/ui/side-panel";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { describeCondition, pretty } from "@/features/admin-banks/condition";
import { RuleStatusBadge, SeverityBadge } from "@/features/admin-banks/labels";
import {
  useRule,
  useRuleVersions,
  useSetRuleActive,
  type Rule,
} from "@/features/admin-banks/queries";
import { RuleFormModal } from "@/features/admin-banks/rule-form-modal";
import { RuleTestModal } from "@/features/admin-banks/rule-test-modal";
import { isApiError } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/format";
import { useApiErrorToast } from "@/providers/api-error-toast";
import { useToast } from "@/providers/toast";

export interface RulePermissions {
  /** `bank_rules.update`: editar y probar. */
  canUpdate: boolean;
  /** `bank_rules.publish`: publicar, activar y desactivar. */
  canPublish: boolean;
}

type Modal = "edit" | "test" | "publish" | "deactivate" | null;

function Versions({ rule, onOpen }: { rule: Rule; onOpen: (id: string) => void }) {
  const versions = useRuleVersions(rule.id);
  if (versions.isPending) return <LoadingState label="Cargando versiones" blocks={[]} />;
  if (versions.isError) {
    return (
      <ErrorState
        variant="inline"
        title="No pudimos cargar las versiones"
        onRetry={() => void versions.refetch()}
        retrying={versions.isFetching}
      />
    );
  }
  const items = [...versions.data].sort((a, b) => b.version - a.version);
  return (
    <ul aria-label="Versiones" className="m-0 grid list-none p-0">
      {items.map((version) => {
        const current = version.id === rule.id;
        return (
          <li
            key={version.id}
            className="border-border-default flex flex-wrap items-center gap-2 border-b py-2 text-sm last:border-b-0"
          >
            {current ? (
              <span className="font-semibold" aria-current="true">
                v{version.version} (esta)
              </span>
            ) : (
              <Button type="link" size="small" className="px-0" onClick={() => onOpen(version.id)}>
                v{version.version}
              </Button>
            )}
            <RuleStatusBadge status={version.status} />
            <span className="text-text-tertiary ml-auto text-xs">
              {version.created_by.name} · {formatDateTime(version.created_at)}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * Panel de una versión de la regla (`GET /bank-policy-rules/{id}`): condición, vigencia,
 * versiones y acciones (editar, probar, publicar, desactivar).
 */
export function RulePanel({
  ruleId,
  productId,
  permissions,
  onOpen,
  onClose,
}: {
  ruleId: string;
  productId: string;
  permissions: RulePermissions;
  /** Abrir otra versión (o el borrador que se acaba de crear). */
  onOpen: (id: string) => void;
  onClose: () => void;
}) {
  const toast = useToast();
  const showError = useApiErrorToast();
  const query = useRule(ruleId);
  const setActive = useSetRuleActive(ruleId);
  const [modal, setModal] = useState<Modal>(null);
  const rule = query.data;
  const close = () => setModal(null);

  const runStatus = (active: boolean) =>
    setActive.mutate(active, {
      onSuccess: () => {
        toast.success({ title: active ? "Regla publicada" : "Regla desactivada" });
        close();
      },
      onError: (error) => {
        close();
        showError(error);
      },
    });

  let body;
  if (query.isPending) {
    body = <LoadingState label="Cargando regla" blocks={[24, 24, 24, 120]} />;
  } else if (query.isError) {
    const gone = isApiError(query.error) && query.error.status === 404;
    body = (
      <ErrorState
        variant="page"
        title={gone ? "Esta regla ya no existe" : "No pudimos cargar la regla"}
        message={query.error.message}
        onRetry={() => void query.refetch()}
        retrying={query.isFetching}
      />
    );
  } else {
    const data = query.data;
    body = (
      <div className="grid gap-6">
        <DataList layout="inline">
          <Datum label="Estado">
            <RuleStatusBadge status={data.status} />
          </Datum>
          <Datum label="Severidad">
            <SeverityBadge severity={data.severity} />
          </Datum>
          <Datum label="Finalidad">{data.purpose?.label ?? "Todas las finalidades"}</Datum>
          <Datum label="Mensaje">{data.message}</Datum>
          <Datum label="Vigente desde">{formatDateTime(data.valid_from)}</Datum>
          <Datum label="Vigente hasta">{formatDateTime(data.valid_to) ?? "Sin vencimiento"}</Datum>
          <Datum label="Creada por">
            {data.created_by.name} · {formatDateTime(data.created_at)}
          </Datum>
        </DataList>
        <section aria-labelledby="rule-condition" className="grid gap-2">
          <h3 id="rule-condition" className="m-0 text-base font-semibold">
            Condición
          </h3>
          <p className="m-0 font-mono text-sm">{describeCondition(data.condition)}</p>
          <pre className="bg-bg-subtle border-border-default m-0 max-h-64 overflow-auto rounded-md border p-3 font-mono text-xs">
            {pretty(data.condition)}
          </pre>
        </section>
        <section aria-labelledby="rule-versions" className="grid gap-2">
          <h3 id="rule-versions" className="m-0 text-base font-semibold">
            Versiones
          </h3>
          <Versions rule={data} onOpen={onOpen} />
        </section>
      </div>
    );
  }

  const publish = rule && permissions.canPublish && rule.status !== "ACTIVE";
  const deactivate = rule && permissions.canPublish && rule.status === "ACTIVE";
  const footer = rule && (permissions.canUpdate || permissions.canPublish) && (
    <div className="flex flex-wrap gap-2">
      {deactivate && (
        <Button danger onClick={() => setModal("deactivate")}>
          Desactivar
        </Button>
      )}
      {permissions.canUpdate && <Button onClick={() => setModal("test")}>Probar</Button>}
      <div className="flex-1" />
      {permissions.canUpdate && (
        <Button type={publish ? "default" : "primary"} onClick={() => setModal("edit")}>
          {rule.status === "DRAFT" ? "Editar" : "Nueva versión"}
        </Button>
      )}
      {publish && (
        <Button type="primary" onClick={() => setModal("publish")}>
          {rule.status === "DRAFT" ? "Publicar" : "Activar"}
        </Button>
      )}
    </div>
  );

  return (
    <>
      <SidePanel
        open
        onClose={onClose}
        eyebrow={rule ? `${rule.bank_product.name} · v${rule.version}` : "Regla"}
        title={rule?.code ?? "Regla"}
        footer={footer || undefined}
        width={600}
      >
        {body}
      </SidePanel>
      {rule && modal === "edit" && (
        <RuleFormModal
          productId={productId}
          rule={rule}
          onClose={close}
          onSaved={(saved) => {
            if (saved.id !== rule.id) onOpen(saved.id);
          }}
        />
      )}
      {rule && modal === "test" && <RuleTestModal rule={rule} onClose={close} />}
      {rule && modal === "publish" && (
        <ActionModal
          open
          title={
            rule.status === "DRAFT"
              ? `Publicar ${rule.code} v${rule.version}`
              : `Activar ${rule.code} v${rule.version}`
          }
          description="Desde ahora se aplica a las evaluaciones de este producto. Si hay otra versión activa, pasa a inactiva."
          okText={rule.status === "DRAFT" ? "Publicar" : "Activar"}
          loading={setActive.isPending}
          onSubmit={() => runStatus(true)}
          onCancel={close}
        />
      )}
      {rule && modal === "deactivate" && (
        <ActionModal
          open
          title={`Desactivar ${rule.code} v${rule.version}`}
          description="Deja de aplicarse a las evaluaciones nuevas. Las evaluaciones hechas guardan la versión que usaron."
          okText="Desactivar"
          danger
          loading={setActive.isPending}
          onSubmit={() => runStatus(false)}
          onCancel={close}
        />
      )}
    </>
  );
}
