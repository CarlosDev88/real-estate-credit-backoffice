"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Input, Select } from "antd";
import { useEffect, useId, useState } from "react";
import type { ReactNode } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { ActionModal } from "@/components/ui/action-modal";
import { FormField, useFormErrorHandler, type FieldControlProps } from "@/components/ui/form-field";
import { useCatalog } from "@/features/dashboard/queries";
import { fromLocalInput, toLocalInput } from "@/features/filings/local-datetime";
import {
  DEFAULT_PRIORITY,
  useApplicationOptions,
  useCancelTask,
  useCompleteTask,
  useCreateTask,
  useUpdateTask,
  type Task,
  type TaskCreateRequest,
  type TaskUpdateRequest,
  type WorkdayApplication,
} from "@/features/workday/queries";
import { useToast } from "@/providers/toast";

/** Límites del contrato (`TaskCreateRequest`, `TaskCancelRequest`). */
export const TITLE_MAX = 180;
export const DESCRIPTION_MAX = 4000;
export const REASON_MAX = 1000;
const PRIORITY_CATALOG = "task_priority";

/** Persona a quien se puede asignar una tarea (el usuario actual y los asesores). */
export interface Assignee {
  id: string;
  name: string;
}

/** Solicitud a la que queda vinculada una tarea nueva. */
export interface TaskTarget {
  id: string;
  code: string;
  client_display_name: string;
}

const targetLabel = (t: TaskTarget) => `${t.code} · ${t.client_display_name}`;

function ReadOnlyField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-1.5">
      <span className="text-sm font-medium">{label}</span>
      <div className="bg-bg-subtle border-border-default rounded-md border px-3 py-1.5 text-sm">
        {children}
      </div>
    </div>
  );
}

// ---------- crear y editar ----------

const formSchema = z.object({
  title: z
    .string()
    .trim()
    .min(1, { error: "Escribe el título." })
    .max(TITLE_MAX, { error: `Máximo ${TITLE_MAX} caracteres.` }),
  description: z.string().max(DESCRIPTION_MAX, { error: `Máximo ${DESCRIPTION_MAX} caracteres.` }),
  due_at: z
    .string()
    .refine((v) => v === "" || fromLocalInput(v) !== null, { error: "Fecha y hora inválidas." }),
  priority_code: z.string(),
  application_id: z.string(),
  assigned_to_id: z.string(),
});
type FormValues = z.infer<typeof formSchema>;
const FORM_FIELDS = [
  "title",
  "description",
  "due_at",
  "priority_code",
  "application_id",
  "assigned_to_id",
] as const;

/** Busca solicitudes para vincular la tarea (espera 300 ms entre teclas). */
function ApplicationPicker({
  value,
  onChange,
  control,
}: {
  value: string;
  onChange: (value: string) => void;
  control: FieldControlProps;
}) {
  const [text, setText] = useState("");
  const [term, setTerm] = useState("");
  useEffect(() => {
    const id = setTimeout(() => setTerm(text.trim()), 300);
    return () => clearTimeout(id);
  }, [text]);
  const options = useApplicationOptions(term, true);
  return (
    <Select
      {...control}
      showSearch={{ filterOption: false, onSearch: setText }}
      value={value || undefined}
      onChange={onChange}
      placeholder="Busca por código, nombre o cédula"
      notFoundContent={options.isFetching ? "Buscando…" : "Sin resultados"}
      loading={options.isFetching}
      virtual={false}
      options={(options.data ?? []).map((a: WorkdayApplication) => ({
        value: a.id,
        label: targetLabel(a),
      }))}
    />
  );
}

interface TaskFormModalProps {
  open: boolean;
  onClose: () => void;
  /** Editar esta tarea; sin ella, se crea una nueva. */
  task?: Task | null;
  /** Al crear desde una fila de la bandeja, la solicitud ya está elegida. */
  target?: TaskTarget | null;
  /** Personas a quien asignar (solo el administrador); vacío: no se ofrece el campo. */
  assignees: Assignee[];
  meId: string;
}

/** Crear o editar una tarea: título, descripción, vencimiento, prioridad y responsable. */
export function TaskFormModal({
  open,
  onClose,
  task,
  target,
  assignees,
  meId,
}: TaskFormModalProps) {
  const ids = useId();
  const toast = useToast();
  const create = useCreateTask();
  const update = useUpdateTask();
  const priorities = useCatalog(PRIORITY_CATALOG);
  const editing = !!task;

  const defaults = (): FormValues => ({
    title: task?.title ?? "",
    description: task?.description ?? "",
    due_at: task?.due_at ? toLocalInput(new Date(task.due_at)) : "",
    priority_code: task?.priority.code ?? DEFAULT_PRIORITY,
    application_id: target?.id ?? "",
    assigned_to_id: task?.assigned_to.id ?? meId,
  });

  const { control, handleSubmit, setError, reset, formState } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: defaults(),
  });
  const onError = useFormErrorHandler<FormValues>(setError, FORM_FIELDS);

  // Cada vez que se abre, con los datos de la tarea o de la fila elegida.
  useEffect(() => {
    if (open) reset(defaults());
    // eslint-disable-next-line react-hooks/exhaustive-deps -- solo al abrir
  }, [open, task?.id, target?.id]);

  const submit = handleSubmit((values) => {
    const due_at = values.due_at ? fromLocalInput(values.due_at) : null;
    const assigned =
      assignees.length > 0 && values.assigned_to_id
        ? { assigned_to_id: values.assigned_to_id }
        : {};
    if (editing && task) {
      const body: TaskUpdateRequest = {
        title: values.title.trim(),
        description: values.description.trim(),
        due_at,
        ...(values.priority_code ? { priority_code: values.priority_code } : {}),
        ...assigned,
      };
      update.mutate(
        { id: task.id, body },
        {
          onSuccess: () => {
            toast.success({ title: "Tarea actualizada" });
            onClose();
          },
          onError,
        },
      );
      return;
    }
    if (!values.application_id) {
      setError("application_id", { type: "required", message: "Elige la solicitud." });
      return;
    }
    const body: TaskCreateRequest = {
      title: values.title.trim(),
      application_id: values.application_id,
      ...(values.description.trim() ? { description: values.description.trim() } : {}),
      ...(due_at ? { due_at } : {}),
      ...(values.priority_code ? { priority_code: values.priority_code } : {}),
      ...assigned,
    };
    create.mutate(body, {
      onSuccess: () => {
        toast.success({ title: "Tarea creada" });
        onClose();
      },
      onError,
    });
  });

  return (
    <ActionModal
      open={open}
      title={editing ? "Editar tarea" : "Nueva tarea"}
      description={
        editing
          ? undefined
          : "La tarea queda vinculada a la solicitud y aparece en la bandeja del responsable."
      }
      okText={editing ? "Guardar cambios" : "Crear tarea"}
      loading={create.isPending || update.isPending}
      onSubmit={submit}
      onCancel={onClose}
    >
      {editing ? (
        task.parent && (
          <ReadOnlyField label="Vinculada a">
            {task.parent.type_label}
            {task.parent.code ? ` ${task.parent.code}` : ""} · {task.parent.client_display_name}
          </ReadOnlyField>
        )
      ) : target ? (
        <ReadOnlyField label="Solicitud">{targetLabel(target)}</ReadOnlyField>
      ) : (
        <FormField
          id={`${ids}-application`}
          label="Solicitud"
          error={formState.errors.application_id?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="application_id"
              render={({ field }) => (
                <ApplicationPicker value={field.value} onChange={field.onChange} control={ctl} />
              )}
            />
          )}
        </FormField>
      )}

      <FormField id={`${ids}-title`} label="Título" error={formState.errors.title?.message}>
        {(ctl) => (
          <Controller
            control={control}
            name="title"
            render={({ field }) => <Input {...field} {...ctl} maxLength={TITLE_MAX} />}
          />
        )}
      </FormField>

      <FormField
        id={`${ids}-description`}
        label="Descripción"
        optional="opcional"
        error={formState.errors.description?.message}
      >
        {(ctl) => (
          <Controller
            control={control}
            name="description"
            render={({ field }) => (
              <Input.TextArea {...field} {...ctl} rows={3} maxLength={DESCRIPTION_MAX} />
            )}
          />
        )}
      </FormField>

      <div className="grid gap-4 min-[600px]:grid-cols-2">
        <FormField
          id={`${ids}-due`}
          label="Vence"
          optional="opcional"
          error={formState.errors.due_at?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="due_at"
              render={({ field }) => <Input {...field} {...ctl} type="datetime-local" />}
            />
          )}
        </FormField>
        <FormField
          id={`${ids}-priority`}
          label="Prioridad"
          error={formState.errors.priority_code?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="priority_code"
              render={({ field }) => (
                <Select
                  {...ctl}
                  value={field.value || undefined}
                  onChange={field.onChange}
                  options={priorities.items.map((p) => ({ value: p.code, label: p.label }))}
                  loading={priorities.isPending}
                  virtual={false}
                />
              )}
            />
          )}
        </FormField>
      </div>

      {assignees.length > 0 && (
        <FormField
          id={`${ids}-assignee`}
          label="Responsable"
          error={formState.errors.assigned_to_id?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="assigned_to_id"
              render={({ field }) => (
                <Select
                  {...ctl}
                  value={field.value || undefined}
                  onChange={field.onChange}
                  options={assignees.map((a) => ({ value: a.id, label: a.name }))}
                  virtual={false}
                />
              )}
            />
          )}
        </FormField>
      )}
    </ActionModal>
  );
}

// ---------- completar ----------

export function CompleteTaskModal({ task, onClose }: { task: Task | null; onClose: () => void }) {
  const toast = useToast();
  const complete = useCompleteTask();
  return (
    <ActionModal
      open={!!task}
      title="Completar tarea"
      description={task ? `"${task.title}" queda como completada.` : undefined}
      okText="Completar"
      loading={complete.isPending}
      onSubmit={() => {
        if (!task) return;
        complete.mutate(task.id, {
          onSuccess: () => {
            toast.success({ title: "Tarea completada" });
            onClose();
          },
          // El error (por ejemplo, `409 TASK_NOT_PENDING`) va al toast global.
          onError: () => onClose(),
        });
      }}
      onCancel={onClose}
    />
  );
}

// ---------- cancelar ----------

const cancelSchema = z.object({
  reason: z
    .string()
    .trim()
    .min(1, { error: "Escribe el motivo." })
    .max(REASON_MAX, { error: `Máximo ${REASON_MAX} caracteres.` }),
});
type CancelValues = z.infer<typeof cancelSchema>;

export function CancelTaskModal({ task, onClose }: { task: Task | null; onClose: () => void }) {
  const ids = useId();
  const toast = useToast();
  const cancel = useCancelTask();
  const { control, handleSubmit, setError, reset, formState } = useForm<CancelValues>({
    resolver: zodResolver(cancelSchema),
    defaultValues: { reason: "" },
  });
  const onError = useFormErrorHandler<CancelValues>(setError, ["reason"]);

  const close = () => {
    reset({ reason: "" });
    onClose();
  };

  const submit = handleSubmit((values) => {
    if (!task) return;
    cancel.mutate(
      { id: task.id, reason: values.reason.trim() },
      {
        onSuccess: () => {
          toast.success({ title: "Tarea cancelada" });
          close();
        },
        onError,
      },
    );
  });

  return (
    <ActionModal
      open={!!task}
      title="Cancelar tarea"
      description={task ? `"${task.title}" deja de estar pendiente.` : undefined}
      okText="Cancelar tarea"
      cancelText="Volver"
      danger
      loading={cancel.isPending}
      onSubmit={submit}
      onCancel={close}
    >
      <FormField id={`${ids}-reason`} label="Motivo" error={formState.errors.reason?.message}>
        {(ctl) => (
          <Controller
            control={control}
            name="reason"
            render={({ field }) => (
              <Input.TextArea {...field} {...ctl} rows={3} maxLength={REASON_MAX} />
            )}
          />
        )}
      </FormField>
    </ActionModal>
  );
}
