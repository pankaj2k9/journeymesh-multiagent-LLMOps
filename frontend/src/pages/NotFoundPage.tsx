import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { Button } from '../components/common/Button';

export function NotFoundPage() {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-center gap-4 py-16 text-center">
      <h1 className="text-2xl font-semibold text-ink">{t('errors.notFound')}</h1>
      <Link to="/">
        <Button>{t('errors.goHome')}</Button>
      </Link>
    </div>
  );
}

export default NotFoundPage;
