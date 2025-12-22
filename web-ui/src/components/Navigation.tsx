"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useSession, signOut } from "@/lib/auth-client";

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
  const { data: session, isPending } = useSession();

  // Don't show navigation on login/signup pages
  if (pathname === "/login" || pathname === "/signup") {
    return null;
  }

  const handleLogout = async () => {
    await signOut();
    router.push("/login");
  };

  return (
    <nav className="bg-white shadow-sm border-b border-gray-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          <div className="flex items-center">
            <Link href="/" className="flex items-center">
              <span className="text-xl font-bold text-gray-900">CodeFRAME</span>
            </Link>
          </div>

          <div className="flex items-center space-x-4">
            {isPending ? (
              <div className="text-sm text-gray-500">Loading...</div>
            ) : session ? (
              <>
                <span className="text-sm text-gray-700">
                  {session.user.name || session.user.email}
                </span>
                <button
                  onClick={handleLogout}
                  className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                >
                  Logout
                </button>
              </>
            ) : (
              <>
                <Link
                  href="/login"
                  className="text-sm font-medium text-gray-700 hover:text-gray-900"
                >
                  Login
                </Link>
                <Link
                  href="/signup"
                  className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
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
