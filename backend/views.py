from django.http import JsonResponse
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from django.db import models

from requests import get

from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from django_filters import rest_framework as filters

from backend.models import CustomUser, ProductInfo, Order, OrderItem
from backend.serializers import *

from backend.permission import IsShopOrShopEmployee
from backend.utils import load_products_from_data, parse_file_content, send_verification_email

from backend.filters import ProductInfoFilter

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

    def post(self, request, *args, **kwargs):
        try:
            serializer = RegisterSerializer(data=request.data)

            if serializer.is_valid():
                user = serializer.save()

                # Отправляем письмо подтверждения
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

        except Exception as e:
            return Response({
                'status': 'error',
                'message': 'Внутренняя ошибка сервера при регистрации',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
        'product_parameters__parameter'
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

        serializer = self.get_serializer(queryset, many=True)

        # Добавляем статистику
        response_data = {
            'count': queryset.count(),
            'results': serializer.data,
            'filters_available': {
                'price_range': {
                    'min': queryset.aggregate(models.Min('price'))['price__min'],
                    'max': queryset.aggregate(models.Max('price'))['price__max']
                },
                'categories': list(queryset.values_list(
                    'product__category__name', flat=True
                ).distinct()),
                'shops': list(queryset.values_list(
                    'shop__name', flat=True
                ).distinct())
            }
        }

        return Response(response_data)


class CartAPIView(APIView):
    """API для просмотра текущей корзины пользователя"""
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        """Получить корзину пользователя (статус NEW)"""
        cart, created = Order.objects.get_or_create(
            user=request.user,
            status=Order.StatusChoices.NEW
        )
        serializer = OrderSerializer(cart)
        return Response(serializer.data)


class AddToCartAPIView(APIView):
    """API для добавления товара в корзину"""
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        """Добавить товар в корзину"""
        product_info_id = request.data.get('product_info_id')
        quantity = request.data.get('quantity', 1)

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
            defaults={'quantity': quantity}
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


class UpdateCartItemAPIView(APIView):
    """API для обновления количества товара в корзине"""
    permission_classes = [IsAuthenticated]

    def put(self, request, item_id, *args, **kwargs):
        """Обновить количество товара"""
        quantity = request.data.get('quantity')

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