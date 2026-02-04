import type { Metadata } from 'next';
import { Nunito_Sans } from 'next/font/google';
import './globals.css';

const nunitoSans = Nunito_Sans({
  subsets: ['latin'],
  variable: '--font-nunito-sans',
});

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
        {children}
      </body>
    </html>
  );
}
