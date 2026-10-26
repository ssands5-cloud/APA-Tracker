import { clerkMiddleware } from '@clerk/nextjs/server';
import { NextResponse, type NextRequest, type NextFetchEvent } from 'next/server';
import { authConfigured } from './lib/auth-config';

const _clerk = clerkMiddleware();

export default function middleware(request: NextRequest, event: NextFetchEvent) {
  // Missing provider configuration never creates keyless auth or a local bypass.
  // The server loader independently denies private reads; public demo remains usable.
  if (!authConfigured()) return NextResponse.next();
  return _clerk(request, event);
}
export const config = { matcher: ['/dashboard/:path*', '/sign-in/:path*'] };
