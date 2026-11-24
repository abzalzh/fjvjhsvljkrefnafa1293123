from fastapi import APIRouter, HTTPException, Query, Request

from app.schemas.contracts import Destination, TripPreferences, TripResponse
from app.services.planner.engine import generate
from app.services import ai_gateway

router = APIRouter(prefix='/api')


@router.get('/health')
def health(request: Request):
    data = request.app.state.repository.read()
    return {'status': 'ok', 'schema_version': '1.0',
            'data_mode': 'demo' if request.app.state.settings.demo_mode else 'real',
            'dataset_ready': bool(data.destinations and data.transport.routes),
            'destinations_count': len(data.destinations), 'routes_count': len(data.transport.routes),
            'ai_configured': request.app.state.ai_provider is not None}


@router.get('/destinations', response_model=list[Destination])
def destinations(request: Request, interest: str | None = Query(default=None, max_length=80)):
    data = request.app.state.repository.read()
    return [d for d in data.destinations if interest is None or interest in d.interests]


@router.get('/destinations/{destination_id}', response_model=Destination)
def destination(destination_id: str, request: Request):
    data = request.app.state.repository.read()
    result = next((d for d in data.destinations if d.id == destination_id), None)
    if result is None:
        raise HTTPException(404, 'Destination not found')
    return result


@router.post('/trips/generate', response_model=TripResponse)
def trips(preferences: TripPreferences, request: Request):
    return generate(request.app.state.repository.read(), preferences, request.app.state.settings.demo_mode)


@router.post('/trips/recalculate', response_model=TripResponse)
def recalculate(preferences: TripPreferences, request: Request):
    return trips(preferences, request)


@router.post('/ai/parse', response_model=ai_gateway.ParseResponse)
async def ai_parse(payload: ai_gateway.ParseRequest, request: Request):
    return await ai_gateway.parse(request.app.state.ai_provider, payload, request.app.state.settings.ai_timeout_seconds)


@router.post('/ai/explain', response_model=ai_gateway.ExplainResponse)
async def ai_explain(payload: ai_gateway.ExplainRequest, request: Request):
    # Recompute server-side: do not trust client-supplied costs or itinerary.
    result = trips(payload.preferences, request)
    trip = next((t for t in result.trips if t.id == payload.trip_id), None)
    if trip is None:
        raise HTTPException(404, 'Trip not feasible or not selected; regenerate trips')
    return await ai_gateway.explain(request.app.state.ai_provider, trip, payload.language, request.app.state.settings.ai_timeout_seconds)
