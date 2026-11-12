import { setupServer } from "msw/node";

/** Servidor MSW de las pruebas: cada prueba agrega sus handlers con `server.use`. */
export const server = setupServer();

export const ORIGIN = "http://localhost:3000";
export const apiUrl = (path: string) => `${ORIGIN}/api/v1${path}`;
