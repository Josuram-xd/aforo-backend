import { createClient } from "@supabase/supabase-js";
import { authenticate, type DbClient } from "../_shared/auth.ts";
import { corsHeaders, jsonResponse } from "../_shared/cors.ts";
import { csvRow, formatBogota } from "../_shared/csv.ts";

const MAX_RANGE_MS = 31 * 24 * 60 * 60 * 1000;
const PAGE_SIZE = 1000;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
// ISO 8601 date-time with an explicit offset or Z.
const ISO_DATETIME =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?(Z|[+-]\d{2}:\d{2})$/;

export interface Deps {
  createUserClient: (authorization: string) => DbClient;
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
};

function parseIso(value: unknown): number | null {
  if (typeof value !== "string" || !ISO_DATETIME.test(value)) return null;
  const ms = Date.parse(value);
  return Number.isNaN(ms) ? null : ms;
}

export async function handle(req: Request, deps: Deps): Promise<Response> {
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: corsHeaders(req) });
  }
  if (req.method !== "GET" && req.method !== "POST") {
    return jsonResponse(req, 405, { error: "Método no permitido." });
  }

  const auth = await authenticate(req, deps.createUserClient, [
    "teacher",
    "admin",
  ]);
  if (auth instanceof Response) return auth;

  // Parameters: query string (GET) or JSON body (POST).
  let params: Record<string, unknown>;
  if (req.method === "GET") {
    params = Object.fromEntries(new URL(req.url).searchParams);
  } else {
    try {
      params = await req.json();
    } catch {
      return jsonResponse(req, 400, { error: "El cuerpo no es JSON válido." });
    }
    if (params === null || typeof params !== "object") {
      return jsonResponse(req, 400, { error: "El cuerpo no es JSON válido." });
    }
  }

  const fromMs = parseIso(params.from);
  const toMs = parseIso(params.to);
  const classroomId = params.classroomId;
  if (fromMs === null || toMs === null) {
    return jsonResponse(req, 400, {
      error: "'from' y 'to' deben ser fechas ISO 8601 con zona horaria.",
    });
  }
  if (toMs <= fromMs) {
    return jsonResponse(req, 400, { error: "'to' debe ser posterior a 'from'." });
  }
  if (toMs - fromMs > MAX_RANGE_MS) {
    return jsonResponse(req, 400, { error: "El rango máximo es de 31 días." });
  }
  if (typeof classroomId !== "string" || !UUID.test(classroomId)) {
    return jsonResponse(req, 400, { error: "'classroomId' debe ser un UUID." });
  }

  const fromIso = new Date(fromMs).toISOString();
  const toIso = new Date(toMs).toISOString();
  const { client } = auth;

  // Audit first: if it cannot be recorded, nothing is exported.
  const { error: auditError } = await client.rpc("log_access", {
    p_action: "EXPORT",
    p_resource: `events classroom=${classroomId} from=${fromIso} to=${toIso}`,
  });
  if (auditError) {
    console.error("log_access failed", auditError.code ?? "");
    return jsonResponse(req, 500, { error: "Error interno." });
  }

  const fetchPage = (offset: number) =>
    client
      .from("events")
      .select("id, occurred_at, direction, method, confidence, students(full_name)")
      .eq("classroom_id", classroomId)
      .gte("occurred_at", fromIso)
      .lt("occurred_at", toIso)
      .order("occurred_at", { ascending: true })
      .order("id", { ascending: true })
      .range(offset, offset + PAGE_SIZE - 1);

  // Fetch the first page before answering so DB errors become a proper 500.
  const first = await fetchPage(0);
  if (first.error) {
    console.error("events query failed", first.error.code ?? "");
    return jsonResponse(req, 500, { error: "Error interno." });
  }

  const encoder = new TextEncoder();
  // deno-lint-ignore no-explicit-any
  const encodeRows = (rows: any[]) =>
    encoder.encode(
      rows.map((e) => {
        const student = Array.isArray(e.students) ? e.students[0] : e.students;
        return csvRow([
          student?.full_name ?? "Desconocido",
          e.direction,
          e.method,
          e.confidence,
          formatBogota(e.occurred_at),
        ]);
      }).join(""),
    );

  let page = first.data ?? [];
  let offset = 0;
  let started = false;
  const stream = new ReadableStream<Uint8Array>({
    async pull(controller) {
      if (!started) {
        started = true;
        controller.enqueue(encoder.encode(
          "﻿" +
            csvRow([
              "estudiante",
              "direccion",
              "metodo",
              "confianza",
              "fecha_hora_bogota",
            ]),
        ));
        return;
      }
      if (page.length === 0) {
        controller.close();
        return;
      }
      controller.enqueue(encodeRows(page));
      if (page.length < PAGE_SIZE) {
        controller.close();
        return;
      }
      offset += PAGE_SIZE;
      const next = await fetchPage(offset);
      if (next.error) {
        console.error("events page failed", next.error.code ?? "");
        controller.error(new Error("page failed"));
        return;
      }
      page = next.data ?? [];
    },
  });

  const day = fromIso.slice(0, 10);
  return new Response(stream, {
    status: 200,
    headers: {
      ...corsHeaders(req),
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="eventos-${day}.csv"`,
      "Cache-Control": "no-store",
    },
  });
}

if (import.meta.main) {
  Deno.serve((req) =>
    handle(req, defaultDeps).catch((err) => {
      console.error("unhandled", err instanceof Error ? err.name : "unknown");
      return jsonResponse(req, 500, { error: "Error interno." });
    })
  );
}
