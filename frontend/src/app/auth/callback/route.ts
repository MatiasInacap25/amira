import { NextResponse, type NextRequest } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { safeNextPath } from "@/lib/auth/safe-next-path";

export async function GET(request: NextRequest) {
  const next = safeNextPath(request.nextUrl.searchParams.get("next"));
  const code = request.nextUrl.searchParams.get("code");
  const error = request.nextUrl.searchParams.get("error");

  if (error || !code) {
    return NextResponse.redirect(new URL("/login?message=confirmation", request.url));
  }

  const supabase = await createClient();
  const { error: exchangeError } = await supabase.auth.exchangeCodeForSession(code);
  if (exchangeError) {
    return NextResponse.redirect(new URL("/login?message=confirmation", request.url));
  }

  const { data, error: userError } = await supabase.auth.getUser();
  if (userError || !data.user?.email_confirmed_at) {
    await supabase.auth.signOut();
    return NextResponse.redirect(new URL("/login?message=confirmation", request.url));
  }

  return NextResponse.redirect(new URL(next, request.url));
}
