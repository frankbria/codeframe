import { NextResponse } from 'next/server'

export async function GET() {
  return NextResponse.json({
    status: 'healthy',
    service: 'codeframe-frontend',
    timestamp: new Date().toISOString()
  })
}
