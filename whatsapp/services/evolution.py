import logging
from dataclasses import dataclass
from urllib.parse import urlencode

import requests
from django.conf import settings


logger = logging.getLogger(__name__)


class EvolutionError(Exception):
    """Erro seguro para exibição, sem payload ou credenciais."""


class EvolutionUnavailable(EvolutionError):
    pass


class EvolutionNotConfigured(EvolutionError):
    pass


@dataclass(frozen=True)
class EvolutionState:
    state: str
    number: str = ''

    @property
    def connected(self):
        return self.state == 'open'


def instance_name(tenant):
    return f'viazap_tenant_{tenant.pk}'


class EvolutionService:
    def __init__(self):
        self.base_url = settings.EVOLUTION_API_URL
        self.api_key = settings.EVOLUTION_API_KEY
        self.timeout = settings.EVOLUTION_API_TIMEOUT

    def _request(self, method, path, *, json=None, not_found_ok=False):
        if not self.base_url or not self.api_key:
            raise EvolutionNotConfigured('O serviço do WhatsApp ainda não foi configurado no servidor.')
        try:
            response = requests.request(
                method,
                f'{self.base_url}{path}',
                headers={'apikey': self.api_key, 'Content-Type': 'application/json'},
                json=json,
                timeout=self.timeout,
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            logger.warning('Evolution API indisponível em %s: %s', path, type(exc).__name__)
            raise EvolutionUnavailable('Não foi possível comunicar com o serviço do WhatsApp.') from exc
        except requests.RequestException as exc:
            logger.error('Falha na requisição à Evolution em %s: %s', path, type(exc).__name__)
            raise EvolutionError('Não foi possível concluir a operação com o WhatsApp.') from exc

        if not_found_ok and response.status_code == 404:
            return None
        if response.status_code in (401, 403):
            logger.error('Evolution rejeitou a autenticação em %s (HTTP %s).', path, response.status_code)
            raise EvolutionError('O serviço do WhatsApp recusou a autenticação do servidor.')
        if response.status_code >= 400:
            logger.warning('Evolution retornou HTTP %s em %s.', response.status_code, path)
            raise EvolutionError('O serviço do WhatsApp não conseguiu concluir a operação.')
        try:
            return response.json()
        except ValueError as exc:
            logger.error('Evolution retornou resposta inválida em %s.', path)
            raise EvolutionError('O serviço do WhatsApp retornou uma resposta inválida.') from exc

    def find_instance(self, tenant):
        name = instance_name(tenant)
        query = urlencode({'instanceName': name})
        # A Evolution v2.3.7 responde 404 quando o filtro não encontra nenhuma
        # instância. Nesse endpoint, isso significa apenas que ela deve ser criada.
        data = self._request('GET', f'/instance/fetchInstances?{query}', not_found_ok=True)
        if data is None:
            return None
        if isinstance(data, list):
            for item in data:
                if self._instance_name_from_payload(item) == name:
                    return item
            return None
        if isinstance(data, dict) and self._instance_name_from_payload(data) == name:
            return data
        return None

    @staticmethod
    def _instance_name_from_payload(payload):
        if not isinstance(payload, dict):
            return ''
        instance = payload.get('instance')
        if not isinstance(instance, dict):
            instance = payload
        return str(
            instance.get('instanceName')
            or instance.get('name')
            or payload.get('instanceName')
            or payload.get('name')
            or ''
        )

    def create_instance(self, tenant):
        existing = self.find_instance(tenant)
        if existing:
            return existing
        return self._request('POST', '/instance/create', json={
            'instanceName': instance_name(tenant),
            'integration': 'WHATSAPP-BAILEYS',
            'qrcode': True,
        })

    def connect(self, tenant):
        return self._request('GET', f'/instance/connect/{instance_name(tenant)}')

    def connection_state(self, tenant):
        data = self._request('GET', f'/instance/connectionState/{instance_name(tenant)}', not_found_ok=True)
        if not data:
            return EvolutionState('missing')
        instance = data.get('instance', data) if isinstance(data, dict) else {}
        state = str(instance.get('state') or instance.get('connectionStatus') or 'unknown').lower()
        number = str(instance.get('number') or instance.get('ownerJid') or '')
        return EvolutionState(state, number.split('@')[0])

    def logout(self, tenant):
        state = self.connection_state(tenant)
        if state.state == 'missing':
            return None
        return self._request('DELETE', f'/instance/logout/{instance_name(tenant)}', not_found_ok=True)


def extract_qr_code(payload):
    """Aceita os formatos de QR retornados pela Evolution v2."""
    if not isinstance(payload, dict):
        return ''
    qrcode = payload.get('qrcode')
    candidates = [payload.get('base64'), payload.get('code')]
    if isinstance(qrcode, dict):
        candidates = [qrcode.get('base64'), qrcode.get('code'), *candidates]
    elif isinstance(qrcode, str):
        candidates.insert(0, qrcode)
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ''
