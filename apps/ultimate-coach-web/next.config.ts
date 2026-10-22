import type { NextConfig } from 'next';

// AES-256-GCM key startup validation.
// Catches misconfigured deployments before the first request, not mid-request.
// Skipped in CI / test environments where the key is intentionally absent.
if (process.env.NODE_ENV === 'production') {
  const rawKey = process.env.UC_SNAPSHOT_KEY ?? '';
  if (!rawKey) {
    console.error('[startup] UC_SNAPSHOT_KEY is not set — snapshot decryption will fail');
  } else {
    const decoded = Buffer.from(rawKey, 'base64');
    if (decoded.length !== 32) {
      // Fatal: wrong key length means every snapshot request will 503.
      throw new Error(
        `[startup] UC_SNAPSHOT_KEY decoded to ${decoded.length} bytes; AES-256 requires exactly 32.`,
      );
    }
  }
}

const config: NextConfig = {
  poweredByHeader: false,
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
