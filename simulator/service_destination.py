"""Single service endpoint, isolated from the historical backend selector."""
from urllib.parse import urlsplit


def validate_endpoint(endpoint):
    if not isinstance(endpoint, str):
        raise ValueError('service_endpoint must be a string, never a target list')
    parsed = urlsplit(endpoint)
    if parsed.scheme != 'http' or (parsed.hostname, parsed.port) not in (('127.0.0.1', 8080), ('edos_service', 80)) or parsed.path or parsed.query or parsed.fragment or parsed.username:
        raise ValueError('proxy service_endpoint must be the host endpoint or http://edos_service:80')
    return endpoint


def validate_request_url(url, endpoint):
    if not url.startswith(endpoint + '/'):
        raise ValueError('proxy requests must stay on the configured service endpoint')
