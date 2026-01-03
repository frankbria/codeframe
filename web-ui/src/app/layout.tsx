/**
 * Root layout
 */

import type { Metadata } from 'next';
import { Nunito_Sans } from 'next/font/google';
import { AuthProvider } from '@/contexts/AuthContext';
import './globals.css';
import Navigation from '@/components/Navigation';

const nunitoSans = Nunito_Sans({
  subsets: ['latin'],
  variable: '--font-sans',
});

export const metadata: Metadata = {
  title: 'CodeFRAME Status Server',
  description: 'Real-time monitoring for autonomous AI coding agents',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={`${nunitoSans.variable} antialiased font-sans`}>
        <AuthProvider>
            <Navigation />
            {children}
        </AuthProvider>
      </body>
    </html>
  );
}
