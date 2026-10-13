import { createClient } from "@supabase/supabase-js";
import { authenticate, type DbClient, ROLES, type Role } from "../_shared/auth.ts";
import { ALLOWED_ORIGINS, corsHeaders, jsonResponse } from "../_shared/cors.ts";

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Frontend route that finishes the invite (sets the session, asks for a password). */
export const INVITE_CALLBACK_PATH = "/auth/callback";

/**
 * Where the invite e-mail link lands: INVITE_REDIRECT_TO if set, otherwise the
 * caller's frontend (only if it is an allowed origin) or the production
 * frontend, plus /auth/callback. Never an arbitrary caller-supplied URL. The
 * result must be listed in Auth > URL Configuration > Redirect URLs.
 */
export function inviteRedirectTo(req: Request): string {
  const configured = Deno.env.get("INVITE_REDIRECT_TO");
  if (configured) return configured;
  const origin = req.headers.get("Origin");
  const base = origin && ALLOWED_ORIGINS.includes(origin)
    ? origin
    : ALLOWED_ORIGINS[0];
  return base + INVITE_CALLBACK_PATH;
}

export interface Deps {
  createUserClient: (authorization: string) => DbClient;
  /** Service-role client. Only ever created server-side, never returned to callers. */
  createAdminClient: () => DbClient;
}

export const defaultDeps: Deps = {
  createUserClient: (authorization) =>
    createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_ANON_KEY")!,
      {
        global: { headers: { Authorization: authorization } },
        auth: { persistSession: false, autoRefreshToken: false },
      },
    ),
  createAdminClient: () =>
    createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
      { auth: { persistSession: false, autoRefreshToken: false } },
    ),
};

export async function handle(req: Request, deps: Deps): Promise<Response> {
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: corsHeaders(req) });
  }
  if (req.method !== "POST") {
    return jsonResponse(req, 405, { error: "Método no permitido." });
  }

  const auth = await authenticate(req, deps.createUserClient, ["admin"]);
  if (auth instanceof Response) return auth;

  let body: { email?: unknown; role?: unknown };
  try {
    body = await req.json();
  } catch {
    return jsonResponse(req, 400, { error: "El cuerpo no es JSON válido." });
  }
  if (body === null || typeof body !== "object") {
    return jsonResponse(req, 400, { error: "El cuerpo no es JSON válido." });
  }

  const email = typeof body.email === "string"
    ? body.email.trim().toLowerCase()
    : "";
  if (email.length === 0 || email.length > 254 || !EMAIL.test(email)) {
    return jsonResponse(req, 400, { error: "Correo inválido." });
  }
  if (typeof body.role !== "string" || !ROLES.includes(body.role as Role)) {
    return jsonResponse(req, 400, {
      error: "El rol debe ser admin, teacher o viewer.",
    });
  }
  const role = body.role as Role;

  try {
    const admin = deps.createAdminClient();

    const { data: roleRow, error: roleError } = await admin
      .from("roles").select("id").eq("code", role).single();
    if (roleError || !roleRow) throw new Error("role lookup");

    // Only brand-new accounts. Supabase re-sends an invite to an existing but
    // unconfirmed account (e.g. someone else signed up with this e-mail and set
    // the password); granting a role to it would let that person in once the
    // real owner accepts. Role changes for existing users go through set_user_role.
    const { data: existing, error: existingError } = await admin
      .from("profiles").select("id").eq("email", email).maybeSingle();
    if (existingError) throw new Error("profile lookup");
    if (existing) {
      return jsonResponse(req, 409, {
        error: "Ya existe un usuario con ese correo.",
      });
    }

    const { data: invited, error: inviteError } = await admin.auth.admin
      .inviteUserByEmail(email, { redirectTo: inviteRedirectTo(req) });
    if (inviteError) {
      if (inviteError.code === "email_exists" || inviteError.status === 422) {
        return jsonResponse(req, 409, {
          error: "Ya existe un usuario con ese correo.",
        });
      }
      throw new Error("invite");
    }
    const userId: string | undefined = invited?.user?.id;
    if (!userId) throw new Error("invite without user");

    // The signup trigger gives every new user the 'viewer' role; replace it.
    const { error: upsertError } = await admin.from("user_roles").upsert(
      { user_id: userId, role_id: roleRow.id, granted_by: auth.userId },
      { onConflict: "user_id,role_id" },
    );
    if (upsertError) throw new Error("role upsert");
    const { error: cleanError } = await admin.from("user_roles")
      .delete().eq("user_id", userId).neq("role_id", roleRow.id);
    if (cleanError) throw new Error("role cleanup");

    return jsonResponse(req, 200, { userId, email, role });
  } catch (err) {
    // Log only a short step label: never the error object, keys or emails.
    console.error(
      "invite-user failed:",
      err instanceof Error ? err.message : "unknown",
    );
    return jsonResponse(req, 500, {
      error: "No se pudo invitar al usuario. Intenta de nuevo.",
    });
  }
}

if (import.meta.main) {
  Deno.serve((req) =>
    handle(req, defaultDeps).catch(() =>
      jsonResponse(req, 500, { error: "Error interno." })
    )
  );
}
