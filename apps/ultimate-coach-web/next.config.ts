import type { NextConfig } from 'next';

const config: NextConfig = {
  poweredByHeader: false,
  outputFileTracingIncludes: { '/dashboard/[[...section]]': ['./private-snapshots/historical.enc.json'] },
  async headers() {
    return [{ source: '/:path*', headers: [
      { key: 'X-Content-Type-Options', value: 'nosniff' },
      { key: 'Referrer-Policy', value: 'no-referrer' },
      { key: 'X-Frame-Options', value: 'DENY' },
      { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
      { key: 'Content-Security-Policy', value: "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'" },
      { key: 'X-Robots-Tag', value: 'noindex, nofollow' },
    ] }, ...['/dashboard/:path*', '/sign-in/:path*', '/access-denied'].map(source => ({ source, headers: [
      { key: 'Cache-Control', value: 'private, no-store, max-age=0' },
      { key: 'CDN-Cache-Control', value: 'no-store' },
      { key: 'Vercel-CDN-Cache-Control', value: 'no-store' },
    ] }))];
  },
};
export default config;
