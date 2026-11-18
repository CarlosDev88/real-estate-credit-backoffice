// Acciones del flujo de validación de un proyecto. La API dice cuáles puede hacer el
// usuario ahora (`ProjectDetail.available_actions`, códigos de las transiciones de
// `workflow-transitions`, flujo `PROJECT`); aquí solo se decide a qué endpoint va cada
// una y cómo se confirma. La API no manda la etiqueta de la transición (brecha anotada):
// el texto copia el de las transiciones sembradas.

export type ProjectEndpoint = "submit" | "activate" | "reject" | "archive";

export interface ProjectAction {
  endpoint: ProjectEndpoint;
  /** Texto del botón. */
  label: string;
  /** Título del modal de confirmación. */
  title: string;
  /** Qué pasa al confirmar. */
  description: string;
  /** El contrato exige motivo (`ReasonRequest`) o lo deja opcional. */
  reasonRequired: boolean;
  danger: boolean;
  /** Botón principal del panel (la acción que se espera en ese estado). */
  primary: boolean;
  toast: string;
}

const SUBMIT: ProjectAction = {
  endpoint: "submit",
  label: "Enviar a validación",
  title: "Enviar a validación",
  description:
    "El proyecto pasa a validación: un asesor lo revisa y lo aprueba o lo devuelve a borrador.",
  reasonRequired: false,
  danger: false,
  primary: true,
  toast: "Proyecto enviado a validación",
};

const APPROVE: ProjectAction = {
  endpoint: "activate",
  label: "Aprobar",
  title: "Aprobar proyecto",
  description: "El proyecto queda activo y ya puede recibir oportunidades.",
  reasonRequired: false,
  danger: false,
  primary: true,
  toast: "Proyecto aprobado",
};

const ARCHIVE: ProjectAction = {
  endpoint: "archive",
  label: "Archivar",
  title: "Archivar proyecto",
  description: "El proyecto deja de estar disponible y ya no se puede editar.",
  reasonRequired: true,
  danger: true,
  primary: false,
  toast: "Proyecto archivado",
};

/** Código de la transición → acción. Los códigos desconocidos no se muestran. */
export const PROJECT_ACTIONS: Readonly<Record<string, ProjectAction>> = {
  SUBMIT_FOR_REVIEW: SUBMIT,
  APPROVE,
  APPROVE_DRAFT: {
    ...APPROVE,
    label: "Aprobar sin enviar a validación",
    primary: false,
  },
  REJECT: {
    endpoint: "reject",
    label: "Rechazar",
    title: "Rechazar proyecto",
    description: "El proyecto vuelve a borrador para que la constructora lo corrija.",
    reasonRequired: true,
    danger: true,
    primary: false,
    toast: "Proyecto devuelto a borrador",
  },
  ARCHIVE_DRAFT: ARCHIVE,
  ARCHIVE_PENDING: ARCHIVE,
  ARCHIVE_ACTIVE: ARCHIVE,
};

/** Acciones disponibles, en el orden de la API y sin repetir el mismo destino. */
export function actionsFor(codes: readonly string[]): ProjectAction[] {
  const seen = new Set<string>();
  const out: ProjectAction[] = [];
  for (const code of codes) {
    const action = PROJECT_ACTIONS[code];
    if (!action || seen.has(action.label)) continue;
    seen.add(action.label);
    out.push(action);
  }
  return out;
}
