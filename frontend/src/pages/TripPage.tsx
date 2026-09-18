import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams, useSearchParams } from 'react-router-dom';

import { ApiError } from '../api/client';
import { BudgetTab } from '../components/budget/BudgetTab';
import { Button } from '../components/common/Button';
import { Callout } from '../components/common/Callout';
import { Card } from '../components/common/Card';
import { Collapsible } from '../components/common/Collapsible';
import { EmptyState } from '../components/common/EmptyState';
import { Spinner } from '../components/common/Spinner';
import { TabPanel, Tabs, type TabDefinition } from '../components/common/Tabs';
import { ReviewPanel } from '../components/review/ReviewPanel';
import { BudgetSection } from '../components/trip/BudgetSection';
import { EvaluationPanel } from '../components/trip/EvaluationPanel';
import { FlightsSection } from '../components/trip/FlightsSection';
import { HotelsSection } from '../components/trip/HotelsSection';
import { ItinerarySection } from '../components/trip/ItinerarySection';
import { JourneyOverviewCard } from '../components/trip/JourneyOverviewCard';
import { PlanActions } from '../components/trip/PlanActions';
import { ProviderStatusPanel } from '../components/trip/ProviderStatusPanel';
import { SupervisorPlanCard } from '../components/trip/SupervisorPlanCard';
import { TravelTips } from '../components/trip/TravelTips';
import { WeatherSection } from '../components/trip/WeatherSection';
import { useLanguage } from '../hooks/useLanguage';
import { useApproveTrip, useRequestChanges, useTrip } from '../hooks/useTrips';

const MAX_REVISIONS = 3;

/**
 * Tabs that exist now, and tabs whose content arrives in a later phase.
 *
 * The placeholders are deliberate: the trip dashboard's shape is part of the
 * product, and introducing four new tabs later would move everything a
 * traveller had learned the position of. An empty tab that says what will be
 * there is more honest than a tab strip that keeps changing length.
 */
const TAB_IDS = [
  'overview',
  'flights',
  'hotels',
  'activities',
  'itinerary',
  'budget',
  'bookings',
  'documents',
  'travelers',
  'assistant',
] as const;

type TabId = (typeof TAB_IDS)[number];

const PLACEHOLDER_TABS: TabId[] = ['bookings', 'documents', 'travelers', 'assistant'];

function isTabId(value: string | null): value is TabId {
  return value !== null && (TAB_IDS as readonly string[]).includes(value);
}

export function TripPage() {
  const { tripId } = useParams<{ tripId: string }>();
  const { t } = useTranslation();
  const { language } = useLanguage();
  const [searchParams, setSearchParams] = useSearchParams();
  const { data: trip, isLoading, isError, error, refetch } = useTrip(tripId);
  const approve = useApproveTrip(tripId ?? '');
  const changes = useRequestChanges(tripId ?? '');
  const [reviewError, setReviewError] = useState<string | null>(null);

  // The tab lives in the query string so a link can open a journey straight on
  // its budget, and so the browser's back button steps between tabs the way a
  // traveller expects.
  const requested = searchParams.get('tab');
  const active: TabId = isTabId(requested) ? requested : 'overview';
  const setActive = (id: string) => {
    const next = new URLSearchParams(searchParams);
    if (id === 'overview') next.delete('tab');
    else next.set('tab', id);
    setSearchParams(next, { replace: true });
  };

  if (isLoading) {
    return <Spinner label={t('common.loading')} />;
  }

  if (isError || !trip) {
    const notFound = error instanceof ApiError && error.isNotFound;
    return (
      <div className="space-y-4">
        <Callout tone="danger" title={t('errors.title')}>
          {notFound ? t('trip.notFound') : t('errors.network')}
        </Callout>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => void refetch()}>
            {t('errors.retry')}
          </Button>
          <Link to="/dashboard">
            <Button variant="ghost">{t('trip.backToHistory')}</Button>
          </Link>
        </div>
      </div>
    );
  }

  const journey = trip.final_journey;
  const tips = journey?.travel_tips?.length ? journey.travel_tips : trip.itinerary.travel_tips;

  const handleReviewError = (err: unknown) => {
    if (err instanceof ApiError) {
      if (err.isRevisionLimit) {
        setReviewError(t('errors.revisionLimit'));
        return;
      }
      if (err.isRateLimited) {
        setReviewError(t('errors.rateLimited'));
        return;
      }
      setReviewError(err.message || t('errors.title'));
      return;
    }
    setReviewError(t('errors.title'));
  };

  const runApprove = () => {
    setReviewError(null);
    approve.mutate({ language }, { onError: handleReviewError });
  };

  const runRequestChanges = (value: string) => {
    setReviewError(null);
    changes.mutate({ changes: value, language }, { onError: handleReviewError });
  };

  // A revision or an approval replaces every section below, so the whole plan
  // is marked busy while one is in flight. The spinner always resolves: the
  // mutation settles either way and the error is shown with a retry.
  const busy = approve.isPending || changes.isPending;

  const tabs: TabDefinition[] = TAB_IDS.map((id) => ({
    id,
    label: t(`tripTabs.${id}`),
  }));

  return (
    <div className="space-y-5">
      <JourneyOverviewCard trip={trip} />

      <div className="border-b border-line">
        <Tabs tabs={tabs} active={active} onChange={setActive} ariaLabel={t('tripTabs.aria')} />
      </div>

      <TabPanel id="overview" active={active}>
        <div className="space-y-6">
          <SupervisorPlanCard trip={trip} />

          <ReviewPanel
            status={trip.review_status}
            revision={trip.revision}
            maxRevisions={MAX_REVISIONS}
            reviews={trip.reviews}
            approving={approve.isPending}
            requesting={changes.isPending}
            errorMessage={reviewError}
            onApprove={runApprove}
            onRequestChanges={runRequestChanges}
            onRetry={() => {
              setReviewError(null);
              void refetch();
            }}
          />

          <Card className="p-5 sm:p-6">
            <PlanActions trip={trip} />
            {busy ? (
              <Spinner
                label={approve.isPending ? t('review.approving') : t('review.submittingChanges')}
                className="py-6"
              />
            ) : null}
          </Card>

          <div
            aria-busy={busy || undefined}
            className={`space-y-6 transition-opacity ${busy ? 'opacity-60' : ''}`.trim()}
          >
            <WeatherSection weather={journey?.weather ?? trip.weather} />
            <BudgetSection budget={journey?.budget ?? trip.budget} />
            <TravelTips tips={tips} closingNote={journey?.closing_note} />
          </div>

          <div className="print:hidden">
            <Collapsible
              showLabel={t('trip.showTechnical')}
              hideLabel={t('trip.hideTechnical')}
              summary={<p className="text-sm text-muted">{t('trip.technicalSummary')}</p>}
            >
              <div className="space-y-6">
                {trip.evaluation ? <EvaluationPanel evaluation={trip.evaluation} /> : null}
                <ProviderStatusPanel statuses={trip.provider_status} />
              </div>
            </Collapsible>
          </div>
        </div>
      </TabPanel>

      <TabPanel id="flights" active={active}>
        <FlightsSection flights={journey?.flights ?? trip.flights} />
      </TabPanel>

      <TabPanel id="hotels" active={active}>
        <HotelsSection hotels={journey?.hotels ?? trip.hotels} />
      </TabPanel>

      <TabPanel id="activities" active={active}>
        <ItinerarySection itinerary={journey?.itinerary ?? trip.itinerary} />
      </TabPanel>

      <TabPanel id="itinerary" active={active}>
        <ItinerarySection itinerary={journey?.itinerary ?? trip.itinerary} />
      </TabPanel>

      <TabPanel id="budget" active={active}>
        {tripId ? <BudgetTab tripId={tripId} /> : null}
      </TabPanel>

      {PLACEHOLDER_TABS.map((id) => (
        <TabPanel key={id} id={id} active={active}>
          <EmptyState message={t(`tripTabs.placeholder.${id}`)} />
        </TabPanel>
      ))}

      <div className="flex flex-wrap gap-2 print:hidden">
        <Link to="/">
          <Button variant="secondary">{t('trip.planAnother')}</Button>
        </Link>
        <Link to="/dashboard">
          <Button variant="ghost">{t('trip.backToHistory')}</Button>
        </Link>
      </div>
    </div>
  );
}

export default TripPage;
