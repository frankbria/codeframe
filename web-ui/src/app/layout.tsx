import type { Metadata } from 'next';
import { Nunito_Sans } from 'next/font/google';
import { Toaster } from 'sonner';
import { AppLayout } from '@/components/layout';
import { NotificationProvider } from '@/contexts/NotificationContext';
import './globals.css';

const nunitoSans = Nunito_Sans({
  subsets: ['latin'],
  variable: '--font-nunito-sans',
});

/**
 * Every page is server-rendered per request (#936).
 *
 * The CSP nonce in `src/proxy.ts` is minted per request, and Next.js can only
 * stamp it onto a document it renders at request time — a statically
 * prerendered page keeps whatever was baked in at build time, i.e. no nonce.
 * Measured before adding this: on a static route 0 of 21 scripts carried the
 * nonce (with 'strict-dynamic' and no 'unsafe-inline' that is a blank page);
 * on a dynamic route, 22 of 22 did.
 *
 * The cost is small here because these pages are `'use client'` shells whose
 * prerender is an empty loading skeleton — the data is fetched client-side
 * either way, and the JS/CSS chunks are still served statically from
 * /_next/static, which the proxy matcher skips.
 */
export const dynamic = 'force-dynamic';

export const metadata: Metadata = {
  title: 'CodeFRAME',
  description: 'AI-powered development workflow orchestration',
  manifest: '/site.webmanifest',
  openGraph: {
    title: 'CodeFRAME',
    description: 'AI-powered development workflow orchestration',
    type: 'website',
  },
};

// Note: favicon.ico, icon.png, and apple-icon.png in this directory
// are auto-detected by Next.js App Router (file-based metadata)

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={`${nunitoSans.variable} font-sans antialiased`}>
        <NotificationProvider>
          <AppLayout>{children}</AppLayout>
          <Toaster richColors position="top-right" />
        </NotificationProvider>
      </body>
    </html>
  );
}
