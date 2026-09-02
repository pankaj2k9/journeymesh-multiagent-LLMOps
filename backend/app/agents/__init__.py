"""JourneyMesh specialist agents."""

from app.agents.base import BaseAgent
from app.agents.budget_agent import BudgetAgent
from app.agents.final_response_agent import FinalResponseAgent
from app.agents.flight_agent import FlightAgent
from app.agents.hotel_agent import HotelAgent
from app.agents.itinerary_agent import ItineraryAgent
from app.agents.supervisor import SupervisorAgent
from app.agents.weather_agent import WeatherAgent

AGENT_REGISTRY = {
    FlightAgent.name: FlightAgent,
    HotelAgent.name: HotelAgent,
    WeatherAgent.name: WeatherAgent,
    BudgetAgent.name: BudgetAgent,
    ItineraryAgent.name: ItineraryAgent,
}

__all__ = [
    "BaseAgent",
    "SupervisorAgent",
    "FlightAgent",
    "HotelAgent",
    "WeatherAgent",
    "BudgetAgent",
    "ItineraryAgent",
    "FinalResponseAgent",
    "AGENT_REGISTRY",
]
