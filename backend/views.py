from django.http import JsonResponse
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError

from requests import get

from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from backend.models import CustomUser
from backend.serializers import LoginSerializer, RegisterSerializer

from backend.permission import IsShopOrShopEmployee
from backend.utils import load_products_from_data, parse_file_content


class PartnerUpdate(APIView):
    """
    API класс для обновления прайса от поставщика.
    Поддерживает загрузку товаров из URL и загруженных файлов.
    """

    permission_classes = [IsAuthenticated, IsShopOrShopEmployee]

    def post(self, request, *args, **kwargs):
        """
        POST запрос для обновления товаров.

        Параметры:
        - url (опционально): URL на файл с товарами
        - file (опционально): Загруженный файл с товарами

        Поддерживаемые форматы: YAML, JSON
        """
        # Получение URL или файла
        url = request.data.get('url')
        file = request.FILES.get('file')

        data = None
        error_message = None

        # Загрузка из URL
        if url:
            try:
                validate_url = URLValidator()
                validate_url(url)
                stream = get(url).content
                data = parse_file_content(stream, 'yaml')
            except ValidationError:
                error_message = 'Некорректный URL'
            except Exception as e:
                error_message = f'Ошибка при загрузке файла из URL: {str(e)}'

        # Загрузка из файла
        elif file:
            try:
                # Определение формата файла по расширению
                file_name = file.name.lower()
                if file_name.endswith('.json'):
                    file_format = 'json'
                elif file_name.endswith(('.yaml', '.yml')):
                    file_format = 'yaml'
                else:
                    file_format = 'yaml'  # По умолчанию

                file_content = file.read()
                data = parse_file_content(file_content, file_format)

            except Exception as e:
                error_message = f'Ошибка при загрузке файла: {str(e)}'

        else:
            return JsonResponse({
                'Status': False,
                'Error': 'Укажите URL или загрузите файл'
            })

        # Обработка ошибок при парсинге
        if error_message:
            return JsonResponse({
                'Status': False,
                'Error': error_message
            })

        if not data:
            return JsonResponse({
                'Status': False,
                'Error': 'Не удалось распарсить файл'
            })

        # Загрузка товаров
        result = load_products_from_data(data, request.user)

        if result['status']:
            return JsonResponse({
                'Status': True,
                'Shop': result['shop_id'],
                'Products': result['products_loaded'],
                'Categories': result['categories_loaded']
            }, status=200)
        else:
            return JsonResponse({
                'Status': False,
                'Error': result.get('error', 'Неизвестная ошибка')
            })


class LoginView(APIView):
    """
    API view для аутентификации пользователя по email и паролю.
    Возвращает JWT токены при успешной аутентификации.
    """
    permission_classes = []

    def post(self, request, *args, **kwargs):
        serializer = LoginSerializer(data=request.data, context={'request': request})

        if serializer.is_valid():
            user = serializer.validated_data['user']

            # Генерация JWT токенов
            refresh = RefreshToken.for_user(user)

            return Response({
                'status': 'success',
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'username': user.username,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'role': user.role.name if user.role else None,
                },
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            }, status=status.HTTP_200_OK)

        return Response({
            'status': 'error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class RegisterView(APIView):
    """
    API view для регистрации нового пользователя.
    Создает пользователя с ролью "Покупатель" по умолчанию.
    """
    permission_classes = []


class RegisterView(APIView):
    permission_classes = []

    def post(self, request, *args, **kwargs):
        serializer = RegisterSerializer(data=request.data)

        if serializer.is_valid():
            user = serializer.save()

            # Отправляем письмо подтверждения
            from backend.utils import send_verification_email
            email_sent = send_verification_email(user, request)

            return Response({
                'status': 'success',
                'message': 'Пользователь успешно зарегистрирован. Проверьте вашу почту для подтверждения email.',
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'username': user.username,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'phone': user.phone,
                    'avatar': user.avatar.url if user.avatar else None,
                    'role': user.role.name if user.role else None,
                    'email_verified': user.email_verified,
                },
                'email_sent': email_sent
            }, status=status.HTTP_201_CREATED)

        return Response({
            'status': 'error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class VerifyEmailView(APIView):
    """
    API view для подтверждения email пользователя.
    """
    permission_classes = []

    def get(self, request, *args, **kwargs):
        token = request.GET.get('token')
        email = request.GET.get('email')

        if not token or not email:
            return Response({
                'status': 'error',
                'message': 'Отсутствуют необходимые параметры'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Пользователь не найден'
            }, status=status.HTTP_404_NOT_FOUND)

        if user.email_verified:
            return Response({
                'status': 'info',
                'message': 'Email уже подтвержден'
            }, status=status.HTTP_200_OK)

        if user.verify_email(token):
            # Генерируем токены после подтверждения email
            refresh = RefreshToken.for_user(user)

            return Response({
                'status': 'success',
                'message': 'Email успешно подтвержден',
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'username': user.username,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'email_verified': user.email_verified,
                },
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'status': 'error',
                'message': 'Недействительный или просроченный токен'
            }, status=status.HTTP_400_BAD_REQUEST)