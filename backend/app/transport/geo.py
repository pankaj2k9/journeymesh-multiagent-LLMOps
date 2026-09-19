"""Where the places are, and how far apart.

Coordinates come from each city's Wikipedia article (fetched once, not typed
from memory) and are used only for distances: a straight line times a factor
for how much longer the road or rail is. Good enough to plan and to compare
modes; never presented as a route length a traveller could drive.
"""

from __future__ import annotations

import math

# Keys match `app.mcp.aviation.AIRPORTS`, plus waypoints such as Teknaf.
COORDINATES: dict[str, tuple[float, float]] = {
    "abu dhabi": (24.4667, 54.3667),
    "agra": (27.18, 78.02),
    "ahmedabad": (23.0225, 72.5714),
    "alappuzha": (9.49, 76.33),
    "alexandria": (31.1975, 29.8925),
    "amalfi": (40.6337, 14.6026),
    "amritsar": (31.64, 74.86),
    "amsterdam": (52.3728, 4.8936),
    "antalya": (36.8869, 30.7033),
    "aswan": (24.0889, 32.8997),
    "bagdogra": (26.7, 88.3167),
    "bali": (-8.6717, 115.2339),
    "bandar seri begawan": (4.8903, 114.9422),
    "bandarban": (22.198, 92.22),
    "bangalore": (12.9789, 77.5917),
    "bangkok": (13.7525, 100.4942),
    "barcelona": (41.3833, 2.1833),
    "barisal": (22.7, 90.3667),
    "beijing": (39.9067, 116.3975),
    "bengaluru": (12.9789, 77.5917),
    "berlin": (52.52, 13.405),
    "bhaktapur": (27.6722, 85.4278),
    "bohol": (9.65, 123.85),
    "boracay": (11.9689, 121.9239),
    "busan": (35.18, 129.075),
    "cairo": (30.0444, 31.2358),
    "cape town": (-33.9253, 18.4239),
    "cappadocia": (38.6431, 34.8289),
    "caticlan": (11.8997, 121.9094),
    "cebu": (10.293, 123.902),
    "chengdu": (30.66, 104.0633),
    "chennai": (13.0825, 80.275),
    "chiang mai": (18.7953, 98.9986),
    "chittagong": (22.335, 91.8325),
    "chitwan": (27.5, 84.3333),
    "cinque terre": (44.1194, 9.7167),
    "coimbatore": (11.0008, 76.9633),
    "colombo": (6.9344, 79.8428),
    "cox's bazar": (21.4272, 92.005),
    "da nang": (16.0694, 108.2097),
    "darjeeling": (27.0375, 88.2631),
    "dehradun": (30.345, 78.029),
    "delhi": (28.61, 77.23),
    "denizli": (37.7833, 29.0964),
    "dhaka": (23.7644, 90.3889),
    "doha": (25.2867, 51.5333),
    "dubai": (25.2047, 55.2708),
    "el nido": (11.18, 119.39),
    "ella": (6.8753, 81.0383),
    "faro": (37.0161, -7.935),
    "florence": (43.7714, 11.2542),
    "galle": (6.0328, 80.2156),
    "gangtok": (27.33, 88.62),
    "geneva": (46.2017, 6.1469),
    "goa": (15.4989, 73.8278),
    "granada": (37.175, -3.6),
    "guangzhou": (23.13, 113.26),
    "guilin": (25.275, 110.296),
    "guwahati": (26.1722, 91.7458),
    "ha long": (20.95, 107.0833),
    "hampi": (15.3344, 76.4622),
    "hangzhou": (30.267, 120.153),
    "hanoi": (21, 105.85),
    "haridwar": (29.945, 78.163),
    "hiroshima": (34.3914, 132.4519),
    "ho chi minh city": (10.7756, 106.7019),
    "hoi an": (15.8771, 108.326),
    "hong kong": (22.3, 114.2),
    "hualien": (23.9722, 121.6064),
    "hue": (16.4639, 107.5867),
    "hurghada": (27.2578, 33.8117),
    "hyderabad": (17.3617, 78.4747),
    "interlaken": (46.6833, 7.85),
    "istanbul": (41.0136, 28.955),
    "izmir": (38.4244, 27.1322),
    "jaipur": (26.915, 75.82),
    "jaisalmer": (26.913, 70.915),
    "jakarta": (-6.18, 106.83),
    "jeju": (33.513, 126.523),
    "jessore": (23.167, 89.209),
    "jodhpur": (26.28, 73.02),
    "kandy": (7.2931, 80.635),
    "kathmandu": (27.71, 85.32),
    "khajuraho": (24.85, 79.925),
    "khulna": (22.83, 89.55),
    "kochi": (9.9312, 76.2673),
    "kolkata": (22.5675, 88.37),
    "krabi": (8.0592, 98.9189),
    "kuakata": (21.8029, 90.1809),
    "kuala lumpur": (3.1478, 101.6953),
    "kyoto": (35.0116, 135.7681),
    "labuan bajo": (-8.5, 119.8833),
    "langkawi": (6.35, 99.8),
    "leh": (34.1526, 77.5771),
    "lisbon": (38.7253, -9.15),
    "lombok": (-8.5833, 116.1167),
    "london": (51.5072, -0.1275),
    "los angeles": (34.05, -118.25),
    "luang prabang": (19.89, 102.1347),
    "lucerne": (47.05, 8.3),
    "lucknow": (26.85, 80.95),
    "lukla": (27.6889, 86.7306),
    "lumbini": (27.4814, 83.2758),
    "luxor": (25.6967, 32.6444),
    "macau": (22.19, 113.54),
    "madeira": (32.65, -16.9167),
    "madrid": (40.4169, -3.7033),
    "malacca": (2.1944, 102.2486),
    "malaga": (36.7194, -4.42),
    "male": (4.1753, 73.5089),
    "malé": (4.1753, 73.5089),
    "manali": (32.2432, 77.1892),
    "manama": (26.2233, 50.5875),
    "manila": (14.5958, 120.9772),
    "melbourne": (-37.8142, 144.9631),
    "milan": (45.4669, 9.19),
    "mumbai": (19.0761, 72.8775),
    "munnar": (10.0892, 77.0597),
    "mysuru": (12.3086, 76.6531),
    "nagarkot": (27.7236, 85.5247),
    "nairobi": (-1.2864, 36.8172),
    "naples": (40.8358, 14.2486),
    "nara": (34.6844, 135.805),
    "new delhi": (28.6139, 77.2089),
    "new york": (40.7128, -74.0061),
    "nuwara eliya": (6.9667, 80.7667),
    "ooty": (11.41, 76.7),
    "osaka": (34.6939, 135.5022),
    "pamukkale": (37.9239, 29.1233),
    "paris": (48.8567, 2.3522),
    "paro": (27.4333, 89.4167),
    "pattaya": (12.9357, 100.889),
    "penang": (5.4144, 100.3292),
    "phuket": (7.89, 98.3983),
    "pisa": (43.7167, 10.4),
    "pokhara": (28.2083, 83.9889),
    "port blair": (11.6683, 92.7378),
    "porto": (41.15, -8.6108),
    "puerto princesa": (9.74, 118.744),
    "pune": (18.5211, 73.8553),
    "rajshahi": (24.3745, 88.6042),
    "rangamati": (22.6333, 92.2),
    "rishikesh": (30.1083, 78.2972),
    "rome": (41.8933, 12.4828),
    "saint martin's island": (20.6131, 92.3267),
    "sajek valley": (23.635, 92.49),
    "san francisco": (37.7775, -122.4164),
    "sapporo": (43.0619, 141.3544),
    "seoul": (37.56, 126.99),
    "seville": (37.3886, -5.995),
    "shanghai": (31.2325, 121.4692),
    "sharm el sheikh": (27.915, 34.3275),
    "shenzhen": (22.5467, 114.0544),
    "shillong": (25.5822, 91.8944),
    "shimla": (31.1033, 77.1722),
    "siem reap": (13.3622, 103.8597),
    "sigiriya": (7.9569, 80.7597),
    "singapore": (1.2833, 103.8333),
    "sintra": (38.7992, -9.3883),
    "sreemangal": (24.3197, 91.7836),
    "srimangal": (24.3197, 91.7836),
    "srinagar": (34.09, 74.79),
    "st. martin's island": (20.6131, 92.3267),
    "sydney": (-33.8678, 151.21),
    "sylhet": (24.9, 91.8667),
    "taipei": (25.0375, 121.5625),
    "teknaf": (20.8681, 92.2983),
    "thimphu": (27.4722, 89.6361),
    "thiruvananthapuram": (8.5241, 76.9366),
    "tokyo": (35.6897, 139.6922),
    "toronto": (43.6525, -79.3817),
    "udaipur": (24.58, 73.68),
    "ulaanbaatar": (47.9219, 106.9153),
    "valencia": (39.47, -0.3764),
    "varanasi": (25.3189, 83.0128),
    "venice": (45.4375, 12.3358),
    "vientiane": (17.98, 102.63),
    "xi'an": (34.2611, 108.9422),
    "yogyakarta": (-7.8014, 110.3644),
    "zermatt": (46.0167, 7.75),
    "zhangjiajie": (29.117, 110.479),
    "zurich": (47.3744, 8.5411),
}

# Destinations without an airport of their own: the city whose airport serves
# them. Flying there means flying to the gateway and continuing on the ground.
GATEWAYS: dict[str, str] = {
    "bandarban": "chittagong",
    "rangamati": "chittagong",
    "sajek valley": "chittagong",
    "saint martin's island": "cox's bazar",
    "st. martin's island": "cox's bazar",
    "sreemangal": "sylhet",
    "srimangal": "sylhet",
    "kuakata": "barisal",
    "khulna": "jessore",
    "kyoto": "osaka",
    "rishikesh": "dehradun",
    "haridwar": "dehradun",
    "darjeeling": "bagdogra",
    "gangtok": "bagdogra",
    "ooty": "coimbatore",
    "munnar": "kochi",
    "alappuzha": "kochi",
    "kandy": "colombo",
    "sigiriya": "colombo",
    "galle": "colombo",
    "ella": "colombo",
    "nuwara eliya": "colombo",
    "malacca": "kuala lumpur",
    "boracay": "caticlan",
    "el nido": "puerto princesa",
    "ha long": "hanoi",
    "hoi an": "da nang",
    "pamukkale": "denizli",
    "nagarkot": "kathmandu",
    "bhaktapur": "kathmandu",
    "thimphu": "paro",
    "sintra": "lisbon",
    "amalfi": "naples",
    "cinque terre": "pisa",
    "lucerne": "zurich",
    "interlaken": "zurich",
    "zermatt": "geneva",
    "nara": "osaka",
}

# Islands reached by road to a jetty and then a boat: (jetty, boat mode).
FERRY_ACCESS: dict[str, tuple[str, str]] = {
    "saint martin's island": ("teknaf", "ferry"),
    "st. martin's island": ("teknaf", "ferry"),
    "boracay": ("caticlan", "ferry"),
}

# Places no road or railway reaches from anywhere else on the map.
FLY_ONLY: frozenset[str] = frozenset(
    {
        "port blair", "male", "malé", "bali", "langkawi", "lombok", "labuan bajo",
        "lukla", "madeira", "jeju",
    }
)

# Island groups in an archipelago: the road network stops at the shore, so two
# places are ground-connected only on the same island.
ISLANDS: dict[str, str] = {
    "manila": "luzon",
    "cebu": "cebu",
    "bohol": "bohol",
    "caticlan": "panay",
    "puerto princesa": "palawan",
    "el nido": "palawan",
}

# How much longer the ground route is than the straight line, on average.
ROAD_FACTOR = 1.3

# Mountain roads wind: the last stretch into the hills is a much longer drive.
# Only that stretch is penalised - a long trip is mostly plains highway.
HILL_EXTRA_FACTOR = 0.5
HILL_STRETCH_KM = 150.0
HILLY: frozenset[str] = frozenset({
    "kathmandu", "pokhara", "nagarkot", "bhaktapur", "lukla", "paro", "thimphu",
    "leh", "manali", "shimla", "darjeeling", "gangtok", "shillong", "munnar", "ooty",
    "srinagar", "sajek valley", "bandarban", "rangamati", "nuwara eliya", "ella", "kandy",
    "zermatt", "interlaken", "amalfi", "cinque terre",
})


def normalise(city: str) -> str:
    return " ".join((city or "").strip().lower().split())


def coordinates(city: str) -> tuple[float, float] | None:
    return COORDINATES.get(normalise(city))


def straight_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance in kilometres (haversine)."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6371.0 * math.asin(math.sqrt(h))
