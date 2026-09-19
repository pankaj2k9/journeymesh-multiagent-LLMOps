import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router-dom';

import { Button } from '../components/common/Button';
import { BLOG_POSTS, findPost, type BlogBlock } from '../content/blog';
import { NotFoundPage } from './NotFoundPage';
import { PostCover, formatPostDate } from './BlogPage';

function Block({ block }: { block: BlogBlock }) {
  switch (block.type) {
    case 'h2':
      return <h2 className="mt-8 text-lg font-semibold text-ink">{block.text}</h2>;
    case 'ul':
      return (
        <ul className="mt-3 list-disc space-y-1.5 pl-5 text-ink">
          {block.items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      );
    case 'tip':
      return (
        <p className="mt-6 rounded-xl border border-brand-line bg-brand-bg px-4 py-3 text-sm text-brand-fg">
          {block.text}
        </p>
      );
    default:
      return <p className="mt-4 leading-relaxed text-ink">{block.text}</p>;
  }
}

export function BlogPostPage() {
  const { t, i18n } = useTranslation();
  const { slug } = useParams();
  const post = findPost(slug);

  useEffect(() => {
    if (post) document.title = `${post.title} · ${t('app.name')}`;
  }, [post, t]);

  if (!post) return <NotFoundPage />;

  const more = BLOG_POSTS.filter((item) => item.slug !== post.slug).slice(0, 2);

  return (
    <article className="mx-auto max-w-3xl">
      <Link to="/blog" className="text-sm font-medium text-accent hover:underline">
        ← {t('blog.back')}
      </Link>

      <header className="jm-rise mt-4">
        <p className="text-xs font-medium text-accent">{post.category}</p>
        <h1 className="text-balance mt-1 text-2xl font-bold text-ink sm:text-4xl">{post.title}</h1>
        <p className="mt-2 text-sm text-muted">
          {formatPostDate(post.published, i18n.language)} ·{' '}
          {t('blog.readTime', { count: post.readMinutes })}
        </p>
      </header>

      <div className="mt-6 overflow-hidden rounded-2xl border border-line shadow-card">
        <PostCover post={post} large />
      </div>

      <div className="mt-6 text-base">
        <p className="text-lg text-muted">{post.excerpt}</p>
        {post.body.map((block, index) => (
          <Block key={index} block={block} />
        ))}
      </div>

      <div className="mt-10 rounded-2xl border border-line bg-surface p-5 shadow-card">
        <p className="font-semibold text-ink">{t('blog.ctaTitle')}</p>
        <p className="mt-1 text-sm text-muted">{t('blog.ctaBody')}</p>
        <Link to="/#planner" className="mt-3 inline-block">
          <Button>{t('home.heroCta')}</Button>
        </Link>
      </div>

      {more.length > 0 ? (
        <section className="mt-10">
          <h2 className="text-base font-semibold text-ink">{t('blog.more')}</h2>
          <ul className="mt-3 grid gap-3 sm:grid-cols-2">
            {more.map((item) => (
              <li key={item.slug}>
                <Link
                  to={`/blog/${item.slug}`}
                  className="block rounded-xl border border-line bg-surface p-4 transition hover:-translate-y-0.5 hover:shadow-card"
                >
                  <span aria-hidden="true">{item.emoji}</span>{' '}
                  <span className="font-medium text-ink">{item.title}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </article>
  );
}

export default BlogPostPage;
