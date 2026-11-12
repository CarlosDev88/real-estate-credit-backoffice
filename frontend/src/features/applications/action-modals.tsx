"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Alert, Button, Input, InputNumber, Modal, Select } from "antd";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { FormField, useFormErrorHandler } from "@/features/applications/form-field";
import { useCatalog } from "@/features/applications/queries";
import {
  useAdvisors,
  useAssign,
  useCreateBuyerLink,
  useTransition,
  useWithdraw,
  type AvailableAction,
  type BuyerAccessLinkCreated,
} from "@/features/applications/workspace-queries";
import { formatDateTime } from "@/lib/format";
import { useToast } from "@/providers/toast";

/** Máximo de `comment` en transiciones y desistimientos (API §16.3). */
const COMMENT_MAX = 2000;

/** `{ [key]: value }` solo si hay valor: los campos opcionales vacíos no se envían. */
function optional<K extends string>(key: K, value: string | undefined): Partial<Record<K, string>> {
  return value ? ({ [key]: value } as Record<K, string>) : {};
}

const optionsOf = (items: { code: string; label: string }[]) =>
  items.map((item) => ({ value: item.code, label: item.label }));

interface BaseModalProps {
  applicationId: string;
  open: boolean;
  onClose: () => void;
}

// ---------- transición ----------

const transitionSchema = z.object({
  reason_code: z.string().optional(),
  comment: z.string().max(COMMENT_MAX, { error: `Máximo ${COMMENT_MAX} caracteres.` }),
});
type TransitionValues = z.infer<typeof transitionSchema>;
const TRANSITION_FIELDS = ["reason_code", "comment"] as const;

/**
 * Confirmación de una transición de `available_actions`. El motivo siempre se ofrece:
 * la API dice si es obligatorio para el destino (`400` en `reason_code`), así el front
 * no guarda la lista de estados que lo exigen.
 */
export function TransitionModal({
  applicationId,
  open,
  onClose,
  action,
  version,
}: BaseModalProps & { action: AvailableAction | null; version: number }) {
  const ids = useId();
  const toast = useToast();
  const transition = useTransition(applicationId);
  const reasons = useCatalog("application_transition_reason");
  const { control, handleSubmit, setError, reset, formState } = useForm<TransitionValues>({
    resolver: zodResolver(transitionSchema),
    defaultValues: { reason_code: undefined, comment: "" },
  });
  const onError = useFormErrorHandler<TransitionValues>(setError, TRANSITION_FIELDS);

  const close = () => {
    reset();
    onClose();
  };

  const submit = handleSubmit((values) => {
    if (!action) return;
    transition.mutate(
      {
        target_status: action.target_status,
        ...optional("reason_code", values.reason_code),
        comment: values.comment.trim(),
        expected_version: version,
      },
      {
        onSuccess: () => {
          toast.success({ title: "Cambio de estado registrado", message: action.label });
          close();
        },
        onError,
      },
    );
  });

  return (
    <Modal
      open={open && !!action}
      title={action?.label}
      onCancel={close}
      okText={action?.label}
      cancelText="Cancelar"
      onOk={() => void submit()}
      confirmLoading={transition.isPending}
      destroyOnHidden
    >
      <form noValidate onSubmit={(e) => void submit(e)} className="grid gap-4 pt-2">
        <FormField
          id={`${ids}-reason`}
          label="Motivo"
          optional="si el cambio lo exige"
          error={formState.errors.reason_code?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="reason_code"
              render={({ field }) => (
                <Select
                  {...ctl}
                  value={field.value}
                  onChange={field.onChange}
                  allowClear
                  placeholder="Elige un motivo"
                  options={optionsOf(reasons.items)}
                  loading={reasons.isPending}
                  virtual={false}
                />
              )}
            />
          )}
        </FormField>
        <FormField
          id={`${ids}-comment`}
          label="Comentario"
          optional="opcional"
          error={formState.errors.comment?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="comment"
              render={({ field }) => (
                <Input.TextArea {...field} {...ctl} rows={3} maxLength={COMMENT_MAX} />
              )}
            />
          )}
        </FormField>
      </form>
    </Modal>
  );
}

// ---------- desistimiento ----------

const withdrawSchema = z.object({
  reason_code: z.string({ error: "Elige el motivo." }).min(1, { error: "Elige el motivo." }),
  comment: z.string().max(COMMENT_MAX, { error: `Máximo ${COMMENT_MAX} caracteres.` }),
});
type WithdrawValues = z.infer<typeof withdrawSchema>;
const WITHDRAW_FIELDS = ["reason_code", "comment"] as const;

export function WithdrawModal({
  applicationId,
  open,
  onClose,
  version,
}: BaseModalProps & { version: number }) {
  const ids = useId();
  const toast = useToast();
  const withdraw = useWithdraw(applicationId);
  const reasons = useCatalog("application_withdrawal_reason");
  const { control, handleSubmit, setError, reset, formState } = useForm<WithdrawValues>({
    resolver: zodResolver(withdrawSchema),
    defaultValues: { reason_code: "", comment: "" },
  });
  const onError = useFormErrorHandler<WithdrawValues>(setError, WITHDRAW_FIELDS);

  const close = () => {
    reset();
    onClose();
  };

  const submit = handleSubmit((values) => {
    withdraw.mutate(
      {
        reason_code: values.reason_code,
        comment: values.comment.trim(),
        expected_version: version,
      },
      {
        onSuccess: () => {
          toast.success({ title: "Desistimiento registrado" });
          close();
        },
        onError,
      },
    );
  });

  return (
    <Modal
      open={open}
      title="Registrar desistimiento"
      onCancel={close}
      okText="Registrar desistimiento"
      okButtonProps={{ danger: true }}
      cancelText="Cancelar"
      onOk={() => void submit()}
      confirmLoading={withdraw.isPending}
      destroyOnHidden
    >
      <form noValidate onSubmit={(e) => void submit(e)} className="grid gap-4 pt-2">
        <FormField
          id={`${ids}-reason`}
          label="Motivo"
          error={formState.errors.reason_code?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="reason_code"
              render={({ field }) => (
                <Select
                  {...ctl}
                  value={field.value || undefined}
                  onChange={field.onChange}
                  placeholder="Elige un motivo"
                  options={optionsOf(reasons.items)}
                  loading={reasons.isPending}
                  virtual={false}
                />
              )}
            />
          )}
        </FormField>
        <FormField
          id={`${ids}-comment`}
          label="Comentario"
          optional="opcional"
          error={formState.errors.comment?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="comment"
              render={({ field }) => (
                <Input.TextArea {...field} {...ctl} rows={3} maxLength={COMMENT_MAX} />
              )}
            />
          )}
        </FormField>
      </form>
    </Modal>
  );
}

// ---------- reasignación ----------

const assignSchema = z.object({
  advisor_id: z.string({ error: "Elige el asesor." }).min(1, { error: "Elige el asesor." }),
  reason: z.string(),
});
type AssignValues = z.infer<typeof assignSchema>;
const ASSIGN_FIELDS = ["advisor_id", "reason"] as const;

export function ReassignModal({
  applicationId,
  open,
  onClose,
  currentAdvisorId,
}: BaseModalProps & { currentAdvisorId: string }) {
  const ids = useId();
  const toast = useToast();
  const router = useRouter();
  const assign = useAssign(applicationId);
  const advisors = useAdvisors(open);
  const { control, handleSubmit, setError, reset, formState } = useForm<AssignValues>({
    resolver: zodResolver(assignSchema),
    defaultValues: { advisor_id: "", reason: "" },
  });
  const onError = useFormErrorHandler<AssignValues>(setError, ASSIGN_FIELDS);

  const close = () => {
    reset();
    onClose();
  };

  const submit = handleSubmit((values) => {
    assign.mutate(
      { advisor_id: values.advisor_id, reason: values.reason.trim() },
      {
        onSuccess: ({ lostAccess }) => {
          toast.success({ title: "Asesor reasignado" });
          close();
          // Quien reasignó ya no ve la solicitud: vuelve al listado.
          if (lostAccess) router.push("/solicitudes");
        },
        onError,
      },
    );
  });

  const options = (advisors.data ?? [])
    .filter((user) => user.id !== currentAdvisorId)
    .map((user) => ({ value: user.id, label: user.name || user.email }));

  return (
    <Modal
      open={open}
      title="Reasignar asesor"
      onCancel={close}
      okText="Reasignar"
      cancelText="Cancelar"
      onOk={() => void submit()}
      confirmLoading={assign.isPending}
      destroyOnHidden
    >
      <form noValidate onSubmit={(e) => void submit(e)} className="grid gap-4 pt-2">
        <FormField
          id={`${ids}-advisor`}
          label="Asesor"
          error={formState.errors.advisor_id?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="advisor_id"
              render={({ field }) => (
                <Select
                  {...ctl}
                  value={field.value || undefined}
                  onChange={field.onChange}
                  placeholder="Elige un asesor"
                  showSearch={{ optionFilterProp: "label" }}
                  options={options}
                  loading={advisors.isPending}
                  virtual={false}
                />
              )}
            />
          )}
        </FormField>
        <FormField
          id={`${ids}-reason`}
          label="Motivo"
          optional="opcional"
          error={formState.errors.reason?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="reason"
              render={({ field }) => <Input.TextArea {...field} {...ctl} rows={3} />}
            />
          )}
        </FormField>
      </form>
    </Modal>
  );
}

// ---------- enlace del comprador ----------

/** Vigencia del enlace en horas (API §8: 72 por omisión, máximo 168). */
const LINK_HOURS = { min: 1, max: 168, default: 72 } as const;

const linkSchema = z.object({
  delivery_channel: z.string().optional(),
  expires_in_hours: z
    .number({ error: "Escribe la vigencia en horas." })
    .int()
    .min(LINK_HOURS.min, { error: `Mínimo ${LINK_HOURS.min} hora.` })
    .max(LINK_HOURS.max, { error: `Máximo ${LINK_HOURS.max} horas.` }),
});
type LinkValues = z.infer<typeof linkSchema>;
const LINK_FIELDS = ["delivery_channel", "expires_in_hours"] as const;

export function BuyerLinkModal({ applicationId, open, onClose }: BaseModalProps) {
  const ids = useId();
  const toast = useToast();
  const create = useCreateBuyerLink(applicationId);
  const channels = useCatalog("buyer_access_channel");
  const [created, setCreated] = useState<BuyerAccessLinkCreated | null>(null);
  const { control, handleSubmit, setError, reset, formState } = useForm<LinkValues>({
    resolver: zodResolver(linkSchema),
    defaultValues: { delivery_channel: undefined, expires_in_hours: LINK_HOURS.default },
  });
  const onError = useFormErrorHandler<LinkValues>(setError, LINK_FIELDS);

  const close = () => {
    reset();
    setCreated(null);
    onClose();
  };

  const submit = handleSubmit((values) => {
    create.mutate(
      {
        // El canal que se ve elegido: el primero del catálogo si no se cambió. Sin
        // catálogo, la API usa el suyo por omisión.
        ...optional("delivery_channel", values.delivery_channel || channels.items[0]?.code),
        expires_in_hours: values.expires_in_hours,
      },
      { onSuccess: setCreated, onError },
    );
  });

  const copy = async () => {
    if (!created) return;
    try {
      await navigator.clipboard.writeText(created.url);
      toast.success({ title: "Enlace copiado" });
    } catch {
      toast.error({
        title: "No pudimos copiar el enlace",
        message: "Selecciónalo y cópialo a mano.",
      });
    }
  };

  return (
    <Modal
      open={open}
      title="Enviar enlace al comprador"
      onCancel={close}
      destroyOnHidden
      footer={
        created ? (
          <Button type="primary" onClick={close}>
            Listo
          </Button>
        ) : (
          <div className="flex justify-end gap-2">
            <Button onClick={close}>Cancelar</Button>
            <Button type="primary" loading={create.isPending} onClick={() => void submit()}>
              Generar enlace
            </Button>
          </div>
        )
      }
    >
      {created ? (
        <div className="grid gap-3 pt-2">
          <FormField
            id={`${ids}-url`}
            label="Enlace de acceso"
            help={`Sirve una sola vez y vence el ${formatDateTime(created.expires_at) ?? ""}.`}
          >
            {(ctl) => (
              <Input {...ctl} readOnly value={created.url} onFocus={(e) => e.target.select()} />
            )}
          </FormField>
          <div>
            <Button onClick={() => void copy()}>Copiar</Button>
          </div>
        </div>
      ) : (
        <form noValidate onSubmit={(e) => void submit(e)} className="grid gap-4 pt-2">
          <Alert
            type="warning"
            showIcon
            title="El enlace anterior queda revocado"
            description="Si había un enlace sin usar, deja de servir. Las sesiones abiertas del comprador siguen activas."
          />
          <FormField
            id={`${ids}-channel`}
            label="Canal de envío"
            error={formState.errors.delivery_channel?.message}
          >
            {(ctl) => (
              <Controller
                control={control}
                name="delivery_channel"
                render={({ field }) => (
                  <Select
                    {...ctl}
                    value={field.value ?? channels.items[0]?.code}
                    onChange={field.onChange}
                    options={optionsOf(channels.items)}
                    loading={channels.isPending}
                    virtual={false}
                  />
                )}
              />
            )}
          </FormField>
          <FormField
            id={`${ids}-hours`}
            label="Vigencia"
            help={`Entre ${LINK_HOURS.min} y ${LINK_HOURS.max} horas.`}
            error={formState.errors.expires_in_hours?.message}
          >
            {(ctl) => (
              <Controller
                control={control}
                name="expires_in_hours"
                render={({ field }) => (
                  <InputNumber<number>
                    {...ctl}
                    value={field.value}
                    onChange={(v) => field.onChange(v ?? Number.NaN)}
                    min={LINK_HOURS.min}
                    max={LINK_HOURS.max}
                    precision={0}
                    suffix="horas"
                    className="w-40"
                  />
                )}
              />
            )}
          </FormField>
        </form>
      )}
    </Modal>
  );
}
