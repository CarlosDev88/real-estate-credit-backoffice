export interface paths {
    "/api/v1/auth/me": {
        parameters: {
            query?: never;
        };
        get: operations["auth_me"];
        put?: never;
    };
    "/api/v1/old": {
        parameters: {
            query?: never;
        };
        get: operations["old_list"];
        post?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        Me: {
            id: string;
        };
        Old: {
            x: number;
        };
        Status: "A" | "B";
    };
    responses: never;
}
export type $defs = Record<string, never>;
export interface operations {
    auth_me: {
        responses: {
            200: components["schemas"]["Me"];
        };
    };
    old_list: {
        responses: {
            200: never;
        };
    };
}
