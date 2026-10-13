import { jsonResponse } from "./cors.ts";

export type Role = "admin" | "teacher" | "viewer";
export const ROLES: readonly Role[] = ["admin", "teacher", "viewer"];

// Minimal surface of the supabase-js client that we use; lets tests inject mocks.
// deno-lint-ignore no-explicit-any
export type DbClient = any;

export interface AuthContext {
  userId: string;
  roles: Role[];
  client: DbClient; // created with the caller's JWT, so RLS applies
}

/**
 * Authenticates the caller from the Authorization header and loads the roles
 * (read through RLS with the caller's own JWT). Inactive accounts get 403.
 * Returns a Response (401/403/500) when the request must stop, otherwise the
 * AuthContext.
 */
export async function authenticate(
  req: Request,
  createUserClient: (authorization: string) => DbClient,
  allowedRoles: readonly Role[],
): Promise<AuthContext | Response> {
  const authorization = req.headers.get("Authorization") ?? "";
  const match = /^Bearer\s+(\S+)$/i.exec(authorization);
  if (!match) {
    return jsonResponse(req, 401, { error: "Falta el token de autenticación." });
  }

  const client = createUserClient(`Bearer ${match[1]}`);

  const { data: userData, error: userError } = await client.auth.getUser(
    match[1],
  );
  if (userError || !userData?.user?.id) {
    return jsonResponse(req, 401, { error: "Token inválido o vencido." });
  }
  const userId: string = userData.user.id;

  const { data: rows, error: rolesError } = await client
    .from("user_roles")
    .select("roles(code)")
    .eq("user_id", userId);
  if (rolesError) {
    console.error("roles lookup failed", rolesError.code ?? "");
    return jsonResponse(req, 500, { error: "Error interno." });
  }

  // A deactivated account keeps reading its own user_roles rows through RLS, so the
  // role alone is not enough: require profiles.is_active as the database does.
  const { data: profile, error: profileError } = await client
    .from("profiles")
    .select("is_active")
    .eq("id", userId)
    .maybeSingle();
  if (profileError) {
    console.error("profile lookup failed", profileError.code ?? "");
    return jsonResponse(req, 500, { error: "Error interno." });
  }
  if (profile?.is_active !== true) {
    return jsonResponse(req, 403, { error: "Tu cuenta está desactivada." });
  }

  const roles: Role[] = [];
  // deno-lint-ignore no-explicit-any
  for (const row of (rows ?? []) as any[]) {
    const code = Array.isArray(row.roles) ? row.roles[0]?.code : row.roles?.code;
    if (ROLES.includes(code)) roles.push(code);
  }

  if (!roles.some((r) => allowedRoles.includes(r))) {
    return jsonResponse(req, 403, {
      error: "No tienes permisos para esta acción.",
    });
  }
  return { userId, roles, client };
}
