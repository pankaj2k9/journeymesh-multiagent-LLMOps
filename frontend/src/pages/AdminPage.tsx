import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import {
  MEDIA_CATEGORIES,
  deleteMedia,
  listMedia,
  uploadMedia,
  type MediaCategory,
} from '../api/media';
import { useAuth } from '../auth/useAuth';
import { Button } from '../components/common/Button';
import { Callout } from '../components/common/Callout';
import { Card } from '../components/common/Card';
import { EmptyState } from '../components/common/EmptyState';
import { StatCard } from '../components/common/StatCard';
import { inputClass } from '../components/planner/Field';
import { describeApiError } from '../utils/apiError';

const mediaKey = (category: MediaCategory | '') => ['media', category] as const;

/**
 * The administrator's panel. Today that is the media library - the one
 * ADMIN-only surface the API has. Every call here is checked for the ADMIN
 * role on the server; the route guard only keeps the page tidy.
 */
export function AdminPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const [filter, setFilter] = useState<MediaCategory | ''>('');
  const [file, setFile] = useState<File | null>(null);
  const [category, setCategory] = useState<MediaCategory>('blog');
  const [altText, setAltText] = useState('');
  const [formKey, setFormKey] = useState(0);

  const media = useQuery({
    queryKey: mediaKey(filter),
    queryFn: () => listMedia(filter || undefined),
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['media'] });

  const upload = useMutation({
    mutationFn: () => uploadMedia(file as File, category, altText),
    onSuccess: () => {
      setFile(null);
      setAltText('');
      setFormKey((key) => key + 1);
      void refresh();
    },
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteMedia(id),
    onSuccess: () => void refresh(),
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (file) upload.mutate();
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold text-ink sm:text-2xl">{t('admin.title')}</h1>
        <p className="mt-1 text-sm text-muted">{t('admin.subtitle', { email: user?.email })}</p>
      </header>

      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard label={t('admin.mediaTotal')} value={String(media.data?.total ?? '–')} icon="🖼" />
        <StatCard label={t('admin.role')} value={user?.role ?? ''} icon="🛡" />
        <StatCard
          label={t('admin.lastLogin')}
          value={user?.last_login_at ? new Date(user.last_login_at).toLocaleDateString() : '–'}
          icon="⏱"
        />
      </div>

      <Card className="p-5">
        <h2 className="text-base font-semibold text-ink">{t('admin.uploadTitle')}</h2>
        <p className="mt-1 text-sm text-muted">{t('admin.uploadBody')}</p>
        <form
          key={formKey}
          onSubmit={submit}
          className="mt-4 grid gap-3 sm:grid-cols-[2fr_1fr_2fr_auto] sm:items-end"
        >
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-muted">{t('admin.file')}</span>
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              className={inputClass}
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-muted">{t('admin.category')}</span>
            <select
              className={inputClass}
              value={category}
              onChange={(event) => setCategory(event.target.value as MediaCategory)}
            >
              {MEDIA_CATEGORIES.map((item) => (
                <option key={item} value={item}>
                  {t(`admin.categories.${item}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-muted">{t('admin.altText')}</span>
            <input
              className={inputClass}
              value={altText}
              maxLength={300}
              onChange={(event) => setAltText(event.target.value)}
            />
          </label>
          <Button type="submit" loading={upload.isPending} disabled={!file}>
            {t('admin.upload')}
          </Button>
        </form>
        {upload.isError ? (
          <div className="mt-3">
            <Callout tone="danger" title={t('errors.title')}>
              {describeApiError(upload.error, t)}
            </Callout>
          </div>
        ) : null}
      </Card>

      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-base font-semibold text-ink">{t('admin.libraryTitle')}</h2>
          <select
            className={`${inputClass} w-auto`}
            value={filter}
            aria-label={t('admin.category')}
            onChange={(event) => setFilter(event.target.value as MediaCategory | '')}
          >
            <option value="">{t('admin.allCategories')}</option>
            {MEDIA_CATEGORIES.map((item) => (
              <option key={item} value={item}>
                {t(`admin.categories.${item}`)}
              </option>
            ))}
          </select>
        </div>

        {media.isError ? (
          <Callout tone="danger" title={t('errors.title')}>
            {describeApiError(media.error, t)}
          </Callout>
        ) : media.data && media.data.items.length === 0 ? (
          <EmptyState message={t('admin.libraryEmpty')} />
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {media.data?.items.map((asset) => (
              <li
                key={asset.id}
                className="overflow-hidden rounded-2xl border border-line bg-surface shadow-card"
              >
                <img
                  src={asset.derivatives.small?.url ?? asset.url}
                  alt={asset.alt_text}
                  loading="lazy"
                  className="aspect-video w-full bg-elevated object-cover"
                />
                <div className="space-y-2 p-3">
                  <p
                    className="truncate text-sm font-medium text-ink"
                    title={asset.original_filename}
                  >
                    {asset.title || asset.original_filename || asset.filename}
                  </p>
                  <p className="text-xs text-muted">
                    {t(`admin.categories.${asset.category}`)} · {Math.round(asset.file_size / 1024)}{' '}
                    KB
                  </p>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => void navigator.clipboard?.writeText(asset.url)}
                    >
                      {t('admin.copyUrl')}
                    </Button>
                    <Button
                      size="sm"
                      variant="danger"
                      loading={remove.isPending && remove.variables === asset.id}
                      onClick={() => {
                        if (window.confirm(t('admin.confirmDelete'))) remove.mutate(asset.id);
                      }}
                    >
                      {t('admin.delete')}
                    </Button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

export default AdminPage;
