import type { Metadata } from 'next';
import { SessionDetailClient } from './SessionDetailClient';

interface PageProps {
  params: Promise<{ id: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { id } = await params;
  const shortId = id.slice(-8);
  return { title: `Session #${shortId} — CodeFRAME` };
}

export default async function SessionDetailPage({ params }: PageProps) {
  const { id } = await params;
  return <SessionDetailClient sessionId={id} />;
}
