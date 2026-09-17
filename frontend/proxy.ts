import { NextRequest, NextResponse } from "next/server";

export function proxy(request: NextRequest) {
  const canonical = new URL(
    process.env.PUBLIC_ORIGIN ||
      process.env.RENDER_EXTERNAL_URL ||
      "http://127.0.0.1:3100",
  );
  if (
    !["GET", "HEAD"].includes(request.method) ||
    !["localhost", "127.0.0.1"].includes(canonical.hostname) ||
    request.nextUrl.protocol !== canonical.protocol
  )
    return NextResponse.next();

  const alias =
    canonical.hostname === "localhost" ? "127.0.0.1" : "localhost";
  const aliasHost = alias + (canonical.port ? `:${canonical.port}` : "");
  if (request.headers.get("host")?.toLowerCase() !== aliasHost)
    return NextResponse.next();

  // OAuth state and session cookies are host-only. Establish the callback's
  // configured host before rendering a page that can start Google sign-in.
  canonical.pathname = request.nextUrl.pathname;
  canonical.search = request.nextUrl.search;
  return NextResponse.redirect(canonical, {
    status: 307,
    headers: { "Cache-Control": "no-store" },
  });
}

export const config = {
  matcher: ["/((?!api(?:/|$)|_next(?:/|$)|.*\\.[^/]+$).*)"],
};
