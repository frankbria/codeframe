"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "@/lib/auth-client";

/**
 * Protected route wrapper component
 *
 * Checks if user is authenticated and redirects to login page if not.
 * Shows loading spinner while checking authentication status.
 *
 * Usage:
 *   <ProtectedRoute>
 *     <YourProtectedContent />
 *   </ProtectedRoute>
 */
export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { data: session, isPending } = useSession();

  useEffect(() => {
    if (!isPending && !session) {
      // Redirect to login if not authenticated
      router.push("/login");
    }
  }, [session, isPending, router]);

  // Show loading spinner while checking auth
  if (isPending) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-center">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-primary border-r-transparent"></div>
          <p className="mt-4 text-muted-foreground">Loading...</p>
        </div>
      </div>
    );
  }

  // Don't render children if not authenticated (will redirect)
  if (!session) {
    return null;
  }

  // Render protected content
  return <>{children}</>;
}
