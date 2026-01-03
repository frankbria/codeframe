import { LoginForm } from "@/components/auth/LoginForm";

/**
 * Login page
 *
 * Displays the login form with CodeFRAME branding.
 * Accessible at /login
 */
export default function LoginPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4 py-12 sm:px-6 lg:px-8">
      <LoginForm />
    </div>
  );
}
