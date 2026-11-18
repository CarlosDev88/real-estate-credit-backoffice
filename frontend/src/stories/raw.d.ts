// Importación de un archivo como texto (Vite y Vitest): `import css from "./x.css?raw"`.
declare module "*?raw" {
  const content: string;
  export default content;
}
