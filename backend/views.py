from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.contrib.sites.shortcuts import get_current_site
from django.shortcuts import redirect
from django.urls import reverse
from urllib.parse import urlencode
from django.conf import settings

from requests import get

from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework_simplejwt.tokens import RefreshToken

from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiExample, OpenApiParameter

from backend.models import CustomUser, Shop, ProductInfo, ProductImage, Order, OrderItem, Contact
from backend.serializers import (
    LoginSerializer, RegisterSerializer, ProductInfoSerializer,
    OrderSerializer, ContactSerializer,
    ConfirmOrderSerializer, ProductImageUploadSerializer, ProductImageSerializer
)

from backend.permission import IsShopOrShopEmployee
from backend.utils import (
    load_products_from_data, parse_file_content
)
from backend.tasks import send_verification_email_task, send_order_confirmation_email_task
from backend.filters import ProductInfoFilter
from backend.throttling import (
    RegisterRateThrottle, LoginRateThrottle,
    VerifyEmailRateThrottle, PartnerUpdateRateThrottle
)


@extend_schema(
    tags=['products'],
    summary='Обновление прайса от поставщика',
    description='Загружает товары из YAML или JSON файла по URL или из загруженного файла',
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'url': {'type': 'string', 'format': 'uri', 'description': 'URL на файл с товарами'},
                'file': {'type': 'string', 'format': 'binary', 'description': 'Загруженный файл с товарами'}
            }
        }
    },
    responses={
        200: OpenApiResponse(description='Товары успешно загружены'),
        400: OpenApiResponse(description='Ошибка валидации или парсинга'),
    }
)
class PartnerUpdate(APIView):
    """Импорт прайс-листа (YAML/JSON) по URL или через передачу файла.

    Старые товары магазина удаляются перед загрузкой новых; операция атомарна.
    Ответ содержит ключи: status, products, categories (shop, shop_employee).
    Лимит тротлинга: 10 запросов/ч.
    """

    permission_classes = [IsAuthenticated, IsShopOrShopEmployee]
    throttle_classes = [PartnerUpdateRateThrottle]

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
            return Response({
                'status': 'error',
                'message': 'Укажите URL или загрузите файл'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Обработка ошибок при парсинге
        if error_message:
            return Response({
                'status': 'error',
                'message': error_message
            }, status=status.HTTP_400_BAD_REQUEST)

        if not data:
            return Response({
                'status': 'error',
                'message': 'Не удалось распарсить файл'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Загрузка товаров
        result = load_products_from_data(data, request.user)

        if result['status']:
            return Response({
                'status': 'success',
                'shop': result['shop_id'],
                'products': result['products_loaded'],
                'categories': result['categories_loaded']
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'status': 'error',
                'message': result.get('error', 'Неизвестная ошибка')
            }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['auth'],
    summary='Вход в систему',
    description='Аутентификация пользователя по email и паролю, возвращает JWT токены',
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'email': {'type': 'string', 'format': 'email'},
                'password': {'type': 'string'}
            },
            'required': ['email', 'password']
        }
    },
    responses={
        200: OpenApiResponse(description='Успешная аутентификация'),
        400: OpenApiResponse(description='Неверные данные'),
    },
    examples=[
        OpenApiExample(
            'Пример входа',
            value={'email': 'user@example.com', 'password': 'password123'}
        )
    ]
)
class LoginView(APIView):
    """
    API view для аутентификации пользователя по email и паролю.
    Возвращает JWT токены при успешной аутентификации.
    """
    permission_classes = []
    throttle_classes = [LoginRateThrottle]

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


@extend_schema(
    tags=['auth'],
    summary='Редирект на OAuth-провайдера',
    description='Перенаправляет браузер на страницу авторизации Google. '
                'Поддерживаемый провайдер: `google-oauth2`.',
    parameters=[
        OpenApiParameter(
            name='provider',
            type=str,
            location=OpenApiParameter.PATH,
            description='Идентификатор провайдера (google-oauth2)',
            required=True,
        ),
    ],
    responses={
        302: OpenApiResponse(description='Редирект на страницу провайдера'),
    }
)
class SocialAuthView(APIView):
    """Инициирует социальную авторизацию — редирект на провайдера"""
    permission_classes = []

    def get(self, request, provider):
        auth_url = reverse('social:begin', args=[provider])
        return redirect(auth_url)


@extend_schema(
    tags=['auth'],
    summary='Получить JWT после OAuth',
    description='Возвращает JWT токены из сессии после успешного завершения OAuth-флоу. '
                'Вызывать сразу после редиректа с провайдера.',
    responses={
        200: OpenApiResponse(description='Токены успешно выданы (access + refresh)'),
        400: OpenApiResponse(description='Токены не найдены — OAuth-флоу не завершён'),
    }
)
class SocialAuthTokenView(APIView):
    """Выдача JWT-токенов после OAuth.

    Читает одноразовый код из сессии, извлекает JWT-пару из
    Redis-кэша (описывает их social_pipeline) и удаляет запись.
    Повторный вызов с тем же кодом вернёт 400 (TTL 5 мин).
    """
    permission_classes = []

    def get(self, request):
        from django.core.cache import cache

        code = request.session.pop('social_auth_code', None)
        if not code:
            return Response({
                'status': 'error',
                'message': 'Токены не найдены. Выполните авторизацию через социальную сеть.'
            }, status=status.HTTP_400_BAD_REQUEST)

        tokens = cache.get(f'social_auth_tokens_{code}')
        if not tokens:
            return Response({
                'status': 'error',
                'message': 'Код авторизации истёк или уже использован. Выполните авторизацию заново.'
            }, status=status.HTTP_400_BAD_REQUEST)

        cache.delete(f'social_auth_tokens_{code}')
        return Response({
            'status': 'success',
            'tokens': tokens
        }, status=status.HTTP_200_OK)


@extend_schema(
    tags=['auth'],
    summary='Регистрация нового пользователя',
    description='Создаёт пользователя с ролью "Покупатель" и отправляет письмо подтверждения email',
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'email': {'type': 'string', 'format': 'email'},
                'password': {'type': 'string'},
                'first_name': {'type': 'string'},
                'last_name': {'type': 'string'},
                'phone': {'type': 'string'},
            },
            'required': ['email', 'password']
        }
    },
    responses={
        201: OpenApiResponse(description='Пользователь успешно зарегистрирован'),
        400: OpenApiResponse(description='Ошибка валидации данных'),
    }
)
class RegisterView(APIView):
    """
    API view для регистрации нового пользователя.
    Создает пользователя с ролью "Покупатель" по умолчанию.
    """
    permission_classes = []
    throttle_classes = [RegisterRateThrottle]

    def post(self, request, *args, **kwargs):
        try:
            serializer = RegisterSerializer(data=request.data)

            if serializer.is_valid():
                user = serializer.save()

                # Отправляем письмо подтверждения асинхронно через Celery
                current_site = get_current_site(request)
                send_verification_email_task.delay(user.id, current_site.domain)
                email_sent = True  # Задача поставлена в очередь

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

        except Exception as e:
            return Response({
                'status': 'error',
                'message': 'Внутренняя ошибка сервера при регистрации',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    tags=['auth'],
    summary='Подтверждение email',
    description='Подтверждает email пользователя по токену из письма',
    parameters=[
        OpenApiParameter(name='token', type=str, required=True, description='Токен подтверждения'),
        OpenApiParameter(name='email', type=str, required=True, description='Email пользователя'),
    ],
    responses={
        200: OpenApiResponse(description='Email подтверждён'),
        400: OpenApiResponse(description='Неверный токен или параметры'),
        404: OpenApiResponse(description='Пользователь не найден'),
    }
)
class VerifyEmailView(APIView):
    """
    API view для подтверждения email пользователя.
    """
    permission_classes = []
    throttle_classes = [VerifyEmailRateThrottle]

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


@extend_schema(
    tags=['products'],
    summary='Список товаров',
    description='Получение списка товаров с фильтрацией, поиском и сортировкой',
    parameters=[
        OpenApiParameter(name='name', type=str, description='Поиск по названию'),
        OpenApiParameter(name='category_id', type=int, description='Фильтр по категории'),
        OpenApiParameter(name='shop_id', type=int, description='Фильтр по магазину'),
        OpenApiParameter(name='price_min', type=float, description='Минимальная цена'),
        OpenApiParameter(name='price_max', type=float, description='Максимальная цена'),
        OpenApiParameter(name='ordering', type=str, description='Сортировка (id, -id, price, -price и т.д.)'),
    ],
    responses={200: ProductInfoSerializer}
)
class ProductListAPIView(generics.ListAPIView):
    """
    API для получения списка товаров с возможностью фильтрации и поиска.

    Поддерживаемые фильтры:
    - Ценовой диапазон: price_min, price_max, price_rrc_min, price_rrc_max
    - Количество: quantity_min, quantity_max, in_stock
    - Магазин: shop_id, shop_name, supplier
    - Категория: category_id, category_name
    - Поиск по названию: name
    - Поиск по модели: model
    - Поиск по характеристикам: parameter
    - Внешний ID: external_id
    """
    queryset = ProductInfo.objects.select_related(
        'product', 'shop', 'product__category'
    ).prefetch_related(
        'product_parameters__parameter',
        'images',
    ).all()

    serializer_class = ProductInfoSerializer
    filterset_class = ProductInfoFilter
    permission_classes = []

    def get_queryset(self):
        """Оптимизация запросов и сортировка"""
        queryset = super().get_queryset()

        # Сортировка по параметру из запроса
        ordering = self.request.query_params.get('ordering', '-id')

        # Валидация полей сортировки
        valid_ordering_fields = [
            'id', '-id', 'price', '-price', 'quantity', '-quantity',
            'name', '-name', 'product__name', '-product__name',
            'shop__name', '-shop__name', 'created_at', '-created_at'
        ]

        if ordering in valid_ordering_fields:
            queryset = queryset.order_by(ordering)

        return queryset

    def list(self, request, *args, **kwargs):
        """Переопределение для добавления мета-информации"""
        queryset = self.filter_queryset(self.get_queryset())

        # Пагинация
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        price_stats = queryset.aggregate(
            price_min=models.Min('price'),
            price_max=models.Max('price'),
        )
        serializer = self.get_serializer(queryset, many=True)

        # Добавляем статистику
        response_data = {
            'count': len(serializer.data),
            'results': serializer.data,
            'filters_available': {
                'price_range': {
                    'min': price_stats['price_min'],
                    'max': price_stats['price_max'],
                },
                'categories': list(queryset.values_list(
                    'product__category__name', flat=True
                ).distinct()),
                'shops': list(queryset.values_list(
                    'shop__name', flat=True
                ).distinct()),
            }
        }

        return Response(response_data)


@extend_schema(
    tags=['cart'],
    summary='Получение корзины',
    description='Возвращает текущую корзину пользователя со статусом NEW',
    responses={
        200: OrderSerializer,
        401: OpenApiResponse(description='Требуется аутентификация'),
    }
)
class CartAPIView(APIView):
    """API для просмотра текущей корзины пользователя"""
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        """Получить корзину пользователя (статус NEW)"""
        cart = Order.objects.filter(
            user=request.user,
            status=Order.StatusChoices.NEW
        ).first()

        if not cart:
            return Response({'status': 'success', 'cart': None, 'message': 'Корзина пуста'})

        serializer = OrderSerializer(cart)
        return Response(serializer.data)


@extend_schema(
    tags=['cart'],
    summary='Добавление товара в корзину',
    description='Добавляет товар в корзину или увеличивает количество',
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'product_info_id': {'type': 'integer'},
                'quantity': {'type': 'integer', 'default': 1}
            },
            'required': ['product_info_id']
        }
    },
    responses={
        200: OpenApiResponse(description='Товар добавлен в корзину'),
        400: OpenApiResponse(description='Ошибка валидации или недостаточно товара'),
        404: OpenApiResponse(description='Товар не найден'),
    }
)
class AddToCartAPIView(APIView):
    """Добавление товара в корзину с фиксацией цены.

    Цена снапшотируется в момент добавления и не изменяется
    даже если магазин позже обновит прайс-лист.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        """Добавить товар в корзину, зафиксировав текущую цену."""
        product_info_id = request.data.get('product_info_id')
        try:
            quantity = int(request.data.get('quantity', 1))
        except (TypeError, ValueError):
            return Response({'status': 'error', 'message': 'Количество должно быть числом'},
                            status=status.HTTP_400_BAD_REQUEST)

        if quantity <= 0:
            return Response({'status': 'error', 'message': 'Количество должно быть больше нуля'},
                            status=status.HTTP_400_BAD_REQUEST)

        if not product_info_id:
            return Response({
                'status': 'error',
                'message': 'Не указан product_info_id'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            product_info = ProductInfo.objects.get(id=product_info_id)
        except ProductInfo.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Товар не найден'
            }, status=status.HTTP_404_NOT_FOUND)

        # Проверка наличия товара
        if product_info.quantity < quantity:
            return Response({
                'status': 'error',
                'message': f'Недостаточно товара на складе. Доступно: {product_info.quantity}'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Получение или создание корзины
        cart, created = Order.objects.get_or_create(
            user=request.user,
            status=Order.StatusChoices.NEW
        )

        # Проверка, есть ли уже этот товар в корзине
        order_item, item_created = OrderItem.objects.get_or_create(
            order=cart,
            product=product_info,
            shop=product_info.shop,
            defaults={'quantity': quantity, 'price': product_info.price}
        )

        if not item_created:
            # Обновляем количество, если товар уже в корзине
            order_item.quantity += quantity
            if order_item.quantity > product_info.quantity:
                return Response({
                    'status': 'error',
                    'message': f'Недостаточно товара на складе. Доступно: {product_info.quantity}'
                }, status=status.HTTP_400_BAD_REQUEST)
            order_item.save()

        serializer = OrderSerializer(cart)
        return Response({
            'status': 'success',
            'message': 'Товар добавлен в корзину',
            'cart': serializer.data
        }, status=status.HTTP_200_OK)


@extend_schema(
    tags=['cart'],
    summary='Обновление количества товара в корзине',
    description='Обновляет количество товара в корзине',
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'quantity': {'type': 'integer'}
            },
            'required': ['quantity']
        }
    },
    responses={
        200: OpenApiResponse(description='Количество обновлено'),
        400: OpenApiResponse(description='Ошибка валидации'),
        404: OpenApiResponse(description='Позиция не найдена'),
    }
)
class UpdateCartItemAPIView(APIView):
    """API для обновления количества товара в корзине"""
    permission_classes = [IsAuthenticated]

    def put(self, request, item_id, *args, **kwargs):
        """Обновить количество товара"""
        try:
            quantity = int(request.data.get('quantity', 1))
        except (TypeError, ValueError):
            return Response({'status': 'error', 'message': 'Количество должно быть числом'},
                            status=status.HTTP_400_BAD_REQUEST)

        if quantity <= 0:
            return Response({'status': 'error', 'message': 'Количество должно быть больше нуля'},
                            status=status.HTTP_400_BAD_REQUEST)

        if not quantity:
            return Response({
                'status': 'error',
                'message': 'Не указано количество'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            order_item = OrderItem.objects.get(
                id=item_id,
                order__user=request.user,
                order__status=Order.StatusChoices.NEW
            )
        except OrderItem.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Позиция не найдена'
            }, status=status.HTTP_404_NOT_FOUND)

        # Проверка наличия товара
        if quantity > order_item.product.quantity:
            return Response({
                'status': 'error',
                'message': f'Недостаточно товара на складе. Доступно: {order_item.product.quantity}'
            }, status=status.HTTP_400_BAD_REQUEST)

        order_item.quantity = quantity
        order_item.save()

        cart = order_item.order
        serializer = OrderSerializer(cart)
        return Response({
            'status': 'success',
            'message': 'Количество обновлено',
            'cart': serializer.data
        }, status=status.HTTP_200_OK)


@extend_schema(
    tags=['cart'],
    summary='Удаление товара из корзины',
    description='Удаляет товар из корзины',
    responses={
        200: OpenApiResponse(description='Товар удалён из корзины'),
        404: OpenApiResponse(description='Позиция не найдена'),
    }
)
class RemoveFromCartAPIView(APIView):
    """API для удаления товара из корзины"""
    permission_classes = [IsAuthenticated]

    def delete(self, request, item_id, *args, **kwargs):
        """Удалить товар из корзины"""
        try:
            order_item = OrderItem.objects.get(
                id=item_id,
                order__user=request.user,
                order__status=Order.StatusChoices.NEW
            )
        except OrderItem.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Позиция не найдена'
            }, status=status.HTTP_404_NOT_FOUND)

        cart = order_item.order
        order_item.delete()

        serializer = OrderSerializer(cart)
        return Response({
            'status': 'success',
            'message': 'Товар удалён из корзины',
            'cart': serializer.data
        }, status=status.HTTP_200_OK)


@extend_schema(
    methods=['POST'],
    tags=['contacts'],
    summary='Создание контакта',
    description='Создаёт новый контакт для пользователя',
    request=ContactSerializer,
    responses={
        201: OpenApiResponse(description='Контакт создан'),
        400: OpenApiResponse(description='Ошибка валидации'),
    }
)
@extend_schema(
    methods=['GET'],
    tags=['contacts'],
    summary='Список контактов',
    description='Возвращает список контактов текущего пользователя',
    responses={200: ContactSerializer(many=True)}
)
class ContactAPIView(APIView):
    """API для создания и просмотра контактных данных пользователя"""
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        """Создать новый контакт"""
        serializer = ContactSerializer(data=request.data, context={'request': request})

        if serializer.is_valid():
            contact = serializer.save()
            return Response({
                'status': 'success',
                'message': 'Контакт успешно создан',
                'contact': ContactSerializer(contact).data
            }, status=status.HTTP_201_CREATED)

        return Response({
            'status': 'error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, *args, **kwargs):
        """Получить список контактов текущего пользователя"""
        contacts = Contact.objects.filter(user=request.user)
        serializer = ContactSerializer(contacts, many=True)
        return Response({
            'status': 'success',
            'contacts': serializer.data
        }, status=status.HTTP_200_OK)


@extend_schema(
    methods=['GET'],
    tags=['contacts'],
    summary='Получение контакта',
    description='Возвращает конкретный контакт пользователя',
    responses={
        200: ContactSerializer,
        404: OpenApiResponse(description='Контакт не найден'),
    }
)
@extend_schema(
    methods=['PATCH'],
    tags=['contacts'],
    summary='Обновление контакта',
    description='Частичное обновление контакта',
    request=ContactSerializer(partial=True),
    responses={
        200: OpenApiResponse(description='Контакт обновлён'),
        400: OpenApiResponse(description='Ошибка валидации'),
        404: OpenApiResponse(description='Контакт не найден'),
    }
)
@extend_schema(
    methods=['DELETE'],
    tags=['contacts'],
    summary='Удаление контакта',
    description='Удаляет контакт пользователя',
    responses={
        200: OpenApiResponse(description='Контакт удалён'),
        404: OpenApiResponse(description='Контакт не найден'),
    }
)
class ContactDetailView(APIView):
    """API для просмотра, обновления и удаления конкретного контакта"""
    permission_classes = [IsAuthenticated]

    def get_object(self, contact_id, user):
        """Получить контакт или вернуть 404"""
        try:
            return Contact.objects.get(id=contact_id, user=user)
        except Contact.DoesNotExist:
            return None

    def get(self, request, contact_id, *args, **kwargs):
        """Получить конкретный контакт"""
        contact = self.get_object(contact_id, request.user)
        if not contact:
            return Response({
                'status': 'error',
                'message': 'Контакт не найден'
            }, status=status.HTTP_404_NOT_FOUND)

        serializer = ContactSerializer(contact)
        return Response({
            'status': 'success',
            'contact': serializer.data
        }, status=status.HTTP_200_OK)

    def patch(self, request, contact_id, *args, **kwargs):
        """Частичное обновление контакта"""
        contact = self.get_object(contact_id, request.user)
        if not contact:
            return Response({
                'status': 'error',
                'message': 'Контакт не найден'
            }, status=status.HTTP_404_NOT_FOUND)

        serializer = ContactSerializer(contact, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response({
                'status': 'success',
                'message': 'Контакт успешно обновлен',
                'contact': serializer.data
            }, status=status.HTTP_200_OK)

        return Response({
            'status': 'error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, contact_id, *args, **kwargs):
        """Удалить контакт"""
        contact = self.get_object(contact_id, request.user)
        if not contact:
            return Response({
                'status': 'error',
                'message': 'Контакт не найден'
            }, status=status.HTTP_404_NOT_FOUND)

        contact.delete()
        return Response({
            'status': 'success',
            'message': 'Контакт успешно удален'
        }, status=status.HTTP_200_OK)


@extend_schema(
    tags=['orders'],
    summary='Подтверждение заказа',
    description='Подтверждает корзину как заказ с контактными данными',
    request=ConfirmOrderSerializer,
    responses={
        200: OpenApiResponse(description='Заказ подтверждён'),
        400: OpenApiResponse(description='Ошибка валидации или пустая корзина'),
        404: OpenApiResponse(description='Корзина не найдена'),
    }
)
class ConfirmOrderAPIView(APIView):
    """API для подтверждения заказа с контактными данными"""
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        """Подтвердить заказ с контактными данными"""
        serializer = ConfirmOrderSerializer(data=request.data, context={'request': request})

        if not serializer.is_valid():
            return Response({
                'status': 'error',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        # Получаем корзину пользователя
        try:
            cart = Order.objects.get(user=request.user, status=Order.StatusChoices.NEW)
        except Order.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Корзина пуста'
            }, status=status.HTTP_404_NOT_FOUND)

        # Проверяем, что в корзине есть товары
        if not cart.order_items.exists():
            return Response({
                'status': 'error',
                'message': 'Корзина пуста'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Получаем или создаем контакт
        contact = serializer.validated_data.get('contact')

        with transaction.atomic():
            # Создаём контакт внутри транзакции — откатится при ошибке
            if not contact:
                contact_data = {
                    'user': request.user,
                    'last_name': serializer.validated_data['last_name'],
                    'first_name': serializer.validated_data['first_name'],
                    'patronymic': serializer.validated_data.get('patronymic', ''),
                    'email': serializer.validated_data.get('email', ''),
                    'phone': serializer.validated_data['phone'],
                    'city': serializer.validated_data['city'],
                    'street': serializer.validated_data['street'],
                    'house': serializer.validated_data['house'],
                    'building': serializer.validated_data.get('building', ''),
                    'structure': serializer.validated_data.get('structure', ''),
                    'apartment': serializer.validated_data.get('apartment', ''),
                }
                contact = Contact.objects.create(**contact_data)

            # Блокируем товары от конкурентных изменений
            order_items = cart.order_items.select_related('product').select_for_update()

            # Проверяем остатки ДО изменения статуса
            for item in order_items:
                product_info = item.product
                if product_info.quantity < item.quantity:
                    return Response({
                        'status': 'error',
                        'message': f'Недостаточно товара "{product_info.name}" на складе. '
                                   f'Доступно: {product_info.quantity}, требуется: {item.quantity}'
                    }, status=status.HTTP_400_BAD_REQUEST)

            # Только после успешной проверки — меняем статус и списываем
            cart.contact = contact
            cart.status = Order.StatusChoices.CONFIRMED
            cart.save()

            for item in order_items:
                item.product.quantity -= item.quantity
                item.product.save(update_fields=['quantity'])

        # Отправляем email уведомления асинхронно через Celery
        send_order_confirmation_email_task.delay(cart.id)

        # Сериализуем подтвержденный заказ
        order_serializer = OrderSerializer(cart)

        return Response({
            'status': 'success',
            'message': 'Заказ успешно подтвержден',
            'order': order_serializer.data
        }, status=status.HTTP_200_OK)


@extend_schema(
    tags=['orders'],
    summary='Список заказов',
    description='Возвращает список заказов в зависимости от роли пользователя',
    responses={
        200: OrderSerializer(many=True),
        401: OpenApiResponse(description='Требуется аутентификация'),
    }
)
class OrderListAPIView(APIView):
    """Список заказов с фильтрацией по роли и пагинацией.

    Фильтрация по роли:
    - buyer: только свои заказы
    - shop: заказы с товарами из своего магазина
    - shop_employee: заказы магазинов, в которых сотрудник активен
    - admin: все заказы
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        """Вернуть список заказов с учётом роли пользователя. Поддерживает ?page= для пагинации."""
        user = request.user

        # Если пользователь - покупатель, показываем только его заказы
        _prefetch = ['order_items__product', 'order_items__shop']

        if user.is_buyer():
            orders = Order.objects.filter(user=user).prefetch_related(*_prefetch).order_by('-date')

        # Если пользователь - владелец магазина, показываем заказы с товарами из его магазина
        elif user.is_shop():
            try:
                shop = user.shop
                # Получаем заказы, которые содержат товары из этого магазина
                orders = Order.objects.filter(
                    order_items__shop=shop
                ).distinct().prefetch_related(*_prefetch).order_by('-date')
            except Shop.DoesNotExist:
                orders = Order.objects.none()

        # Если пользователь - сотрудник магазина, показываем заказы с товарами из магазинов, где он работает
        elif user.is_shop_employee():
            # Получаем магазины, где работает сотрудник
            employments = user.shop_employments.filter(is_active=True)
            shop_ids = employments.values_list('shop_id', flat=True)
            # Получаем заказы, которые содержат товары из этих магазинов
            orders = Order.objects.filter(
                order_items__shop_id__in=shop_ids
            ).distinct().prefetch_related(*_prefetch).order_by('-date')

        # Администратор видит все заказы
        elif user.is_admin():
            orders = Order.objects.all().prefetch_related(*_prefetch).order_by('-date')

        else:
            orders = Order.objects.none()

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(orders, request)
        if page is not None:
            serializer = OrderSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = OrderSerializer(orders, many=True)
        return Response({
            'status': 'success',
            'count': len(serializer.data),
            'orders': serializer.data
        }, status=status.HTTP_200_OK)


@extend_schema(
    methods=['GET'],
    tags=['orders'],
    summary='Получение заказа',
    description='Возвращает конкретный заказ с проверкой прав доступа',
    responses={
        200: OrderSerializer,
        404: OpenApiResponse(description='Заказ не найден или нет прав'),
    }
)
@extend_schema(
    methods=['PATCH'],
    tags=['orders'],
    summary='Обновление статуса заказа',
    description='Обновляет статус заказа (для админа, владельца магазина, сотрудника)',
    responses={
        200: OpenApiResponse(description='Статус обновлён'),
        403: OpenApiResponse(description='Нет прав на изменение'),
        404: OpenApiResponse(description='Заказ не найден'),
    }
)
class OrderDetailView(APIView):
    """API для просмотра конкретного заказа с проверкой прав доступа"""
    permission_classes = [IsAuthenticated]

    def get_object(self, order_id, user):
        """Получить заказ с проверкой прав доступа"""
        try:
            order = Order.objects.prefetch_related(
                'order_items__product', 'order_items__shop'
            ).get(id=order_id)

            # Покупатель может видеть только свои заказы
            if user.is_buyer():
                if order.user != user:
                    return None

            # Владелец магазина может видеть заказы с товарами из своего магазина
            elif user.is_shop():
                try:
                    shop = user.shop
                    if not order.order_items.filter(shop=shop).exists():
                        return None
                except Shop.DoesNotExist:
                    return None

            # Сотрудник магазина может видеть заказы с товарами из магазинов, где он работает
            elif user.is_shop_employee():
                employments = user.shop_employments.filter(is_active=True)
                shop_ids = employments.values_list('shop_id', flat=True)
                if not order.order_items.filter(shop_id__in=shop_ids).exists():
                    return None

            # Администратор видит все заказы
            elif not user.is_admin():
                return None

            return order
        except Order.DoesNotExist:
            return None

    def get(self, request, order_id, *args, **kwargs):
        """Получить конкретный заказ"""
        order = self.get_object(order_id, request.user)
        if not order:
            return Response({
                'status': 'error',
                'message': 'Заказ не найден или у вас нет прав на просмотр'
            }, status=status.HTTP_404_NOT_FOUND)

        serializer = OrderSerializer(order)
        return Response({
            'status': 'success',
            'order': serializer.data
        }, status=status.HTTP_200_OK)

    def patch(self, request, order_id, *args, **kwargs):
        """Обновить статус заказа (только для админа, владельца магазина и сотрудника)"""
        user = request.user

        # Проверяем, что пользователь имеет права на изменение статуса
        if not (user.is_admin() or user.is_shop() or user.is_shop_employee()):
            return Response({
                'status': 'error',
                'message': 'У вас нет прав на изменение статуса заказа'
            }, status=status.HTTP_403_FORBIDDEN)

        # Получаем заказ с проверкой прав доступа
        order = self.get_object(order_id, user)
        if not order:
            return Response({
                'status': 'error',
                'message': 'Заказ не найден или у вас нет прав на редактирование'
            }, status=status.HTTP_404_NOT_FOUND)

        # Получаем новый статус
        new_status = request.data.get('status')
        if not new_status:
            return Response({
                'status': 'error',
                'message': 'Не указан новый статус'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Проверяем валидность статуса
        valid_statuses = [choice[0] for choice in Order.StatusChoices.choices]
        if new_status not in valid_statuses:
            return Response({
                'status': 'error',
                'message': f'Недопустимый статус. Доступные статусы: {valid_statuses}'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Обновляем статус
        order.status = new_status
        order.save()

        serializer = OrderSerializer(order)
        return Response({
            'status': 'success',
            'message': 'Статус заказа успешно обновлен',
            'order': serializer.data
        }, status=status.HTTP_200_OK)


@extend_schema(
    methods=['GET'],
    tags=['products'],
    summary='Получение изображений товара',
    description='Возвращает все изображения для указанного товара',
    responses={
        200: OpenApiResponse(description='Список изображений'),
        403: OpenApiResponse(description='Нет доступа к товару'),
        404: OpenApiResponse(description='Товар не найден'),
    }
)
@extend_schema(
    methods=['POST'],
    tags=['products'],
    summary='Загрузка изображения товара',
    description='Загружает новое изображение для товара (только для владельца магазина)',
    request={
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'image': {'type': 'string', 'format': 'binary'}
            },
            'required': ['image']
        }
    },
    responses={
        201: OpenApiResponse(description='Изображение загружено'),
        400: OpenApiResponse(description='Ошибка валидации'),
        403: OpenApiResponse(description='Нет доступа к товару'),
        404: OpenApiResponse(description='Товар не найден'),
    }
)
class ProductImageAPIView(APIView):
    """Получение списка и загрузка изображений товара"""
    permission_classes = [IsAuthenticated, IsShopOrShopEmployee]

    def _get_product_info(self, product_info_id, user):
        """Получить ProductInfo с проверкой принадлежности магазину пользователя"""
        try:
            product_info = ProductInfo.objects.select_related('shop__user').get(
                id=product_info_id
            )
        except ProductInfo.DoesNotExist:
            return None, Response(
                {'status': 'error', 'message': 'Товар не найден'},
                status=status.HTTP_404_NOT_FOUND
            )
        if user.is_shop() and product_info.shop.user != user:
            return None, Response(
                {'status': 'error', 'message': 'Нет доступа к этому товару'},
                status=status.HTTP_403_FORBIDDEN
            )
        return product_info, None

    def get(self, request, product_info_id, *args, **kwargs):
        """Получить все изображения товара"""
        product_info, error = self._get_product_info(product_info_id, request.user)
        if error:
            return error
        images = product_info.images.all()
        serializer = ProductImageSerializer(images, many=True, context={'request': request})
        return Response({'status': 'success', 'images': serializer.data})

    def post(self, request, product_info_id, *args, **kwargs):
        """Добавить новое изображение товара"""
        product_info, error = self._get_product_info(product_info_id, request.user)
        if error:
            return error

        serializer = ProductImageUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'status': 'error', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        product_image = ProductImage.objects.create(
            product_info=product_info,
            image=serializer.validated_data['image']
        )
        result = ProductImageSerializer(product_image, context={'request': request})
        return Response({'status': 'success', 'image': result.data}, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=['products'],
    summary='Удаление изображения товара',
    description='Удаляет конкретное изображение товара (только для владельца магазина)',
    responses={
        200: OpenApiResponse(description='Изображение удалено'),
        403: OpenApiResponse(description='Нет доступа'),
        404: OpenApiResponse(description='Изображение не найдено'),
    }
)
class ProductImageDetailAPIView(APIView):
    """Удаление конкретного изображения товара"""
    permission_classes = [IsAuthenticated, IsShopOrShopEmployee]

    def delete(self, request, product_info_id, image_id, *args, **kwargs):
        """Удалить изображение по ID"""
        try:
            product_image = ProductImage.objects.select_related(
                'product_info__shop__user'
            ).get(id=image_id, product_info_id=product_info_id)
        except ProductImage.DoesNotExist:
            return Response(
                {'status': 'error', 'message': 'Изображение не найдено'},
                status=status.HTTP_404_NOT_FOUND
            )
        if request.user.is_shop() and product_image.product_info.shop.user != request.user:
            return Response(
                {'status': 'error', 'message': 'Нет доступа'},
                status=status.HTTP_403_FORBIDDEN
            )
        product_image.image.delete(save=False)
        product_image.delete()
        return Response({'status': 'success', 'message': 'Изображение удалено'})


@extend_schema(
    tags=['utilities'],
    summary='Тест Sentry / GlitchTip',
    description='Намеренно вызывает исключение для проверки интеграции с GlitchTip/Sentry. '
                'Возвращает 500 при `DEBUG=True`, 403 при `DEBUG=False`.',
    responses={
        500: OpenApiResponse(description='Тестовое исключение (DEBUG=True)'),
        403: OpenApiResponse(description='Доступно только в DEBUG режиме'),
    }
)
class SentryTestView(APIView):
    """Тестовый view для проверки интеграции с GlitchTip/Sentry."""
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        if not settings.DEBUG:
            return Response(
                {'status': 'error', 'message': 'Доступно только в DEBUG режиме'},
                status=status.HTTP_403_FORBIDDEN
            )
        raise Exception('Тестовое исключение для проверки GlitchTip/Sentry')
