import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router-dom';

import { ApiError } from '../api/client';
import { Button } from '../components/common/Button';
import { Callout } from '../components/common/Callout';
import { Spinner } from '../components/common/Spinner';
import { ReviewPanel } from '../components/review/ReviewPanel';
import { BudgetSection } from '../components/trip/BudgetSection';
import { EvaluationPanel } from '../components/trip/EvaluationPanel';
import { FlightsSection } from '../components/trip/FlightsSection';
import { HotelsSection } from '../components/trip/HotelsSection';
import { ItinerarySection } from '../components/trip/ItinerarySection';
import { JourneyOverviewCard } from '../components/trip/JourneyOverviewCard';
import { ProviderStatusPanel } from '../components/trip/ProviderStatusPanel';
import { TravelTips } from '../components/trip/TravelTips';
import { WeatherSection } from '../components/trip/WeatherSection';
import { useLanguage } from '../hooks/useLanguage';
import { useApproveTrip, useRequestChanges, useTrip } from '../hooks/useTrips';

const MAX_REVISIONS = 3;

export function TripPage() {
  const { tripId } = useParams<{ tripId: string }>();
  const { t } = useTranslation();
  const { language } = useLanguage();
  const { data: trip, isLoading, isError, error, refetch } = useTrip(tripId);
  const approve = useApproveTrip(tripId ?? '');
  const changes = useRequestChanges(tripId ?? '');
  const [reviewError, setReviewError] = useState<string | null>(null);

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
          <Link to="/history">
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

  return (
    <div className="space-y-6">
      <JourneyOverviewCard trip={trip} />

      <ReviewPanel
        status={trip.review_status}
        revision={trip.revision}
        maxRevisions={MAX_REVISIONS}
        reviews={trip.reviews}
        approving={approve.isPending}
        requesting={changes.isPending}
        errorMessage={reviewError}
        onApprove={() => {
          setReviewError(null);
          approve.mutate({ language }, { onError: handleReviewError });
        }}
        onRequestChanges={(value) => {
          setReviewError(null);
          changes.mutate({ changes: value, language }, { onError: handleReviewError });
        }}
      />

      <FlightsSection flights={journey?.flights ?? trip.flights} />
      <HotelsSection hotels={journey?.hotels ?? trip.hotels} />
      <WeatherSection weather={journey?.weather ?? trip.weather} />
      <BudgetSection budget={journey?.budget ?? trip.budget} />
      <ItinerarySection itinerary={journey?.itinerary ?? trip.itinerary} />
      <TravelTips tips={tips} closingNote={journey?.closing_note} />

      {trip.evaluation ? <EvaluationPanel evaluation={trip.evaluation} /> : null}
      <ProviderStatusPanel statuses={trip.provider_status} />

      <div className="flex flex-wrap gap-2">
        <Link to="/">
          <Button variant="secondary">{t('trip.planAnother')}</Button>
        </Link>
        <Link to="/history">
          <Button variant="ghost">{t('trip.backToHistory')}</Button>
        </Link>
      </div>
    </div>
  );
}

export default TripPage;
