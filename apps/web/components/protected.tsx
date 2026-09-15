// Wraps a page: shows skeleton while auth resolves, redirects to /login
// when unauthenticated.

"use client";

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { AppShell } from "@/components/shell";
import { CardSkeleton } from "@/components/ui";

function LoginRedirect() {
  const { user, ready } = useAuth();
  const router = useRouter();
  const params = useSearchParams();

  useEffect(() => {
    if (ready && !user) {
      const next = encodeURIComponent(window.location.pathname + (params.toString() ? `?${params.toString()}` : ""));
      router.replace(`/login?next=${next}`);
    }
  }, [ready, user, router, params]);
  return null;
}

export function Protected({ children }: { children: React.ReactNode }) {
  const { user, ready } = useAuth();

  return (
    <Suspense fallback={<PageSkeleton />}>
      <LoginRedirect />
      {!ready || !user ? (
        <PageSkeleton />
      ) : (
        <AppShell>{children}</AppShell>
      )}
    </Suspense>
  );
}

function PageSkeleton() {
  return (
    <div className="mx-auto max-w-3xl space-y-3 p-4" aria-busy="true">
      <CardSkeleton />
      <CardSkeleton />
      <CardSkeleton />
    </div>
  );
}

export function requireRole(user: { role: string } | null, roles: string[]): boolean {
  return !!user && roles.includes(user.role);
}
