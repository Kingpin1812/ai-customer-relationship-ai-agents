import type { NextRequest } from "next/server";

// Reads BACKEND_URL per request: next.config rewrites are fixed at build time, which breaks images
// and any setup where the API address is only known at run time.
export const dynamic = "force-dynamic";

const HOP_BY_HOP = new Set(["connection", "content-length", "host", "transfer-encoding", "keep-alive"]);
const STRIP_FROM_RESPONSE = new Set([...HOP_BY_HOP, "content-encoding"]);

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
  const target = `${backend}/api/v1/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;

  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) headers.set(key, value);
  });

  const hasBody = !["GET", "HEAD"].includes(request.method);
  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? request.body : undefined,
      redirect: "manual",
      cache: "no-store",
      ...(hasBody ? { duplex: "half" } : {}),
    } as RequestInit);
    const responseHeaders = new Headers();
    upstream.headers.forEach((value, key) => {
      if (!STRIP_FROM_RESPONSE.has(key.toLowerCase())) responseHeaders.set(key, value);
    });
    return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
  } catch {
    return Response.json(
      {
        error: {
          category: "provider_server_error",
          message: "The server could not be reached. Check that it is running.",
          correlation_id: null,
        },
      },
      { status: 502 },
    );
  }
}

export { proxy as GET, proxy as POST, proxy as PATCH, proxy as PUT, proxy as DELETE };
