import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useLanguage } from '../../hooks/useLanguage';
import type { HotelPreference, Interest, PlanRequestBody, TravelStyle } from '../../types';
import {
  DEFAULT_HOME_COUNTRY,
  FALLBACK_COUNTRIES,
  citiesOf,
  isCityIn,
  type Country,
  type TripScope,
} from '../../utils/cities';
import { CURRENCIES, HOTEL_PREFERENCES } from '../../utils/constants';
import { getSessionId } from '../../utils/session';
import { Button } from '../common/Button';
import { Card } from '../common/Card';
import { Collapsible } from '../common/Collapsible';
import { ChoiceChips } from './ChoiceChips';
import { CityPicker } from './CityPicker';
import { Field, inputClass } from './Field';
import { QuickPrompts } from './QuickPrompts';
import { InterestPicker } from './InterestPicker';
import { TravelStylePicker } from './TravelStylePicker';

export type TripType = 'round' | 'oneway';
export type CabinClass = 'economy' | 'premium_economy' | 'business' | 'first';

const CABINS: CabinClass[] = ['economy', 'premium_economy', 'business', 'first'];
const MAX_TRAVELERS = 20;

const HOTEL_ICONS: Partial<Record<HotelPreference, string>> = {
  hostel: '🛏',
  guesthouse: '🏡',
  three_star: '★',
  four_star: '★★',
  five_star: '★★★',
  apartment: '🏢',
  resort: '🌴',
};

interface PlannerFormProps {
  onSubmit: (body: PlanRequestBody) => void;
  submitting?: boolean;
  /** Called as origin and destination change, so the hero can fly the route. */
  onRouteChange?: (origin: string, destination: string) => void;
  /** Countries and their cities; the live list from `/places` when it has loaded. */
  countries?: Country[];
}

interface FormState {
  query: string;
  homeCountry: string;
  /** Only used for an international trip; a domestic one stays in homeCountry. */
  destinationCountry: string;
  scope: TripScope;
  tripType: TripType;
  cabin: CabinClass | '';
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
  homeCountry: DEFAULT_HOME_COUNTRY,
  destinationCountry: '',
  scope: 'domestic',
  tripType: 'round',
  cabin: '',
  origin: '',
  destination: '',
  departureDate: '',
  returnDate: '',
  travelers: 1,
  budget: '',
  currency: 'INR',
  travelStyle: '',
  hotelPreference: '',
  interests: [],
  specialRequirements: '',
  additionalInstructions: '',
};

const CABIN_TEXT: Record<CabinClass, string> = {
  economy: 'economy',
  premium_economy: 'premium economy',
  business: 'business class',
  first: 'first class',
};

/**
 * The request has no fields for scope, trip type or cabin, so those choices
 * travel as a short structured note the agents already read.
 */
function toCountry(form: FormState): string {
  return form.scope === 'domestic' ? form.homeCountry : form.destinationCountry;
}

function selectionNote(form: FormState): string {
  const parts = [
    `Trip scope: ${form.scope}.`,
    `From country: ${form.homeCountry}.`,
    `Flight: ${form.tripType === 'oneway' ? 'one-way' : 'round trip'}.`,
  ];
  if (toCountry(form)) parts.push(`To country: ${toCountry(form)}.`);
  if (form.cabin) parts.push(`Cabin: ${CABIN_TEXT[form.cabin]}.`);
  return parts.join(' ');
}

/** A description written from the picked options, when none was typed. */
function composedQuery(form: FormState): string {
  const kind = form.tripType === 'oneway' ? 'one-way' : 'round';
  const people = form.travelers === 1 ? '1 traveller' : `${form.travelers} travellers`;
  // Abroad, the country is named too: "Osaka, Japan" is unambiguous where a
  // bare city name sometimes is not.
  const place = (city: string, country: string) =>
    form.scope === 'international' && city ? `${city}, ${country}` : city || country;
  const origin = form.origin.trim();
  const from = origin ? ` from ${place(origin, form.homeCountry)}` : '';
  const to = place(form.destination.trim(), toCountry(form));
  return `Plan a ${kind} ${form.scope} trip${from} to ${to} for ${people}.`;
}

export function PlannerForm({
  onSubmit,
  submitting = false,
  onRouteChange,
  countries = FALLBACK_COUNTRIES,
}: PlannerFormProps) {
  const { t } = useTranslation();
  const { language } = useLanguage();
  const [form, setForm] = useState<FormState>(EMPTY);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const queryRef = useRef<HTMLTextAreaElement>(null);

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  useEffect(() => {
    onRouteChange?.(form.origin, form.destination);
  }, [form.origin, form.destination, onRouteChange]);

  const originCities = citiesOf(countries, form.homeCountry);
  const destinationCities = citiesOf(countries, toCountry(form));
  const otherCountries = countries.filter((country) => country.name !== form.homeCountry);

  // A picked city that no longer belongs to the chosen country is dropped, so
  // a "domestic" trip to Dubai cannot be built by accident. A typed city that
  // is in no list is left alone: the traveller meant it.
  const keepIfValid = (city: string, before: string, after: string) =>
    isCityIn(citiesOf(countries, before), city) && !isCityIn(citiesOf(countries, after), city)
      ? ''
      : city;

  const setHomeCountry = (homeCountry: string) => {
    setForm((current) => {
      const next = {
        ...current,
        homeCountry,
        destinationCountry:
          current.destinationCountry === homeCountry ? '' : current.destinationCountry,
      };
      return {
        ...next,
        origin: keepIfValid(current.origin, current.homeCountry, homeCountry),
        destination: keepIfValid(current.destination, toCountry(current), toCountry(next)),
      };
    });
  };

  const setDestinationCountry = (destinationCountry: string) => {
    setForm((current) => ({
      ...current,
      destinationCountry,
      destination: keepIfValid(current.destination, toCountry(current), destinationCountry),
    }));
  };

  const setScope = (scope: TripScope | '') => {
    if (!scope) return;
    setForm((current) => {
      const next = { ...current, scope };
      return {
        ...next,
        destination: keepIfValid(current.destination, toCountry(current), toCountry(next)),
      };
    });
  };

  // Abroad, swapping the cities swaps the countries with them.
  const swap = () => {
    setForm((current) => ({
      ...current,
      origin: current.destination,
      destination: current.origin,
      ...(current.scope === 'international' && current.destinationCountry
        ? { homeCountry: current.destinationCountry, destinationCountry: current.homeCountry }
        : {}),
    }));
  };

  // An example fills the box and hands the caret back. It never submits: the
  // traveller is expected to edit it into their own trip first.
  const applyQuickPrompt = (prompt: string) => {
    update('query', prompt);
    setErrors((current) => {
      const { query: _removed, ...rest } = current;
      return rest;
    });
    const field = queryRef.current;
    if (field) {
      field.focus();
      window.requestAnimationFrame(() => {
        field.setSelectionRange(prompt.length, prompt.length);
      });
    }
  };

  const validate = useMemo(
    () => (): Record<string, string> => {
      const found: Record<string, string> = {};
      const query = form.query.trim();
      // A picked destination is enough to plan from; the description is then
      // written for the traveller.
      if (
        !query &&
        !form.destination.trim() &&
        !(form.scope === 'international' && form.destinationCountry)
      ) {
        found.query = t('planner.queryOrDestination');
      } else if (query && query.length < 10) {
        found.query = t('planner.queryTooShort');
      }
      if (
        form.tripType === 'round' &&
        form.departureDate &&
        form.returnDate &&
        form.returnDate < form.departureDate
      ) {
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
      query: form.query.trim() || composedQuery(form),
      travelers: form.travelers,
      currency: form.currency,
      interests: form.interests,
      response_language: language,
      session_id: getSessionId(),
    };
    if (form.origin.trim()) body.origin = form.origin.trim();
    if (form.destination.trim()) {
      body.destination = form.destination.trim();
    } else if (form.scope === 'international' && form.destinationCountry) {
      // A country with no city picked is still a destination the agents resolve.
      body.destination = form.destinationCountry;
    }
    if (form.departureDate) body.departure_date = form.departureDate;
    if (form.tripType === 'round' && form.returnDate) body.return_date = form.returnDate;
    if (form.budget) body.budget = Number(form.budget);
    if (form.travelStyle) body.travel_style = form.travelStyle;
    if (form.hotelPreference && form.hotelPreference !== 'any') {
      body.hotel_preference = form.hotelPreference;
    }
    if (form.specialRequirements.trim()) {
      body.special_requirements = form.specialRequirements.trim();
    }
    body.additional_instructions = [selectionNote(form), form.additionalInstructions.trim()]
      .filter(Boolean)
      .join('\n');

    onSubmit(body);
  };

  const stepTitle = (index: number, title: string) => (
    <legend className="flex items-center gap-2 text-sm font-semibold text-ink">
      <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-accent text-xs text-accent-contrast">
        {index}
      </span>
      {title}
    </legend>
  );

  return (
    <Card className="p-5 sm:p-6">
      <form onSubmit={handleSubmit} noValidate className="space-y-7">
        {/* ---- 1. Where ------------------------------------------------ */}
        <fieldset className="space-y-4">
          {stepTitle(1, t('planner.whereTitle'))}

          <div className="grid gap-4 sm:grid-cols-[minmax(0,16rem)_1fr] sm:items-end">
            <Field label={t('planner.homeCountry')} htmlFor="homeCountry">
              <select
                id="homeCountry"
                className={inputClass}
                value={form.homeCountry}
                onChange={(event) => setHomeCountry(event.target.value)}
              >
                {countries.map((country) => (
                  <option key={country.name} value={country.name}>
                    {country.name}
                  </option>
                ))}
              </select>
            </Field>
            <ChoiceChips<TripScope>
              label={t('planner.scope')}
              value={form.scope}
              onChange={setScope}
              allowClear={false}
              choices={[
                { value: 'domestic', label: t('planner.scopeDomestic'), icon: '🏠' },
                { value: 'international', label: t('planner.scopeInternational'), icon: '🌍' },
              ]}
            />
          </div>

          {form.scope === 'international' ? (
            <Field label={t('planner.destinationCountry')} htmlFor="destinationCountry">
              <select
                id="destinationCountry"
                className={`${inputClass} sm:max-w-xs`}
                value={form.destinationCountry}
                onChange={(event) => setDestinationCountry(event.target.value)}
              >
                <option value="">{t('planner.chooseCountry')}</option>
                {otherCountries.map((country) => (
                  <option key={country.name} value={country.name}>
                    {country.name}
                  </option>
                ))}
              </select>
            </Field>
          ) : null}

          <div className="grid gap-4 md:grid-cols-[1fr_auto_1fr] md:items-start">
            <Field label={t('planner.origin')} htmlFor="origin" optional={t('common.optional')}>
              <CityPicker
                id="origin"
                value={form.origin}
                onChange={(value) => update('origin', value)}
                cities={originCities}
                exclude={form.destination}
                placeholder={t('planner.originPlaceholder')}
              />
            </Field>
            <button
              type="button"
              onClick={swap}
              className="jm-chip mx-auto mt-7 h-9 w-9 justify-center rounded-full p-0"
              aria-label={t('planner.swap')}
              title={t('planner.swap')}
            >
              ⇄
            </button>
            <Field
              label={t('planner.destination')}
              htmlFor="destination"
              optional={t('common.optional')}
              error={errors.destination}
            >
              <CityPicker
                id="destination"
                value={form.destination}
                onChange={(value) => update('destination', value)}
                cities={destinationCities}
                exclude={form.origin}
                placeholder={t('planner.destinationPlaceholder')}
                invalid={Boolean(errors.destination)}
              />
              {form.scope === 'international' && !form.destinationCountry ? (
                <p className="mt-1 text-xs text-muted">{t('planner.pickCountryFirst')}</p>
              ) : null}
            </Field>
          </div>
        </fieldset>

        {/* ---- 2. When and who ---------------------------------------- */}
        <fieldset className="space-y-4">
          {stepTitle(2, t('planner.whenTitle'))}

          <ChoiceChips<TripType>
            label={t('planner.tripType')}
            value={form.tripType}
            onChange={(value) => value && update('tripType', value)}
            allowClear={false}
            choices={[
              { value: 'round', label: t('planner.roundTrip'), icon: '⇆' },
              { value: 'oneway', label: t('planner.oneWay'), icon: '→' },
            ]}
          />

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
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
            {form.tripType === 'round' ? (
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
            ) : null}
            <Field label={t('planner.travelers')} htmlFor="travelers">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="jm-chip h-9 w-9 justify-center p-0"
                  aria-label={t('planner.fewerTravelers')}
                  disabled={form.travelers <= 1}
                  onClick={() => update('travelers', Math.max(1, form.travelers - 1))}
                >
                  −
                </button>
                <input
                  id="travelers"
                  type="number"
                  min={1}
                  max={MAX_TRAVELERS}
                  className={`${inputClass} w-16 text-center`}
                  value={form.travelers}
                  onChange={(event) =>
                    update(
                      'travelers',
                      Math.min(MAX_TRAVELERS, Math.max(1, Number(event.target.value) || 1)),
                    )
                  }
                />
                <button
                  type="button"
                  className="jm-chip h-9 w-9 justify-center p-0"
                  aria-label={t('planner.moreTravelers')}
                  disabled={form.travelers >= MAX_TRAVELERS}
                  onClick={() => update('travelers', Math.min(MAX_TRAVELERS, form.travelers + 1))}
                >
                  +
                </button>
              </div>
            </Field>
            <div className="grid grid-cols-3 gap-2">
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

        {/* ---- 3. How ------------------------------------------------- */}
        <fieldset className="space-y-4">
          {stepTitle(3, t('planner.howTitle'))}

          <Field label={t('planner.cabin')} htmlFor="cabin" optional={t('common.optional')}>
            <ChoiceChips<CabinClass>
              id="cabin"
              label={t('planner.cabin')}
              value={form.cabin}
              onChange={(value) => update('cabin', value)}
              choices={CABINS.map((cabin) => ({
                value: cabin,
                label: t(`planner.cabins.${cabin}`),
              }))}
            />
          </Field>

          <Field
            label={t('planner.hotelPreference')}
            htmlFor="hotelPreference"
            optional={t('common.optional')}
          >
            <ChoiceChips<HotelPreference>
              id="hotelPreference"
              label={t('planner.hotelPreference')}
              value={form.hotelPreference}
              onChange={(value) => update('hotelPreference', value)}
              choices={HOTEL_PREFERENCES.filter((item) => item !== 'any').map((item) => ({
                value: item,
                label: t(`hotelPreferences.${item}`),
                icon: HOTEL_ICONS[item],
              }))}
            />
          </Field>

          <Field label={t('planner.travelStyle')} htmlFor="travelStyle">
            <div id="travelStyle">
              <TravelStylePicker
                value={form.travelStyle}
                onChange={(value) => update('travelStyle', value)}
              />
            </div>
          </Field>
        </fieldset>

        {/* ---- 4. In their own words ---------------------------------- */}
        <fieldset className="space-y-3">
          {stepTitle(4, t('planner.describeStepTitle'))}
          <Field
            label={t('planner.describeLabel')}
            htmlFor="query"
            hint={t('planner.describeHelp')}
            error={errors.query}
          >
            <textarea
              ref={queryRef}
              id="query"
              name="query"
              rows={3}
              value={form.query}
              onChange={(event) => update('query', event.target.value)}
              placeholder={t('planner.describePlaceholder')}
              className={`${inputClass} resize-y`}
              aria-invalid={Boolean(errors.query)}
              maxLength={4000}
            />
          </Field>

          <QuickPrompts onSelect={applyQuickPrompt} disabled={submitting} />
        </fieldset>

        <Collapsible
          showLabel={t('planner.advancedToggleOpen')}
          hideLabel={t('planner.advancedToggleClose')}
        >
          <div className="space-y-4">
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
                maxLength={1800}
              />
            </Field>
          </div>
        </Collapsible>

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
