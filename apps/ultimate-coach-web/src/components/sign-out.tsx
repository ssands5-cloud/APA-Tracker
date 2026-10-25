'use client';
import { SignOutButton } from '@clerk/nextjs';
export function SignOut() {
  return <SignOutButton redirectUrl="/"><button className="button" type="button">Sign out</button></SignOutButton>;
}
