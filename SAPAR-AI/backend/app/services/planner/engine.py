from datetime import date, timedelta
from math import ceil
from zoneinfo import ZoneInfo
from datetime import datetime

from app.schemas.contracts import (
    BudgetBreakdown, CostEstimate, Dataset, ItineraryItem, Reason,
    TripDay, TripOption, TripPreferences, TripResponse,
)


MESSAGES = {
    'dataset_empty': ('Нет проверенных шаблонов маршрутов.', []),
    'unsupported_origin': ('Для города отправления нет маршрутов.', ['origin']),
    'transport_unavailable': ('Для выбранного транспорта нет маршрутов.', ['transport']),
    'duration_unavailable': ('Нет шаблонов на выбранное число дней.', ['days']),
    'data_incomplete': ('Не хватает цен, времени или данных о доступности.', []),
    'season_unavailable': ('Маршрут недоступен в выбранные даты.', ['start_date']),
    'time_exceeded': ('Маршрут не укладывается в дневной лимит или расписание.', ['max_day_minutes']),
    'budget_exceeded': ('Верхняя граница расходов превышает бюджет.', ['budget_kzt', 'travelers']),
    'accessibility_unconfirmed': ('Доступность объектов не подтверждена.', ['require_accessible']),
    'interests_unmatched': ('Нет совпадений с выбранными интересами.', ['interests']),
    'capacity_exceeded': ('Группа превышает вместимость шаблона маршрута.', ['travelers']),
}


def amount(rule, travelers: int, occurrences: int = 1) -> CostEstimate:
    if rule.estimate is None:
        raise ValueError('unknown cost')
    factor = travelers if rule.basis == 'person' else ceil(travelers / rule.capacity) if rule.basis == 'unit' else 1
    return CostEstimate(min_kzt=rule.estimate.min_kzt * factor * occurrences,
                        max_kzt=rule.estimate.max_kzt * factor * occurrences)


def total(parts) -> CostEstimate:
    return CostEstimate(min_kzt=sum(p.min_kzt for p in parts), max_kzt=sum(p.max_kzt for p in parts))


def generate(data: Dataset, prefs: TripPreferences, demo: bool = False, today: date | None = None) -> TripResponse:
    today = today or datetime.now(ZoneInfo('Asia/Almaty')).date()
    start = prefs.start_date or today
    ds = {d.id: d for d in data.destinations}
    edges = {e.id: e for e in data.transport.connections}
    costs = {c.id: c for c in data.costs}
    sources = {s.id: s for s in data.sources}
    rejected = set()
    candidates = []
    routes = data.transport.routes
    if not routes:
        rejected.add('dataset_empty')
    for route in routes:
        if route.origin.casefold() != prefs.origin.strip().casefold():
            rejected.add('unsupported_origin'); continue
        if route.transport != prefs.transport:
            rejected.add('transport_unavailable'); continue
        if len(route.days) != prefs.days:
            rejected.add('duration_unavailable'); continue
        if prefs.travelers > route.max_travelers:
            rejected.add('capacity_exceeded'); continue
        if start < route.available_from or start + timedelta(days=prefs.days-1) > route.available_until:
            rejected.add('season_unavailable'); continue
        visited = list(dict.fromkeys(d for day in route.days for d in day.destination_ids))
        destinations = [ds[d] for d in visited]
        if any(prefs.transport not in d.transport for d in destinations):
            rejected.add('transport_unavailable'); continue
        if prefs.require_accessible and any(d.infrastructure.accessible != 'yes' for d in destinations):
            rejected.add('accessibility_unconfirmed'); continue
        matched = set(prefs.interests) & {i for d in destinations for i in d.interests}
        if prefs.interests and not matched:
            rejected.add('interests_unmatched'); continue
        used_costs = [route.food_cost_id]
        if prefs.days > 1:
            used_costs.append(route.accommodation_cost_id)
        used_costs += [edges[e].cost_id for day in route.days for e in day.connection_ids]
        used_costs += [c for day in route.days for d in day.destination_ids for c in route.activity_cost_ids[d]]
        if any(costs[c].estimate is None for c in used_costs) or any(d.visit_minutes is None or d.opens_minute is None or d.closes_minute is None for d in destinations):
            rejected.add('data_incomplete'); continue
        itinerary = []
        failure = None
        for day_index, day in enumerate(route.days):
            travel_date = start + timedelta(days=day_index)
            if any(travel_date.month not in ds[d].open_months for d in day.destination_ids):
                failure = 'season_unavailable'; break
            minute = 9 * 60
            items = []
            for index, edge_id in enumerate(day.connection_ids):
                edge = edges[edge_id]
                if edge.minutes is None or (edge.transport in ('public', 'tour') and edge.departures is None):
                    failure = 'data_incomplete'; break
                if edge.departures is not None:
                    next_departure = next((t for t in sorted(edge.departures) if t >= minute), None)
                    if next_departure is None:
                        failure = 'time_exceeded'; break
                    if next_departure > minute:
                        items.append(ItineraryItem(kind='wait', reference_id=edge.id, start_minute=minute, end_minute=next_departure))
                    minute = next_departure
                items.append(ItineraryItem(kind='travel', reference_id=edge.id, start_minute=minute, end_minute=minute+edge.minutes))
                minute += edge.minutes
                if index < len(day.destination_ids):
                    dest = ds[day.destination_ids[index]]
                    if minute < dest.opens_minute:
                        items.append(ItineraryItem(kind='wait', reference_id=dest.id, start_minute=minute, end_minute=dest.opens_minute))
                        minute = dest.opens_minute
                    if minute + dest.visit_minutes > dest.closes_minute:
                        failure = 'time_exceeded'; break
                    items.append(ItineraryItem(kind='visit', reference_id=dest.id, start_minute=minute, end_minute=minute+dest.visit_minutes))
                    minute += dest.visit_minutes
            if failure:
                break
            if minute - 540 > prefs.max_day_minutes:
                failure = 'time_exceeded'; break
            itinerary.append(TripDay(day=day_index+1, date=travel_date, items=items, duration_minutes=minute-540))
        if failure:
            rejected.add(failure); continue
        breakdown = BudgetBreakdown(
            transport=total([amount(costs[edges[e].cost_id], prefs.travelers) for day in route.days for e in day.connection_ids]),
            accommodation=amount(costs[route.accommodation_cost_id], prefs.travelers, prefs.days-1) if prefs.days > 1 else CostEstimate(min_kzt=0, max_kzt=0),
            food=amount(costs[route.food_cost_id], prefs.travelers, prefs.days),
            activities=total([amount(costs[c], prefs.travelers) for day in route.days for d in day.destination_ids for c in route.activity_cost_ids[d]]),
        )
        cost = total([breakdown.transport, breakdown.accommodation, breakdown.food, breakdown.activities])
        if cost.max_kzt > prefs.budget_kzt:
            rejected.add('budget_exceeded'); continue
        source_ids = set(route.source_ids)
        for item in destinations + [edges[e] for day in route.days for e in day.connection_ids] + [costs[c] for c in used_costs]:
            source_ids.update(item.source_ids)
        unknown = [f'{d.id}.infrastructure.{k}' for d in destinations for k, v in d.infrastructure.model_dump().items() if v == 'unknown']
        warnings = list(route.warnings)
        warnings += [w for d in destinations for w in d.warnings]
        warnings += [f'{d.name}: {k}={v}' for d in destinations for k,v in d.infrastructure.model_dump().items() if v in ('no','limited')]
        warnings.append('Расчётная осуществимость и оценочные расходы не гарантируют доступность, цену или безопасность.')
        if prefs.start_date is None:
            warnings.append(f'Дата не указана: расчёт на {start.isoformat()}.')
        if unknown:
            warnings.append('Часть инфраструктуры не подтверждена; см. unknown_fields.')
        if demo:
            warnings.insert(0, 'DEMO: синтетические тестовые данные, не использовать для поездок.')
        confidence = sum(costs[c].kind == 'verified' for c in used_costs) / len(used_costs)
        interest_score = len(matched) / len(set(prefs.interests)) if prefs.interests else 1
        score = round(50*interest_score + 20*confidence + 20*(1-cost.max_kzt/max(1,prefs.budget_kzt)) + 10/(1+len(unknown)), 2)
        candidates.append(TripOption(
            id=route.id, name=route.name, category='balanced', days=prefs.days, travelers=prefs.travelers,
            transport=prefs.transport, estimated_total_kzt=cost.max_kzt, cost_range_kzt=cost,
            budget_breakdown=breakdown, within_budget=True, remaining_budget_kzt=prefs.budget_kzt-cost.max_kzt,
            destinations=destinations, connections=[edges[e] for e in dict.fromkeys(e for day in route.days for e in day.connection_ids)],
            itinerary=itinerary, warnings=list(dict.fromkeys(warnings)),
            sources=[sources[s] for s in sorted(source_ids)], unknown_fields=unknown, score=score,
            recommendation_reasons=['Верхняя граница расходов укладывается в общий бюджет.', f'Совпавшие интересы: {", ".join(sorted(matched)) or "не заданы"}.'],
        ))
    selected = []
    for category, key in [('economy', lambda t: (t.cost_range_kzt.max_kzt, -t.score, t.id)),
                          ('balanced', lambda t: (-t.score, t.cost_range_kzt.max_kzt, t.id)),
                          ('activities', lambda t: (-len(t.destinations), -t.score, t.id))]:
        available = [t for t in candidates if t.id not in {s.id for s in selected}]
        if available:
            choice = min(available, key=key)
            selected.append(choice.model_copy(update={'category': category}))
    reasons = [Reason(code=c, message=MESSAGES[c][0], suggested_fields=MESSAGES[c][1]) for c in sorted(rejected)] if not selected else []
    return TripResponse(status='success' if selected else 'no_results', preferences=prefs,
                        trips=selected, reasons=reasons, data_mode='demo' if demo else 'real')
