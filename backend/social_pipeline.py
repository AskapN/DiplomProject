import secrets as _secrets

from django.core.cache import cache
from rest_framework_simplejwt.tokens import RefreshToken

_CACHE_TTL = 300  # 5 минут


def create_jwt_tokens(strategy, details, response=None, user=None, *args, **kwargs):
    """Создаёт JWT токены и сохраняет в Redis-кэш по одноразовому коду.

    Сессия хранит только непрозрачный код; токены — в кэше с TTL 5 минут.
    Это устраняет утечку токенов через угон сессии и race condition при
    двойном запросе к /api/auth/social/token/.
    """
    if user:
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        code = _secrets.token_urlsafe(32)
        cache.set(f'social_auth_tokens_{code}', {
            'access': access_token,
            'refresh': refresh_token,
        }, timeout=_CACHE_TTL)

        request = strategy.request
        request.session['social_auth_code'] = code

        return {'access': access_token, 'refresh': refresh_token}
    return {}