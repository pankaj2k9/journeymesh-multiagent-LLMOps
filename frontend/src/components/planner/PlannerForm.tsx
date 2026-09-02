import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useLanguage } from '../../hooks/useLanguage';
import type { HotelPreference, Interest, PlanRequestBody, TravelStyle } from '../../types';
import { CURRENCIES, HOTEL_PREFERENCES } from '../../utils/constants';
import { getSessionId } from '../../utils/session';
import { Button } from '../common/Button';
import { Card } from '../common/Card';
import { Field, inputClass } from './Field';
import { InterestPicker } from './InterestPicker';
import { TravelStylePicker } from './TravelStylePicker';

interface PlannerFormProps {
  onSubmit: (body: PlanRequestBody) => void;
  submitting?: boolean;
}

interface FormState {
  query: string;
  origin: string;
  destination: string;
  departureDate: string;
  returnDate: string;
  travelers: number;
  budget: string;
  currency: string;
  travelStyle: TravelStyle | '';
  hotelPreference: HotelPreference | '';
  interests: Interest[];
  specialRequirements: string;
  additionalInstructions: string;
}

const EMPTY: FormState = {
  query: '',
  origin: '',
  destination: '',
  departureDate: '',
  returnDate: '',
  travelers: 1,
  budget: '',
  currency: 'USD',
  travelStyle: '',
  hotelPreference: '',
  interests: [],
  specialRequirements: '',
  additionalInstructions: '',
};

export function PlannerForm({ onSubmit, submitting = false }: PlannerFormProps) {
  const { t } = useTranslation();
  const { language } = useLanguage();
  const [form, setForm] = useState<FormState>(EMPTY);
  const [showDetails, setShowDetails] = useState(true);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const validate = useMemo(
    () => (): Record<string, string> => {
      const found: Record<string, string> = {};
      const query = form.query.trim();
      if (!query) {
        found.query = t('planner.queryRequired');
      } else if (query.length < 10) {
        found.query = t('planner.queryTooShort');
      }
      if (form.departureDate && form.returnDate && form.returnDate < form.departureDate) {
        found.returnDate = t('planner.dateOrderError');
      }
      if (form.budget && Number(form.budget) < 0) {
        found.budget = t('planner.budgetError');
      }
      if (
        form.origin.trim() &&
        form.destination.trim() &&
        form.origin.trim().toLowerCase() === form.destination.trim().toLowerCase()
      ) {
        found.destination = t('planner.sameCityError');
      }
      return found;
    },
    [form, t],
  );

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const found = validate();
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    const body: PlanRequestBody = {
      query: form.query.trim(),
      travelers: form.travelers,
      currency: form.currency,
      interests: form.interests,
      response_language: language,
      session_id: getSessionId(),
    };
    if (form.origin.trim()) body.origin = form.origin.trim();
    if (form.destination.trim()) body.destination = form.destination.trim();
    if (form.departureDate) body.departure_date = form.departureDate;
    if (form.returnDate) body.return_date = form.returnDate;
    if (form.budget) body.budget = Number(form.budget);
    if (form.travelStyle) body.travel_style = form.travelStyle;
    if (form.hotelPreference && form.hotelPreference !== 'any') {
      body.hotel_preference = form.hotelPreference;
    }
    if (form.specialRequirements.trim()) {
      body.special_requirements = form.specialRequirements.trim();
    }
    if (form.additionalInstructions.trim()) {
      body.additional_instructions = form.additionalInstructions.trim();
    }

    onSubmit(body);
  };

  return (
    <Card className="p-5 sm:p-6">
      <form onSubmit={handleSubmit} noValidate className="space-y-6">
        <Field
          label={t('planner.describeLabel')}
          htmlFor="query"
          hint={t('planner.describeHelp')}
          error={errors.query}
        >
          <textarea
            id="query"
            name="query"
            rows={4}
            value={form.query}
            onChange={(event) => update('query', event.target.value)}
            placeholder={t('planner.describePlaceholder')}
            className={`${inputClass} resize-y`}
            aria-invalid={Boolean(errors.query)}
            maxLength={4000}
          />
        </Field>

        <div>
          <button
            type="button"
            onClick={() => setShowDetails((value) => !value)}
            aria-expanded={showDetails}
            className="text-sm font-medium text-mesh-700 hover:underline"
          >
            {showDetails ? t('planner.advancedToggleClose') : t('planner.advancedToggleOpen')}
          </button>
        </div>

        {showDetails ? (
          <div className="space-y-6">
            <fieldset className="space-y-4">
              <legend className="text-sm font-semibold text-journey-ink">
                {t('planner.detailsTitle')}
              </legend>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field
                  label={t('planner.origin')}
                  htmlFor="origin"
                  optional={t('common.optional')}
                >
                  <input
                    id="origin"
                    className={inputClass}
                    value={form.origin}
                    onChange={(event) => update('origin', event.target.value)}
                    placeholder={t('planner.originPlaceholder')}
                    maxLength={120}
                  />
                </Field>
                <Field
                  label={t('planner.destination')}
                  htmlFor="destination"
                  optional={t('common.optional')}
                  error={errors.destination}
                >
                  <input
                    id="destination"
                    className={inputClass}
                    value={form.destination}
                    onChange={(event) => update('destination', event.target.value)}
                    placeholder={t('planner.destinationPlaceholder')}
                    maxLength={120}
                  />
                </Field>
                <Field
                  label={t('planner.departureDate')}
                  htmlFor="departureDate"
                  optional={t('common.optional')}
                >
                  <input
                    id="departureDate"
                    type="date"
                    className={inputClass}
                    value={form.departureDate}
                    onChange={(event) => update('departureDate', event.target.value)}
                  />
                </Field>
                <Field
                  label={t('planner.returnDate')}
                  htmlFor="returnDate"
                  optional={t('common.optional')}
                  error={errors.returnDate}
                >
                  <input
                    id="returnDate"
                    type="date"
                    className={inputClass}
                    value={form.returnDate}
                    min={form.departureDate || undefined}
                    onChange={(event) => update('returnDate', event.target.value)}
                  />
                </Field>
                <Field label={t('planner.travelers')} htmlFor="travelers">
                  <input
                    id="travelers"
                    type="number"
                    min={1}
                    max={20}
                    className={inputClass}
                    value={form.travelers}
                    onChange={(event) =>
                      update('travelers', Math.max(1, Number(event.target.value) || 1))
                    }
                  />
                </Field>
                <div className="grid grid-cols-3 gap-3">
                  <Field
                    label={t('planner.budget')}
                    htmlFor="budget"
                    optional={t('common.optional')}
                    error={errors.budget}
                    className="col-span-2"
                  >
                    <input
                      id="budget"
                      type="number"
                      min={0}
                      step={50}
                      className={inputClass}
                      value={form.budget}
                      onChange={(event) => update('budget', event.target.value)}
                      placeholder={t('planner.budgetPlaceholder')}
                    />
                  </Field>
                  <Field label={t('planner.currency')} htmlFor="currency">
                    <select
                      id="currency"
                      className={inputClass}
                      value={form.currency}
                      onChange={(event) => update('currency', event.target.value)}
                    >
                      {CURRENCIES.map((code) => (
                        <option key={code} value={code}>
                          {code}
                        </option>
                      ))}
                    </select>
                  </Field>
                </div>
              </div>
            </fieldset>

            <fieldset className="space-y-4">
              <legend className="text-sm font-semibold text-journey-ink">
                {t('planner.preferencesTitle')}
              </legend>

              <Field label={t('planner.travelStyle')} htmlFor="travelStyle">
                <div id="travelStyle">
                  <TravelStylePicker
                    value={form.travelStyle}
                    onChange={(value) => update('travelStyle', value)}
                  />
                </div>
              </Field>

              <Field
                label={t('planner.hotelPreference')}
                htmlFor="hotelPreference"
                optional={t('common.optional')}
              >
                <select
                  id="hotelPreference"
                  className={inputClass}
                  value={form.hotelPreference}
                  onChange={(event) =>
                    update('hotelPreference', event.target.value as HotelPreference | '')
                  }
                >
                  <option value="">{t('hotelPreferences.any')}</option>
                  {HOTEL_PREFERENCES.filter((item) => item !== 'any').map((item) => (
                    <option key={item} value={item}>
                      {t(`hotelPreferences.${item}`)}
                    </option>
                  ))}
                </select>
              </Field>

              <Field label={t('planner.interests')} htmlFor="interests">
                <div id="interests">
                  <InterestPicker
                    value={form.interests}
                    onChange={(value) => update('interests', value)}
                  />
                </div>
              </Field>

              <Field
                label={t('planner.specialRequirements')}
                htmlFor="specialRequirements"
                optional={t('common.optional')}
              >
                <textarea
                  id="specialRequirements"
                  rows={2}
                  className={`${inputClass} resize-y`}
                  value={form.specialRequirements}
                  onChange={(event) => update('specialRequirements', event.target.value)}
                  placeholder={t('planner.specialRequirementsPlaceholder')}
                  maxLength={1000}
                />
              </Field>

              <Field
                label={t('planner.additionalInstructions')}
                htmlFor="additionalInstructions"
                optional={t('common.optional')}
              >
                <textarea
                  id="additionalInstructions"
                  rows={2}
                  className={`${inputClass} resize-y`}
                  value={form.additionalInstructions}
                  onChange={(event) => update('additionalInstructions', event.target.value)}
                  placeholder={t('planner.additionalInstructionsPlaceholder')}
                  maxLength={2000}
                />
              </Field>
            </fieldset>
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" size="lg" loading={submitting}>
            {submitting ? t('planner.submitting') : t('planner.submit')}
          </Button>
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              setForm(EMPTY);
              setErrors({});
            }}
          >
            {t('planner.reset')}
          </Button>
        </div>
      </form>
    </Card>
  );
}
