from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class RegisterRateThrottle(AnonRateThrottle):
    """Ограничение частоты регистрации"""
    scope = 'register'


class LoginRateThrottle(AnonRateThrottle):
    """Ограничение частоты логина"""
    scope = 'login'

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = request.user.pk
        else:
            ident = self.get_ident(request)
        return self.cache_format % {'scope': self.scope, 'ident': ident}


class VerifyEmailRateThrottle(AnonRateThrottle):
    """Ограничение частоты подтверждения email"""
    scope = 'verify_email'


class PartnerUpdateRateThrottle(UserRateThrottle):
    """Ограничение частоты загрузки прайса поставщика"""
    scope = 'partner_update'
