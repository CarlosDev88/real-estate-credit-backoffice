import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

// Validación del login. Va en su propio módulo: el formulario lo carga al validar por primera
// vez (y lo precarga en reposo), así Zod no entra en la primera carga de `/login` (PERF-10).

const schema = z.object({
  email: z
    .string()
    .trim()
    .min(1, { error: "Escribe tu correo." })
    .pipe(z.email({ error: "Escribe un correo válido." })),
  password: z.string().min(1, { error: "Escribe tu contraseña." }),
});

export type LoginValues = z.infer<typeof schema>;

export const loginResolver = zodResolver(schema);
