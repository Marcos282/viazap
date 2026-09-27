import uuid

from django.conf import settings
from django.utils.deprecation import MiddlewareMixin

from .models import AcessoSite


class AnalyticsMiddleware(MiddlewareMixin):
    excluded_prefixes = ('/admin/', '/painel/', '/static/', '/media/', '/api/')
    excluded_paths = {'/', '/favicon.ico', '/robots.txt', '/manifest.json'}
    excluded_extensions = ('.css', '.js', '.map', '.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.ico', '.woff', '.woff2')
    cookie_name = 'viazap_visitor'

    def process_request(self, request):
        request.analytics_visitor_key = request.COOKIES.get(self.cookie_name) or uuid.uuid4().hex

    def process_response(self, request, response):
        tenant = getattr(request, 'tenant', None)
        path = request.path or ''
        if (
            tenant is not None
            and request.method == 'GET'
            and response.status_code < 400
            and path not in self.excluded_paths
            and not path.startswith(self.excluded_prefixes)
            and not path.lower().endswith(self.excluded_extensions)
            and 'text/html' in response.get('Content-Type', '')
        ):
            AcessoSite.objects.create(
                tenant=tenant,
                pagina=path[:500],
                visitor_key=request.analytics_visitor_key,
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:1000],
            )

        if not request.COOKIES.get(self.cookie_name):
            response.set_cookie(
                self.cookie_name,
                request.analytics_visitor_key,
                max_age=60 * 60 * 24 * 365,
                httponly=True,
                samesite='Lax',
                secure=not settings.DEBUG,
            )
        return response
