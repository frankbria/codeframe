import SignupForm from "@/components/auth/SignupForm";

/**
 * Signup page
 *
 * Displays the signup form with CodeFRAME branding.
 * Accessible at /signup
 */
export default function SignupPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4 py-12 sm:px-6 lg:px-8">
      <SignupForm />
    </div>
  );
}
