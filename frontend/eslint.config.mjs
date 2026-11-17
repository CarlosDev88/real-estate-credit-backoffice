import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import storybook from "eslint-plugin-storybook";
import tseslint from "typescript-eslint";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  // Reglas de los stories (CSF) y de .storybook/main.ts.
  ...storybook.configs["flat/recommended"],
  {
    files: ["**/*.{ts,tsx,mts}"],
    languageOptions: {
      parser: tseslint.parser,
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      // Promesas olvidadas: errores de red que nadie maneja.
      "@typescript-eslint/no-floating-promises": "error",
      "@typescript-eslint/no-misused-promises": "error",
      "@typescript-eslint/consistent-type-imports": "error",
    },
  },
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "coverage/**",
    "playwright-report/**",
    "test-results/**",
    ".ci-report/**",
    "storybook-static/**",
    // Salidas de ejemplo de las herramientas para las pruebas del reporte del CI.
    "scripts/__fixtures__/**",
    "next-env.d.ts",
    // Generado por `pnpm api:gen` desde ../contracts/openapi.json.
    "src/lib/api/schema.d.ts",
  ]),
]);
