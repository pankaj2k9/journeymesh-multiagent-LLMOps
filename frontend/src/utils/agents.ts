import type { TripPlanResponse } from '../types';

/**
 * Which agents actually contributed to the journey on screen.
 *
 * `selected_agents` is the set the supervisor chose for the *most recent*
 * pass, which after a revision is only the agents that re-ran - asking for
 * weather leaves it reading "weather, itinerary" even though the flights and
 * hotels on the page came from earlier agents and were deliberately
 * preserved. The execution plan shows the union, so the list matches what the
 * traveller can see, and the current pass is highlighted on top of it.
 *
 * Membership is decided by the same result markers the backend uses for
 * preservation, so the two views of "this agent produced something" agree.
 */
export function contributingAgents(trip: TripPlanResponse): string[] {
  const journey = trip.final_journey;
  const produced: Array<[string, boolean]> = [
    ['flight_agent', Boolean((journey?.flights ?? trip.flights).options.length)],
    ['hotel_agent', Boolean((journey?.hotels ?? trip.hotels).options.length)],
    ['weather_agent', Boolean((journey?.weather ?? trip.weather).forecast.length)],
    ['budget_agent', Boolean((journey?.budget ?? trip.budget).estimated_total)],
    ['itinerary_agent', Boolean((journey?.itinerary ?? trip.itinerary).days.length)],
  ];

  const selected = new Set(trip.selected_agents);
  const ordered = produced
    .filter(([agent, hasResult]) => hasResult || selected.has(agent))
    .map(([agent]) => agent);

  // Anything the supervisor named that is not one of the five specialists -
  // the final response agent, for instance - keeps its place at the end.
  const extras = trip.selected_agents.filter((agent) => !ordered.includes(agent));
  return [...ordered, ...extras];
}
