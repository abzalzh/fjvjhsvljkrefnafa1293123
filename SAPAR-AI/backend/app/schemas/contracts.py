from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


Money = Annotated[int, Field(ge=0, le=1_000_000_000_000_000, strict=True)]
ID = Annotated[str, Field(min_length=1, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')]
Transport = Literal['public', 'car', 'taxi', 'tour']
Language = Literal['ru', 'kk', 'en']


class CostEstimate(Model):
    min_kzt: Money
    max_kzt: Money

    @model_validator(mode='after')
    def ordered(self):
        if self.min_kzt > self.max_kzt:
            raise ValueError('min_kzt must not exceed max_kzt')
        return self


class Source(Model):
    id: ID
    title: str = Field(min_length=1, max_length=300)
    url: HttpUrl
    checked_at: date


class Infrastructure(Model):
    mobile: Literal['yes', 'limited', 'no', 'unknown'] = 'unknown'
    toilets: Literal['yes', 'no', 'unknown'] = 'unknown'
    food: Literal['yes', 'no', 'unknown'] = 'unknown'
    accommodation: Literal['yes', 'no', 'unknown'] = 'unknown'
    accessible: Literal['yes', 'no', 'unknown'] = 'unknown'


class Destination(Model):
    id: ID
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=5000)
    region: str = Field(min_length=1, max_length=100)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    interests: list[ID] = Field(min_length=1, max_length=20)
    visit_minutes: int | None = Field(default=None, ge=1, le=720)
    opens_minute: int | None = Field(default=None, ge=0, le=1439)
    closes_minute: int | None = Field(default=None, ge=1, le=1440)
    transport: list[Transport] = Field(min_length=1, max_length=4)
    open_months: list[Annotated[int, Field(ge=1, le=12)]] = Field(min_length=1, max_length=12)
    infrastructure: Infrastructure = Field(default_factory=Infrastructure)
    warnings: list[str] = Field(default_factory=list)
    source_ids: list[ID] = Field(min_length=1)

    @model_validator(mode='after')
    def valid_hours(self):
        if self.opens_minute is not None and self.closes_minute is not None and self.opens_minute >= self.closes_minute:
            raise ValueError('opening time must precede closing time')
        return self


class CostRule(Model):
    id: ID
    estimate: CostEstimate | None
    basis: Literal['person', 'group', 'unit']
    capacity: int = Field(default=1, ge=1, le=100)
    kind: Literal['verified', 'estimate', 'unknown']
    source_ids: list[ID] = Field(min_length=1)

    @model_validator(mode='after')
    def coherent(self):
        if self.estimate is not None and self.estimate.max_kzt > 1_000_000_000:
            raise ValueError('individual cost exceeds supported limit')
        if (self.estimate is None) != (self.kind == 'unknown'):
            raise ValueError('unknown requires null; other kinds require estimate')
        if self.basis != 'unit' and self.capacity != 1:
            raise ValueError('capacity is only applicable to unit costs')
        return self


class TransportConnection(Model):
    id: ID
    origin: str = Field(min_length=1, max_length=80)
    destination: str = Field(min_length=1, max_length=80)
    transport: Transport
    minutes: int | None = Field(default=None, ge=1, le=1440)
    distance_km: float | None = Field(default=None, ge=0)
    cost_id: ID
    # Minute offsets after midnight; null means flexible departure (e.g. own car).
    departures: list[Annotated[int, Field(ge=0, le=1439)]] | None = None
    source_ids: list[ID] = Field(min_length=1)


class RouteDay(Model):
    destination_ids: list[ID] = Field(min_length=1, max_length=8)
    connection_ids: list[ID] = Field(min_length=2, max_length=9)


class RouteTemplate(Model):
    id: ID
    name: str = Field(min_length=1, max_length=200)
    origin: str = Field(min_length=1, max_length=80)
    transport: Transport
    days: list[RouteDay] = Field(min_length=1, max_length=14)
    food_cost_id: ID
    accommodation_cost_id: ID | None = None
    activity_cost_ids: dict[ID, Annotated[list[ID], Field(min_length=1)]]
    max_travelers: int = Field(ge=1, le=20)
    available_from: date
    available_until: date
    source_ids: list[ID] = Field(min_length=1)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def dates(self):
        if self.available_from > self.available_until:
            raise ValueError('invalid availability interval')
        return self


class TransportData(Model):
    connections: list[TransportConnection]
    routes: list[RouteTemplate]


class Dataset(Model):
    schema_version: Literal['1.0'] = '1.0'
    destinations: list[Destination]
    transport: TransportData
    costs: list[CostRule]
    sources: list[Source]

    @model_validator(mode='after')
    def references(self):
        groups = [self.destinations, self.transport.connections, self.transport.routes, self.costs, self.sources]
        for group in groups:
            if len({x.id for x in group}) != len(group):
                raise ValueError('duplicate IDs within entity collection')
        sources = {x.id for x in self.sources}
        costs = {x.id for x in self.costs}
        destinations = {x.id for x in self.destinations}
        connections = {x.id: x for x in self.transport.connections}
        for group in groups[:-1]:
            for item in group:
                if not set(item.source_ids) <= sources:
                    raise ValueError(f'unknown source reference: {item.id}')
        for edge in connections.values():
            if edge.cost_id not in costs:
                raise ValueError(f'unknown connection cost: {edge.id}')
        for route in self.transport.routes:
            refs = [route.food_cost_id] + ([route.accommodation_cost_id] if route.accommodation_cost_id else [])
            for ids in route.activity_cost_ids.values():
                refs.extend(ids)
            if not set(refs) <= costs:
                raise ValueError(f'unknown route cost: {route.id}')
            visited = {d for day in route.days for d in day.destination_ids}
            if not visited <= destinations or set(route.activity_cost_ids) != visited:
                raise ValueError(f'activity costs must explicitly cover visited destinations: {route.id}')
            if len(route.days) > 1 and route.accommodation_cost_id is None:
                raise ValueError('multi-day routes require accommodation cost')
            for day in route.days:
                if len(day.connection_ids) != len(day.destination_ids) + 1:
                    raise ValueError('each day requires outward, intermediate and return connections')
                points = [route.origin, *day.destination_ids, route.origin]
                for i, edge_id in enumerate(day.connection_ids):
                    edge = connections.get(edge_id)
                    if edge is None or (edge.origin, edge.destination, edge.transport) != (points[i], points[i+1], route.transport):
                        raise ValueError(f'broken directed route: {route.id}/{edge_id}')
        return self


class TripPreferences(Model):
    origin: str = Field(default='Almaty', min_length=1, max_length=80)
    budget_kzt: Money
    days: int = Field(ge=1, le=14, strict=True)
    travelers: int = Field(ge=1, le=20, strict=True)
    transport: Transport
    interests: list[ID] = Field(default_factory=list, max_length=20)
    language: Language = 'ru'
    start_date: date | None = None
    max_day_minutes: int = Field(default=600, ge=60, le=840, strict=True)
    require_accessible: bool = False


class ItineraryItem(Model):
    kind: Literal['travel', 'visit', 'wait']
    reference_id: str
    start_minute: int
    end_minute: int


class TripDay(Model):
    day: int
    date: date
    items: list[ItineraryItem]
    duration_minutes: int


class BudgetBreakdown(Model):
    transport: CostEstimate
    accommodation: CostEstimate
    food: CostEstimate
    activities: CostEstimate


class TripOption(Model):
    id: str
    name: str
    category: Literal['economy', 'balanced', 'activities']
    days: int
    travelers: int
    transport: Transport
    estimated_total_kzt: Money
    cost_range_kzt: CostEstimate
    budget_breakdown: BudgetBreakdown
    within_budget: bool
    remaining_budget_kzt: int
    feasibility: Literal['estimated'] = 'estimated'
    destinations: list[Destination]
    connections: list[TransportConnection]
    itinerary: list[TripDay]
    warnings: list[str]
    sources: list[Source]
    unknown_fields: list[str]
    score: float
    recommendation_reasons: list[str]


class Reason(Model):
    code: str
    message: str
    suggested_fields: list[str]


class TripResponse(Model):
    schema_version: Literal['1.0'] = '1.0'
    status: Literal['success', 'no_results']
    preferences: TripPreferences
    trips: list[TripOption]
    reasons: list[Reason]
    data_mode: Literal['real', 'demo']


class ErrorDetail(Model):
    code: str
    message: str
    details: list[dict] = Field(default_factory=list)


class ErrorResponse(Model):
    error: ErrorDetail
