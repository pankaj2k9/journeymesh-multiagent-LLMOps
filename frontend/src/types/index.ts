/**
 * Types mirroring the JourneyMesh API contract (backend/app/schemas).
 */

export type LanguageCode = 'en' | 'bn' | 'hi';

export type DataSource = 'LIVE' | 'SEARCH_DERIVED' | 'ESTIMATE' | 'UNAVAILABLE';

export type ReviewStatus =
  | 'pending'
  | 'awaiting_review'
  | 'approved'
  | 'changes_requested'
  | 'revision_in_progress'
  | 'revision_limit_reached';

export type TripStatus =
  | 'draft'
  | 'awaiting_review'
  | 'revision_in_progress'
  | 'approved'
  | 'failed'
  | 'rejected';

export type BudgetStatus =
  | 'within_budget'
  | 'near_limit'
  | 'over_budget'
  | 'insufficient_data';

export type TravelStyle =
  | 'budget'
  | 'comfort'
  | 'luxury'
  | 'adventure'
  | 'family'
  | 'business'
  | 'relaxed';

export type HotelPreference =
  | 'any'
  | 'hostel'
  | 'guesthouse'
  | 'three_star'
  | 'four_star'
  | 'five_star'
  | 'apartment'
  | 'resort';

export type Interest =
  | 'food'
  | 'nature'
  | 'history'
  | 'culture'
  | 'shopping'
  | 'beaches'
  | 'nightlife'
  | 'photography'
  | 'technology'
  | 'family_activities';

export interface Provenance {
  source: DataSource;
  provider?: string | null;
  retrieved_at?: string | null;
  note?: string | null;
}

export interface ProviderStatus {
  provider: string;
  kind: 'flights' | 'hotels' | 'weather' | 'search' | 'llm';
  ok: boolean;
  source: DataSource;
  latency_ms?: number | null;
  message?: string | null;
  retrieved_at: string;
}

export interface AirportMatch {
  city: string;
  iata?: string | null;
  name?: string | null;
  country?: string | null;
  confidence: number;
}

export interface FlightSegment {
  departure_airport?: string | null;
  departure_iata?: string | null;
  arrival_airport?: string | null;
  arrival_iata?: string | null;
  departure_time?: string | null;
  arrival_time?: string | null;
  duration?: string | null;
}

export interface FlightOption {
  airline?: string | null;
  flight_number?: string | null;
  origin_iata?: string | null;
  destination_iata?: string | null;
  departure_date?: string | null;
  return_date?: string | null;
  stops: number;
  segments: FlightSegment[];
  cabin?: string | null;
  price_per_traveler?: number | null;
  currency?: string | null;
  price_source: DataSource;
  booking_hint?: string | null;
  provenance: Provenance;
}

export interface FlightResults {
  origin?: string | null;
  destination?: string | null;
  origin_airports: AirportMatch[];
  destination_airports: AirportMatch[];
  options: FlightOption[];
  cheapest_total?: number | null;
  currency?: string | null;
  source: DataSource;
  notes: string[];
}

export interface HotelOption {
  name: string;
  area?: string | null;
  category?: string | null;
  rating?: number | null;
  review_summary?: string | null;
  price_per_night?: number | null;
  currency?: string | null;
  price_source: DataSource;
  amenities: string[];
  family_friendly: boolean;
  distance_to_centre_km?: number | null;
  why_recommended?: string | null;
  reference_url?: string | null;
  provenance: Provenance;
}

export interface HotelResults {
  destination?: string | null;
  nights?: number | null;
  price_ceiling_per_night?: number | null;
  options: HotelOption[];
  recommended_index: number;
  currency?: string | null;
  source: DataSource;
  notes: string[];
}

export interface DailyForecast {
  date: string;
  condition?: string | null;
  temp_min_c?: number | null;
  temp_max_c?: number | null;
  humidity_pct?: number | null;
  precipitation_chance_pct?: number | null;
}

export interface CurrentWeather {
  temperature_c?: number | null;
  feels_like_c?: number | null;
  condition?: string | null;
  humidity_pct?: number | null;
  wind_kph?: number | null;
}

export interface WeatherInfo {
  location?: string | null;
  current?: CurrentWeather | null;
  forecast: DailyForecast[];
  packing_recommendations: string[];
  travel_suggestions: string[];
  source: DataSource;
  provider?: string | null;
  retrieved_at?: string | null;
  notes: string[];
}

export interface BudgetBreakdown {
  flights: number;
  hotels: number;
  food: number;
  transport: number;
  activities: number;
  miscellaneous: number;
  total: number;
}

export interface BudgetLine {
  amount: number;
  source: DataSource;
  basis?: string | null;
}

export interface BudgetAnalysis {
  currency: string;
  total_budget?: number | null;
  estimated_total: number;
  breakdown: BudgetBreakdown;
  line_provenance: Record<string, BudgetLine>;
  remaining_budget?: number | null;
  budget_status: BudgetStatus;
  confirmed_cost_total: number;
  estimated_cost_total: number;
  per_traveler_total?: number | null;
  recommendations: string[];
  notes: string[];
}

export interface Activity {
  title: string;
  description?: string | null;
  location?: string | null;
  duration_minutes?: number | null;
  estimated_cost?: number | null;
  currency?: string | null;
  indoor: boolean;
  family_friendly: boolean;
  tags: string[];
}

export interface DaySlot {
  slot: 'morning' | 'afternoon' | 'evening';
  activities: Activity[];
  travel_time_minutes?: number | null;
  notes?: string | null;
}

export interface ItineraryDay {
  day: number;
  date?: string | null;
  title?: string | null;
  summary?: string | null;
  slots: DaySlot[];
  estimated_day_cost?: number | null;
  weather_note?: string | null;
  rest_note?: string | null;
}

export interface ItineraryPlan {
  destination?: string | null;
  days: ItineraryDay[];
  total_days: number;
  pacing: 'relaxed' | 'balanced' | 'packed';
  estimated_activity_cost: number;
  currency?: string | null;
  travel_tips: string[];
  notes: string[];
}

export interface EvaluationCheck {
  name: string;
  dimension: string;
  kind: 'deterministic' | 'llm_judge';
  outcome: 'pass' | 'warn' | 'fail' | 'skipped';
  score: number;
  weight: number;
  reason?: string | null;
}

export interface EvaluationResult {
  overall_score: number;
  passed: boolean;
  mode: string;
  checks: EvaluationCheck[];
  dimension_scores: Record<string, number>;
  failures: string[];
  warnings: string[];
  evaluated_at: string;
}

export interface TripConstraints {
  origin?: string | null;
  destination?: string | null;
  departure_date?: string | null;
  return_date?: string | null;
  travelers: number;
  budget?: number | null;
  currency: string;
  travel_style?: string | null;
  hotel_preference?: string | null;
  interests: string[];
  special_requirements?: string | null;
  additional_instructions?: string | null;
  response_language: LanguageCode;
  nights?: number | null;
  trip_days?: number | null;
  max_hotel_price_per_night?: number | null;
}

export interface JourneyOverview {
  title: string;
  headline?: string | null;
  origin?: string | null;
  destination?: string | null;
  departure_date?: string | null;
  return_date?: string | null;
  travelers: number;
  nights?: number | null;
  travel_style?: string | null;
  language: LanguageCode;
}

export interface FinalJourney {
  trip_id: string;
  language: LanguageCode;
  overview: JourneyOverview;
  flights: FlightResults;
  hotels: HotelResults;
  weather: WeatherInfo;
  budget: BudgetAnalysis;
  itinerary: ItineraryPlan;
  travel_tips: string[];
  provider_status: ProviderStatus[];
  closing_note?: string | null;
}

export interface ReviewRecord {
  revision_number: number;
  review_status: ReviewStatus;
  requested_changes?: string | null;
  selected_agents: string[];
  change_scope: string[];
  reviewed_at?: string | null;
}

export interface TripPlanResponse {
  trip_id: string;
  session_id?: string | null;
  status: TripStatus;
  review_status: ReviewStatus;
  revision: number;
  selected_agents: string[];
  execution_reason?: string | null;
  constraints: TripConstraints;
  flights: FlightResults;
  hotels: HotelResults;
  weather: WeatherInfo;
  budget: BudgetAnalysis;
  itinerary: ItineraryPlan;
  provider_status: ProviderStatus[];
  evaluation?: EvaluationResult | null;
  guardrails: Record<string, unknown>[];
  final_journey?: FinalJourney | null;
  messages: string[];
  created_at?: string | null;
  updated_at?: string | null;
}

export interface TripDetailResponse extends TripPlanResponse {
  reviews: ReviewRecord[];
}

export interface GuardrailBlockedResponse {
  trip_id?: string | null;
  status: 'blocked';
  reason_code: string;
  message: string;
  guidance?: string | null;
}

export type PlanResult = TripPlanResponse | GuardrailBlockedResponse;

export function isBlocked(result: PlanResult): result is GuardrailBlockedResponse {
  return (result as GuardrailBlockedResponse).status === 'blocked';
}

export interface TripSummary {
  trip_id: string;
  session_id?: string | null;
  origin?: string | null;
  destination?: string | null;
  departure_date?: string | null;
  return_date?: string | null;
  travelers: number;
  budget?: number | null;
  currency: string;
  travel_style?: string | null;
  status: TripStatus;
  review_status: ReviewStatus;
  revision_count: number;
  preferred_language: LanguageCode;
  evaluation_score?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface TripListResponse {
  items: TripSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface ApproveResponse {
  trip_id: string;
  status: string;
  revision: number;
  final_summary?: FinalJourney | null;
}

export interface ChangeResponse {
  trip_id: string;
  revision: number;
  selected_agents: string[];
  change_scope: string[];
  status: ReviewStatus;
}

export interface HealthResponse {
  status: string;
  app: string;
  tagline: string;
  version: string;
  environment: string;
  database: string;
  llm: string;
  checks: Record<string, unknown>;
  time?: string | null;
}

export interface PlanRequestBody {
  query: string;
  origin?: string;
  destination?: string;
  departure_date?: string;
  return_date?: string;
  travelers: number;
  budget?: number;
  currency: string;
  travel_style?: string;
  hotel_preference?: string;
  interests: string[];
  special_requirements?: string;
  additional_instructions?: string;
  response_language: LanguageCode;
  session_id?: string;
}
