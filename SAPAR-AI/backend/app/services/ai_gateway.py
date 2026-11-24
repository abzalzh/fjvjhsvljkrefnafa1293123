"""Backend-owned integration boundary. Groq implementation belongs to Yerasyl."""
import asyncio
from typing import Protocol

from pydantic import Field

from app.schemas.contracts import Model, TripPreferences, TripOption, Language


class ParseRequest(Model):
    text: str = Field(min_length=1, max_length=2000)
    preferences: TripPreferences


class ParseResponse(Model):
    status: str
    changes: dict
    preferences: TripPreferences
    warnings: list[str]


class ExplainRequest(Model):
    trip_id: str = Field(min_length=1, max_length=80)
    preferences: TripPreferences
    language: Language = 'ru'


class ExplainResponse(Model):
    status: str
    explanation: str


class AIProvider(Protocol):
    async def parse(self, text: str, preferences: dict) -> dict: ...
    async def explain(self, trip: dict, language: str) -> str: ...


async def parse(provider: AIProvider | None, request: ParseRequest, timeout: float) -> ParseResponse:
    try:
        if provider is None:
            raise RuntimeError('AI not configured')
        changes = await asyncio.wait_for(provider.parse(request.text, request.preferences.model_dump(mode='json')), timeout)
        if not isinstance(changes, dict) or not set(changes) <= set(TripPreferences.model_fields):
            raise ValueError('Invalid AI fields')
        validated = TripPreferences.model_validate(request.preferences.model_dump() | changes)
        delta = {k: v for k, v in validated.model_dump(mode='json').items() if v != request.preferences.model_dump(mode='json')[k]}
        return ParseResponse(status='success', changes=delta, preferences=validated, warnings=[])
    except Exception:
        return ParseResponse(status='fallback', changes={}, preferences=request.preferences,
                             warnings=['ИИ недоступен или вернул некорректные данные. Измените параметры вручную.'])


async def explain(provider: AIProvider | None, trip: TripOption, language: str, timeout: float) -> ExplainResponse:
    try:
        if provider is None:
            raise RuntimeError('AI not configured')
        explanation = await asyncio.wait_for(provider.explain(trip.model_dump(mode='json'), language), timeout)
        if not isinstance(explanation, str) or not 1 <= len(explanation.strip()) <= 8000:
            raise ValueError('Invalid AI explanation')
        return ExplainResponse(status='success', explanation=explanation)
    except Exception:
        return ExplainResponse(status='fallback', explanation=f'{trip.name}: {trip.cost_range_kzt.min_kzt}–{trip.cost_range_kzt.max_kzt} KZT. ' + ' '.join(trip.recommendation_reasons))
