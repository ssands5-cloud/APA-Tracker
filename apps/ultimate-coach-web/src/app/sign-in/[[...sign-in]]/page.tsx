import { ClerkProvider } from '@clerk/nextjs';
import { CaptainSignIn } from '@/components/captain-sign-in';
import { authConfigured } from '@/lib/auth-config';
export const dynamic = 'force-dynamic';
export const revalidate = 0;

export default function SignInPage() {
  if (!authConfigured()) return <main className="auth-page"><h1>Sign-in is being configured</h1>
    <p>The public demo is available. Historical snapshots remain locked until the managed sign-in provider and authorized-viewer list are configured.</p>
    <a className="button" href="/">Open public demo</a></main>;
  return <ClerkProvider><main className="auth-page"><h1>Authorized captain sign-in</h1>
    <p>Invite-only access. A sign-in does not grant permission to historical snapshots.</p>
    <CaptainSignIn/>
    <a className="text-link" href="/">Return to public demo</a></main></ClerkProvider>;
}
