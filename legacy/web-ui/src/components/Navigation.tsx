"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";

/**
 * Navigation bar component
 *
 * Displays navigation with conditional rendering based on authentication status:
 * - When logged in: Shows user email and "Logout" button
 * - When logged out: Shows "Login" and "Signup" links
 */
export default function Navigation() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, isLoading, logout } = useAuth();

  // Don't show navigation on login/signup pages
  if (pathname === "/login" || pathname === "/signup") {
    return null;
  }

  const handleLogout = async () => {
    await logout();
    router.push("/login");
  };

  return (
    <nav className="bg-card shadow-sm border-b border-border">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          <div className="flex items-center">
            <Link href="/" className="flex items-center">
              <span className="text-xl font-bold text-foreground">CodeFRAME</span>
            </Link>
          </div>

          <div className="flex items-center space-x-4">
            {isLoading ? (
              <div className="text-sm text-muted-foreground">Loading...</div>
            ) : user ? (
              <>
                <div data-testid="user-menu">
                  <span className="text-sm text-foreground">
                    {user.name || user.email}
                  </span>
                </div>
                <button
                  onClick={handleLogout}
                  data-testid="logout-button"
                  className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-primary-foreground bg-primary hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary"
                >
                  Logout
                </button>
              </>
            ) : (
              <>
                <Link
                  href="/login"
                  className="text-sm font-medium text-foreground hover:text-foreground/80"
                >
                  Login
                </Link>
                <Link
                  href="/signup"
                  className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-primary-foreground bg-primary hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary"
                >
                  Signup
                </Link>
              </>
            )}
          </div>
        </div>
      </div>
    </nav>
  );
}
