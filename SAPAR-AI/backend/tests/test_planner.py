import pytest
from pydantic import ValidationError

from app.schemas.contracts import CostRule, CostEstimate, Dataset, TripPreferences
from app.services.planner.engine import amount, generate


def test_exact_cost(data, preferences):
    result = generate(data, preferences, True)
    assert result.status == 'success'
    assert len(result.trips) == 3
    trip = result.trips[0]
    # Transport 2 legs x 3 days; lodging 2 nights; food 3 days; 3 tickets.
    assert trip.cost_range_kzt.model_dump() == {'min_kzt':29500,'max_kzt':40100}
    assert trip.remaining_budget_kzt == 29900
    assert trip.budget_breakdown.accommodation.max_kzt == 20000
    assert trip.itinerary[-1].items[-1].end_minute == 960
    assert any(i.kind == 'wait' for i in trip.itinerary[0].items)
    assert trip.sources and trip.unknown_fields
    assert 'DEMO' in trip.warnings[0]


@pytest.mark.parametrize('travelers,expected', [(1,40100),(2,60200),(3,100300),(4,120400)])
def test_room_capacity(data, preferences, travelers, expected):
    p = preferences.model_copy(update={'travelers':travelers,'budget_kzt':200000})
    assert generate(data,p).trips[0].estimated_total_kzt == expected


@pytest.mark.parametrize('days,expected', [(1,6700),(2,23400),(3,40100)])
def test_days_and_nights(data, preferences, days, expected):
    assert generate(data, preferences.model_copy(update={'days':days})).trips[0].estimated_total_kzt == expected


@pytest.mark.parametrize('basis,capacity,expected', [('group',1,100),('person',1,300),('unit',2,200)])
def test_units(basis, capacity, expected):
    rule = CostRule(id='x', estimate=CostEstimate(min_kzt=100,max_kzt=100), basis=basis,capacity=capacity,kind='verified',source_ids=['x'])
    assert amount(rule,3).max_kzt == expected


@pytest.mark.parametrize('update,code', [
    ({'budget_kzt':0},'budget_exceeded'),
    ({'budget_kzt':40099},'budget_exceeded'),
    ({'transport':'taxi'},'transport_unavailable'),
    ({'origin':'Astana'},'unsupported_origin'),
    ({'days':14},'duration_unavailable'),
    ({'max_day_minutes':300},'time_exceeded'),
    ({'require_accessible':True},'accessibility_unconfirmed'),
    ({'interests':['nonexistent']},'interests_unmatched'),
])
def test_rejections(data, preferences, update, code):
    result = generate(data, preferences.model_copy(update=update))
    assert result.status == 'no_results'
    assert code in [r.code for r in result.reasons]


def test_budget_boundary(data, preferences):
    assert generate(data,preferences.model_copy(update={'budget_kzt':40100})).trips[0].remaining_budget_kzt == 0


def test_missing_prices(data, preferences):
    data.costs[0].estimate = None
    data.costs[0].kind = 'unknown'
    assert generate(data,preferences).status == 'no_results'


def test_missing_return_time(data, preferences):
    for edge in data.transport.connections:
        if edge.id.endswith('back'):
            edge.minutes = None
    assert generate(data,preferences).status == 'no_results'


def test_missed_departure(data, preferences):
    for edge in data.transport.connections:
        if edge.id.endswith('back'):
            edge.departures = [600]
    assert generate(data,preferences).status == 'no_results'


def test_public_needs_schedule(data, preferences):
    for edge in data.transport.connections:
        edge.departures = None
    assert generate(data,preferences).status == 'no_results'


def test_season_each_day(data, preferences):
    for d in data.destinations:
        d.open_months = [7,8]
    assert generate(data,preferences).status == 'no_results'


def test_opening_hours(data, preferences):
    for d in data.destinations:
        d.closes_minute=610
    assert generate(data,preferences).status == 'no_results'


def test_missing_hours(data, preferences):
    for d in data.destinations:
        d.opens_minute=None
    assert generate(data,preferences).status == 'no_results'


def test_capacity(data, preferences):
    for route in data.transport.routes:
        route.max_travelers=1
    result=generate(data,preferences.model_copy(update={'travelers':2}))
    assert result.status=='no_results'
    assert 'capacity_exceeded' in [r.code for r in result.reasons]


def test_date_interval(data, preferences):
    p = TripPreferences.model_validate(preferences.model_dump() | {'start_date':'2030-12-30'})
    assert generate(data,p).status == 'no_results'


def test_empty_data(preferences):
    data=Dataset(destinations=[],transport={'connections':[],'routes':[]},costs=[],sources=[])
    assert generate(data,preferences).reasons[0].code == 'dataset_empty'


@pytest.mark.parametrize('change', ['duplicate','source','cost','reverse','activity','lodging'])
def test_reject_broken_dataset(data, change):
    payload=data.model_dump(mode='json')
    if change=='duplicate': payload['destinations'].append(payload['destinations'][0])
    if change=='source': payload['destinations'][0]['source_ids']=['missing']
    if change=='cost': payload['transport']['connections'][0]['cost_id']='missing'
    if change=='reverse': payload['transport']['connections'][0]['origin']='wrong'
    if change=='activity': payload['transport']['routes'][0]['activity_cost_ids']={}
    if change=='lodging': payload['transport']['routes'][-1]['accommodation_cost_id']=None
    with pytest.raises(ValidationError): Dataset.model_validate(payload)


@pytest.mark.parametrize('update', [{'budget_kzt':-1},{'budget_kzt':1.2},{'budget_kzt':True},{'days':0},{'travelers':0},{'travelers':21},{'transport':'plane'},{'extra':1}])
def test_input_validation(preferences, update):
    with pytest.raises(ValidationError): TripPreferences.model_validate(preferences.model_dump() | update)
