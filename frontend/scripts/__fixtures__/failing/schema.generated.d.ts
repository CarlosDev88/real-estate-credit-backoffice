export interface paths {
    "/api/v1/auth/me": {
        parameters: {
            query?: never;
        };
        get: operations["auth_me"];
        put?: never;
    };
    "/api/v1/new": {
        parameters: {
            query?: never;
        };
        get?: never;
        post: operations["new_create"];
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        Me: {
            id: string;
            name: string;
        };
        NewThing: {
            y: string;
        };
        Status: "A" | "B" | "C";
    };
    responses: never;
}
export type $defs = Record<string, never>;
export interface operations {
    auth_me: {
        responses: {
            200: components["schemas"]["Me"];
            401: never;
        };
    };
    new_create: {
        responses: {
            201: components["schemas"]["NewThing"];
        };
    };
}
