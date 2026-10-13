import { assertEquals, assertStringIncludes } from "@std/assert";
import { handle as exportHandle } from "./export-events/index.ts";
import { handle as inviteHandle } from "./invite-user/index.ts";
import { csvCell } from "./_shared/csv.ts";

const CLASSROOM = "11111111-1111-4111-8111-111111111111";
const URL_BASE = "https://x.test/functions/v1/export-events";
const range = "from=2026-10-12T00:00:00-05:00&to=2026-10-13T00:00:00-05:00";

// deno-lint-ignore no-explicit-any
function mockClient(
  opts: { user?: boolean; roles?: string[]; events?: any[]; active?: boolean },
) {
  const calls: { rpc: unknown[] } = { rpc: [] };
  const query = {
    // deno-lint-ignore no-explicit-any
    eq(): any { return query; },
    // deno-lint-ignore no-explicit-any
    gte(): any { return query; },
    // deno-lint-ignore no-explicit-any
    lt(): any { return query; },
    // deno-lint-ignore no-explicit-any
    order(): any { return query; },
    range: () => Promise.resolve({ data: opts.events ?? [], error: null }),
  };
  const client = {
    auth: {
      getUser: () =>
        Promise.resolve(
          opts.user === false
            ? { data: { user: null }, error: { message: "bad" } }
            : { data: { user: { id: "u1" } }, error: null },
        ),
    },
    from: (table: string) => {
      if (table === "user_roles") {
        return {
          select: () => ({
            eq: () =>
              Promise.resolve({
                data: (opts.roles ?? []).map((code) => ({ roles: { code } })),
                error: null,
              }),
          }),
        };
      }
      if (table === "profiles") {
        return {
          select: () => ({
            eq: () => ({
              maybeSingle: () =>
                Promise.resolve({
                  data: { is_active: opts.active ?? true },
                  error: null,
                }),
            }),
          }),
        };
      }
      return { select: () => query };
    },
    rpc: (...args: unknown[]) => {
      calls.rpc.push(args);
      return Promise.resolve({ error: null });
    },
  };
  return { client, calls };
}

function exportReq(token?: string, qs = `${range}&classroomId=${CLASSROOM}`) {
  return new Request(`${URL_BASE}?${qs}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
}

Deno.test("export-events: no token -> 401", async () => {
  const { client } = mockClient({});
  const res = await exportHandle(exportReq(), { createUserClient: () => client });
  assertEquals(res.status, 401);
});

Deno.test("export-events: invalid token -> 401", async () => {
  const { client } = mockClient({ user: false });
  const res = await exportHandle(exportReq("bad"), {
    createUserClient: () => client,
  });
  assertEquals(res.status, 401);
});

Deno.test("export-events: viewer -> 403", async () => {
  const { client, calls } = mockClient({ roles: ["viewer"] });
  const res = await exportHandle(exportReq("t"), {
    createUserClient: () => client,
  });
  assertEquals(res.status, 403);
  assertEquals(calls.rpc.length, 0);
});

Deno.test("export-events: inactive teacher -> 403, nothing audited", async () => {
  const { client, calls } = mockClient({ roles: ["teacher"], active: false });
  const res = await exportHandle(exportReq("t"), {
    createUserClient: () => client,
  });
  assertEquals(res.status, 403);
  assertEquals(calls.rpc.length, 0);
});

Deno.test("export-events: teacher -> 200 csv, audited, escaped", async () => {
  const { client, calls } = mockClient({
    roles: ["teacher"],
    events: [
      {
        id: "e1",
        occurred_at: "2026-10-12T13:30:00Z",
        direction: "ENTRY",
        method: "FACE",
        confidence: 0.93,
        students: { full_name: '=HYPERLINK("x"),Ana' },
      },
    ],
  });
  const res = await exportHandle(exportReq("t"), {
    createUserClient: () => client,
  });
  assertEquals(res.status, 200);
  assertStringIncludes(res.headers.get("Content-Type")!, "text/csv");
  const text = await res.text();
  const lines = text.replace("﻿", "").trim().split("\r\n");
  assertEquals(lines[0], "estudiante,direccion,metodo,confianza,fecha_hora_bogota");
  assertEquals(
    lines[1],
    `"'=HYPERLINK(""x""),Ana",ENTRY,FACE,0.93,2026-10-12 08:30:00`,
  );
  assertEquals((calls.rpc[0] as unknown[])[0], "log_access");
});

Deno.test("export-events: validates params -> 400", async () => {
  const { client } = mockClient({ roles: ["admin"] });
  const deps = { createUserClient: () => client };
  assertEquals(
    (await exportHandle(exportReq("t", `${range}&classroomId=nope`), deps)).status,
    400,
  );
  assertEquals(
    (await exportHandle(
      exportReq("t", `from=2026-01-01T00:00:00Z&to=2026-03-01T00:00:00Z&classroomId=${CLASSROOM}`),
      deps,
    )).status,
    400,
  );
  assertEquals(
    (await exportHandle(exportReq("t", `from=yesterday&to=today&classroomId=${CLASSROOM}`), deps))
      .status,
    400,
  );
});

Deno.test("export-events: CORS only for allowed origins", async () => {
  const { client } = mockClient({});
  const deps = { createUserClient: () => client };
  const ok = await exportHandle(
    new Request(URL_BASE, { method: "OPTIONS", headers: { Origin: "http://localhost:5173" } }),
    deps,
  );
  assertEquals(ok.headers.get("Access-Control-Allow-Origin"), "http://localhost:5173");
  const bad = await exportHandle(
    new Request(URL_BASE, { method: "OPTIONS", headers: { Origin: "https://evil.test" } }),
    deps,
  );
  assertEquals(bad.headers.get("Access-Control-Allow-Origin"), null);
});

Deno.test("csvCell: formula injection and quoting", () => {
  assertEquals(csvCell("=1+1"), `"'=1+1"`);
  assertEquals(csvCell("+1"), `"'+1"`);
  assertEquals(csvCell("-1"), `"'-1"`);
  assertEquals(csvCell("@a"), `"'@a"`);
  assertEquals(csvCell('a,"b"'), `"a,""b"""`);
  assertEquals(csvCell("plain"), "plain");
  assertEquals(csvCell(null), "");
});

// ---- invite-user ----

function inviteReq(body: unknown, token?: string) {
  return new Request("https://x.test/functions/v1/invite-user", {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: JSON.stringify(body),
  });
}

function mockAdmin(inviteError: unknown = null) {
  const writes: string[] = [];
  const admin = {
    auth: {
      admin: {
        inviteUserByEmail: () =>
          Promise.resolve(
            inviteError
              ? { data: null, error: inviteError }
              : { data: { user: { id: "new-user" } }, error: null },
          ),
      },
    },
    from: (table: string) => ({
      select: () => ({
        eq: () => ({ single: () => Promise.resolve({ data: { id: 2 }, error: null }) }),
      }),
      upsert: () => {
        writes.push(`upsert ${table}`);
        return Promise.resolve({ error: null });
      },
      delete: () => ({
        eq: () => ({
          neq: () => {
            writes.push(`delete ${table}`);
            return Promise.resolve({ error: null });
          },
        }),
      }),
    }),
  };
  return { admin, writes };
}

Deno.test("invite-user: no token -> 401", async () => {
  const { client } = mockClient({});
  const { admin } = mockAdmin();
  const res = await inviteHandle(inviteReq({ email: "a@b.co", role: "teacher" }), {
    createUserClient: () => client,
    createAdminClient: () => admin,
  });
  assertEquals(res.status, 401);
});

Deno.test("invite-user: teacher -> 403, service client untouched", async () => {
  const { client } = mockClient({ roles: ["teacher"] });
  let adminCreated = false;
  const res = await inviteHandle(inviteReq({ email: "a@b.co", role: "teacher" }, "t"), {
    createUserClient: () => client,
    createAdminClient: () => {
      adminCreated = true;
      return mockAdmin().admin;
    },
  });
  assertEquals(res.status, 403);
  assertEquals(adminCreated, false);
});

Deno.test("invite-user: inactive admin -> 403, service client untouched", async () => {
  const { client } = mockClient({ roles: ["admin"], active: false });
  let adminCreated = false;
  const res = await inviteHandle(inviteReq({ email: "a@b.co", role: "admin" }, "t"), {
    createUserClient: () => client,
    createAdminClient: () => {
      adminCreated = true;
      return mockAdmin().admin;
    },
  });
  assertEquals(res.status, 403);
  assertEquals(adminCreated, false);
});

Deno.test("invite-user: admin -> 200 and role set", async () => {
  const { client } = mockClient({ roles: ["admin"] });
  const { admin, writes } = mockAdmin();
  const res = await inviteHandle(inviteReq({ email: "New@B.co", role: "teacher" }, "t"), {
    createUserClient: () => client,
    createAdminClient: () => admin,
  });
  assertEquals(res.status, 200);
  assertEquals(await res.json(), { userId: "new-user", email: "new@b.co", role: "teacher" });
  assertEquals(writes, ["upsert user_roles", "delete user_roles"]);
});

Deno.test("invite-user: invalid input -> 400", async () => {
  const { client } = mockClient({ roles: ["admin"] });
  const deps = { createUserClient: () => client, createAdminClient: () => mockAdmin().admin };
  assertEquals((await inviteHandle(inviteReq({ email: "nope", role: "teacher" }, "t"), deps)).status, 400);
  assertEquals((await inviteHandle(inviteReq({ email: "a@b.co", role: "root" }, "t"), deps)).status, 400);
});

Deno.test("invite-user: internal errors are not leaked", async () => {
  const { client } = mockClient({ roles: ["admin"] });
  const { admin } = mockAdmin({ message: "SECRET db details", status: 500 });
  const res = await inviteHandle(inviteReq({ email: "a@b.co", role: "viewer" }, "t"), {
    createUserClient: () => client,
    createAdminClient: () => admin,
  });
  assertEquals(res.status, 500);
  const text = await res.text();
  assertEquals(text.includes("SECRET"), false);
});
