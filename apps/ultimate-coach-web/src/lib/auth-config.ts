/** Environment names only. Never import server configuration into a client component. */
export function authConfigured(): boolean {
  return /^pk_(live|test)_/.test(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ?? '')
    && /^sk_(live|test)_/.test(process.env.CLERK_SECRET_KEY ?? '');
}
