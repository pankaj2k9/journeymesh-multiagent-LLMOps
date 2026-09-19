import { accessToken } from '../auth/tokens';
import { ApiError, apiUrl, request } from './client';

export type MediaCategory = 'blog' | 'destinations' | 'marketing' | 'users' | 'trips';

export const MEDIA_CATEGORIES: MediaCategory[] = [
  'blog',
  'destinations',
  'marketing',
  'users',
  'trips',
];

export interface MediaAsset {
  id: string;
  url: string;
  filename: string;
  original_filename: string;
  category: MediaCategory;
  mime_type: string;
  file_size: number;
  width: number | null;
  height: number | null;
  alt_text: string;
  title: string | null;
  derivatives: Record<string, { url: string; width: number; height: number }>;
  created_at: string | null;
}

export interface MediaList {
  items: MediaAsset[];
  total: number;
}

/** The media library is ADMIN-only on the server; this is just the client. */
export function listMedia(category?: MediaCategory): Promise<MediaList> {
  const query = category ? `?category=${category}` : '';
  return request<MediaList>(`/media${query}`);
}

export function deleteMedia(id: string): Promise<void> {
  return request<void>(`/media/${id}`, { method: 'DELETE' });
}

/**
 * Multipart, so it cannot go through `request`, which always sends JSON.
 * The browser sets the multipart boundary itself when no Content-Type is given.
 */
export async function uploadMedia(
  file: File,
  category: MediaCategory,
  altText: string,
): Promise<MediaAsset> {
  const form = new FormData();
  form.append('file', file);
  form.append('category', category);
  form.append('alt_text', altText);

  const token = accessToken();
  const response = await fetch(apiUrl('/media'), {
    method: 'POST',
    body: form,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  const payload = (await response.json().catch(() => ({}))) as Record<string, unknown>;
  if (!response.ok) {
    throw new ApiError(
      typeof payload.message === 'string' ? payload.message : response.statusText,
      response.status,
      typeof payload.error === 'string' ? payload.error : 'error',
    );
  }
  return payload as unknown as MediaAsset;
}
