from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from django.contrib.sites.shortcuts import get_current_site

import json
from decimal import Decimal
import yaml

from backend.models import Shop, Category, Product, ProductInfo, Parameter, ProductParameter

def load_products_from_data(data, user):
    """
    Загружает товары и категории из словаря данных.

    Args:
        data (dict): Словарь с данными товаров в формате:
            {
                'shop': 'название магазина',
                'categories': [
                    {'id': 1, 'name': 'Категория 1'},
                    ...
                ],
                'goods': [
                    {
                        'id': 1,           # Внешний ID товара (сохраняется в external_id)
                        'name': 'Товар',
                        'category': 1,     # ID категории из списка categories
                        'model': 'модель', # Модель товара
                        'price': 100.00,
                        'price_rrc': 150.00,
                        'quantity': 10,
                        'parameters': {'Цвет': 'Красный', ...}
                    },
                    ...
                ]
            }
        user: Объект пользователя (владельца магазина)

    Returns:
        dict: Словарь с результатом загрузки:
            {
                'status': bool,           # True при успехе, False при ошибке
                'error': str,             # Сообщение об ошибке (только при status=False)
                'shop_id': int,           # ID созданного/найденного магазина
                'products_loaded': int,   # Количество загруженных товаров
                'categories_loaded': int  # Количество новых созданных категорий
            }

    Примечания:
        - Старые товары магазина удаляются перед загрузкой новых
        - Категории связываются с магазином через ManyToMany
        - Параметры товаров сохраняются в отдельных записях ProductParameter
        - Внешний ID товара сохраняется в поле external_id модели ProductInfo
        - Модель товара сохраняется в поле model модели ProductInfo
    """
    try:
        # Создание или получение магазина
        shop, _ = Shop.objects.get_or_create(
            name=data.get('shop', 'Default Shop'),
            user_id=user.id
        )

        categories_count = 0
        products_count = 0

        # Словарь для быстрого поиска категорий по внешнему ID
        category_map = {}

        # Загрузка категорий
        if 'categories' in data:
            for category_data in data['categories']:
                category_object, created = Category.objects.get_or_create(
                    id=category_data.get('id'),
                    defaults={'name': category_data.get('name', 'Unknown')}
                )
                category_object.shops.add(shop.id)
                category_map[category_data.get('id')] = category_object
                if created:
                    categories_count += 1

        # Удаление старых товаров из магазина
        ProductInfo.objects.filter(shop_id=shop.id).delete()

        # Загрузка товаров
        if 'goods' in data:
            for item in data['goods']:
                try:
                    # Получение категории по внешнему ID
                    category_id = item.get('category')
                    if category_id not in category_map:
                        # Если категория не найдена, пропускаем товар
                        print(f"Категория с ID {category_id} не найдена для товара {item.get('name')}")
                        continue

                    category = category_map[category_id]

                    # Создание товара
                    product, _ = Product.objects.get_or_create(
                        name=item.get('name'),
                        category=category
                    )

                    # Создание информации о товаре в магазине
                    product_info = ProductInfo.objects.create(
                        product_id=product.id,
                        shop_id=shop.id,
                        external_id=item.get('id'),
                        model=item.get('model', ''),
                        name=item.get('name'),
                        quantity=int(item.get('quantity', 0)),
                        price=Decimal(str(item.get('price', 0))),
                        price_rrc=Decimal(str(item.get('price_rrc', 0)))
                    )

                    # Добавление параметров товара
                    if 'parameters' in item:
                        for param_name, param_value in item['parameters'].items():
                            parameter_object, _ = Parameter.objects.get_or_create(name=param_name)
                            ProductParameter.objects.create(
                                product_info_id=product_info.id,
                                parameter_id=parameter_object.id,
                                value=param_value
                            )

                    products_count += 1

                except Exception as e:
                    # Логирование ошибки, но продолжение загрузки
                    print(f"Ошибка при загрузке товара {item.get('name')}: {str(e)}")
                    continue

        return {
            'status': True,
            'shop_id': shop.id,
            'products_loaded': products_count,
            'categories_loaded': categories_count
        }

    except Exception as e:
        return {
            'status': False,
            'error': str(e)
        }

def parse_file_content(file_content, file_format='yaml'):
    """
    Парсит содержимое файла в различных форматах.

    Args:
        file_content: Содержимое файла (байты или строка)
        file_format (str): Формат файла ('yaml', 'json'). По умолчанию 'yaml'

    Returns:
        dict: Распарсенные данные

    Raises:
        ValueError: Если формат не поддерживается
    """
    try:
        if isinstance(file_content, bytes):
            file_content = file_content.decode('utf-8')

        if file_format.lower() in ['yaml', 'yml']:
            return yaml.safe_load(file_content)
        elif file_format.lower() == 'json':
            return json.loads(file_content)
        else:
            raise ValueError(f"Неподдерживаемый формат файла: {file_format}")

    except Exception as e:
        raise ValueError(f"Ошибка при парсинге файла: {str(e)}")


def send_verification_email(user, request):
    """Отправляет письмо с подтверждением email"""
    token = user.generate_email_verification_token()

    # Формируем URL для подтверждения
    current_site = get_current_site(request)
    verify_url = f"http://{current_site.domain}/api/verify-email/?token={token}&email={user.email}"

    subject = 'Подтверждение email'
    message = f'''
    Здравствуйте, {user.first_name}!

    Пожалуйста, подтвердите ваш email, перейдя по ссылке:
    {verify_url}

    Эта ссылка действительна в течение 24 часов.

    Если вы не регистрировались на нашем сайте, просто проигнорируйте это письмо.
    '''

    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Ошибка отправки email: {e}")
        return False