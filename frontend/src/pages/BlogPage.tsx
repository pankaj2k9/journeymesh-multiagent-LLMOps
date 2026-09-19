import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { BLOG_POSTS, type BlogPost } from '../content/blog';

function PostCover({ post, large = false }: { post: BlogPost; large?: boolean }) {
  if (post.cover) {
    return (
      <img
        src={post.cover}
        alt=""
        loading="lazy"
        className={`w-full object-cover ${large ? 'aspect-[2/1]' : 'aspect-video'}`}
      />
    );
  }
  return (
    <div
      className={`jm-hero flex w-full items-center justify-center rounded-none border-0 shadow-none ${
        large ? 'aspect-[2/1] text-6xl' : 'aspect-video text-4xl'
      }`}
      aria-hidden="true"
    >
      <span className="jm-float">{post.emoji}</span>
    </div>
  );
}

export function formatPostDate(iso: string, language: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(language, {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

export function BlogPage() {
  const { t, i18n } = useTranslation();
  const categories = Array.from(new Set(BLOG_POSTS.map((post) => post.category)));
  const [category, setCategory] = useState<string>('');

  const posts = category ? BLOG_POSTS.filter((post) => post.category === category) : BLOG_POSTS;

  return (
    <div className="space-y-6">
      <header className="jm-rise">
        <h1 className="text-2xl font-bold text-ink sm:text-3xl">{t('blog.title')}</h1>
        <p className="mt-1 text-sm text-muted sm:text-base">{t('blog.subtitle')}</p>
      </header>

      <div className="flex flex-wrap gap-2" role="group" aria-label={t('blog.filter')}>
        <button
          type="button"
          className="jm-chip"
          aria-pressed={category === ''}
          onClick={() => setCategory('')}
        >
          {t('blog.all')}
        </button>
        {categories.map((item) => (
          <button
            key={item}
            type="button"
            className="jm-chip"
            aria-pressed={category === item}
            onClick={() => setCategory(item)}
          >
            {item}
          </button>
        ))}
      </div>

      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {posts.map((post, index) => (
          <li key={post.slug} className="jm-rise" style={{ animationDelay: `${index * 70}ms` }}>
            <Link
              to={`/blog/${post.slug}`}
              className="group flex h-full flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-card transition hover:-translate-y-1 hover:shadow-raised"
            >
              <PostCover post={post} />
              <div className="flex flex-1 flex-col p-4">
                <p className="text-xs font-medium text-accent">{post.category}</p>
                <h2 className="mt-1 text-base font-semibold text-ink group-hover:text-accent">
                  {post.title}
                </h2>
                <p className="mt-2 flex-1 text-sm text-muted">{post.excerpt}</p>
                <p className="mt-3 text-xs text-faint">
                  {formatPostDate(post.published, i18n.language)} ·{' '}
                  {t('blog.readTime', { count: post.readMinutes })}
                </p>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

export { PostCover };
export default BlogPage;
