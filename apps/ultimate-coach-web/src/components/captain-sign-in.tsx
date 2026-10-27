'use client';
import { SignIn, useAuth } from '@clerk/nextjs';
import { SignOut } from './sign-out';

export function CaptainSignIn() {
  const { isLoaded, isSignedIn } = useAuth();
  if (!isLoaded) return <p role="status">Checking your sign-in…</p>;
  if (isSignedIn) return <div>
    <p role="status">Clerk has signed you in. Open the historical dashboard to check your access.</p>
    <p><a className="button" href="/dashboard">Open historical dashboard</a></p>
    <p>If the dashboard returns you here, sign out and sign in again to renew this browser’s session.</p>
    <SignOut/>
  </div>;
  return <SignIn routing="path" path="/sign-in" forceRedirectUrl="/dashboard" signUpUrl="/access-denied"/>;
}
