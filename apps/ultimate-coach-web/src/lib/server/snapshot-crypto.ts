import 'server-only';
import { createDecipheriv } from 'node:crypto';

export function decryptSnapshot(frame: { format: string; iv: string; ciphertext: string }, key: Buffer): string {
  if (key.length !== 32 || frame.format !== 'ultimate-coach-private-snapshot-v1') throw new Error('Invalid private snapshot');
  const encrypted = Buffer.from(frame.ciphertext, 'base64');
  const iv = Buffer.from(frame.iv, 'base64');
  if (iv.length !== 12 || encrypted.length < 16) throw new Error('Invalid private snapshot');
  const decipher = createDecipheriv('aes-256-gcm', key, iv);
  decipher.setAAD(Buffer.from(frame.format));
  decipher.setAuthTag(encrypted.subarray(-16));
  return Buffer.concat([decipher.update(encrypted.subarray(0, -16)), decipher.final()]).toString('utf8');
}
