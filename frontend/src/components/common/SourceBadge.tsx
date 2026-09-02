import { useTranslation } from 'react-i18next';

import type { DataSource } from '../../types';
import { sourceTone } from '../../utils/format';
import { Badge } from './Badge';

interface SourceBadgeProps {
  source: DataSource;
  className?: string;
}

/**
 * Shows where a value came from. JourneyMesh never presents an estimate as a
 * live price, so this badge is deliberately impossible to miss.
 */
export function SourceBadge({ source, className }: SourceBadgeProps) {
  const { t } = useTranslation();
  return (
    <Badge tone={sourceTone(source)} title={t(`source.explain${source}`)} className={className}>
      {t(`source.${source}`)}
    </Badge>
  );
}
