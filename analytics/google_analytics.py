from dataclasses import dataclass

from django.core.cache import cache
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest
from google.api_core.exceptions import GoogleAPICallError, PermissionDenied
from google.auth.exceptions import DefaultCredentialsError


class GoogleAnalyticsError(Exception):
    pass


@dataclass(frozen=True)
class GoogleAnalyticsReport:
    totals: dict
    daily: list
    pages: list


def _metric_values(row, names):
    return {name: int(float(row.metric_values[index].value or 0)) for index, name in enumerate(names)}


def get_google_analytics_report(*, tenant_id, property_id, days):
    if not property_id or not property_id.isdigit():
        raise GoogleAnalyticsError('Cadastre o ID numérico da propriedade GA4 nas configurações da loja.')
    cache_key = f'ga4-report:{tenant_id}:{property_id}:{days}'
    cached = cache.get(cache_key)
    if cached:
        return cached
    try:
        client = BetaAnalyticsDataClient()
        totals_response = client.run_report(RunReportRequest(
            property=f'properties/{property_id}',
            date_ranges=[DateRange(start_date=f'{days - 1}daysAgo', end_date='today')],
            metrics=[Metric(name=name) for name in ('activeUsers', 'sessions', 'screenPageViews', 'eventCount')],
        ))
        daily_response = client.run_report(RunReportRequest(
            property=f'properties/{property_id}',
            date_ranges=[DateRange(start_date=f'{days - 1}daysAgo', end_date='today')],
            dimensions=[Dimension(name='date')],
            metrics=[Metric(name='activeUsers'), Metric(name='sessions'), Metric(name='screenPageViews')],
            order_bys=[{'dimension': {'dimension_name': 'date'}}],
        ))
        pages_response = client.run_report(RunReportRequest(
            property=f'properties/{property_id}',
            date_ranges=[DateRange(start_date=f'{days - 1}daysAgo', end_date='today')],
            dimensions=[Dimension(name='pagePath')],
            metrics=[Metric(name='screenPageViews'), Metric(name='activeUsers')],
            order_bys=[{'metric': {'metric_name': 'screenPageViews'}, 'desc': True}],
            limit=10,
        ))
    except DefaultCredentialsError as exc:
        raise GoogleAnalyticsError('A conta de serviço do Google Analytics ainda não foi configurada no servidor.') from exc
    except PermissionDenied as exc:
        raise GoogleAnalyticsError('A conta de serviço não tem acesso a esta propriedade do Google Analytics.') from exc
    except GoogleAPICallError as exc:
        raise GoogleAnalyticsError('Não foi possível consultar o Google Analytics agora.') from exc

    total_names = ('activeUsers', 'sessions', 'screenPageViews', 'eventCount')
    totals = _metric_values(totals_response.rows[0], total_names) if totals_response.rows else dict.fromkeys(total_names, 0)
    daily = []
    for row in daily_response.rows:
        daily.append({'date': row.dimension_values[0].value, **_metric_values(row, total_names[:3])})
    pages = []
    for row in pages_response.rows:
        pages.append({'path': row.dimension_values[0].value, **_metric_values(row, ('screenPageViews', 'activeUsers'))})
    report = GoogleAnalyticsReport(totals=totals, daily=daily, pages=pages)
    cache.set(cache_key, report, 300)
    return report
