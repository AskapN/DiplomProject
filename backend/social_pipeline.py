from rest_framework_simplejwt.tokens import RefreshToken


def create_jwt_tokens(strategy, details, response=None, user=None, *args, **kwargs):
    """Создает JWT токены и сохраняет в сессию для последующего получения клиентом"""
    if user:
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        request = strategy.request
        request.session['social_auth_access_token'] = access_token
        request.session['social_auth_refresh_token'] = refresh_token

        return {
            'access': access_token,
            'refresh': refresh_token,
        }
    return {}