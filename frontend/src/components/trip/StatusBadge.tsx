import { useTranslation } from 'react-i18next';

import type { ReviewStatus, TripStatus } from '../../types';
import { Badge } from '../common/Badge';
import type { BadgeTone } from '../common/Badge';

const TONES: Record<string, BadgeTone> = {
  draft: 'muted',
  awaiting_review: 'neutral',
  revision_in_progress: 'caution',
  changes_requested: 'caution',
  approved: 'positive',
  revision_limit_reached: 'negative',
  failed: 'negative',
  pending: 'muted',
};

interface StatusBadgeProps {
  status: TripStatus | ReviewStatus | string;
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const { t } = useTranslation();
  const key = `status.${status}`;
  const label = t(key);
  return <Badge tone={TONES[status] ?? 'muted'}>{label === key ? status : label}</Badge>;
}
