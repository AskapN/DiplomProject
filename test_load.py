#!/usr/bin/env python
"""
Скрипт для тестирования загрузки товаров из файла shop1.yaml
"""
import os
import sys
import django

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'orders.settings')
django.setup()

from django.contrib.auth import get_user_model
from backend.views import load_products_from_data, parse_file_content

def test_load_products():
    """Тестирование загрузки товаров из файла"""

    # Создание тестового пользователя
    User = get_user_model()
    user, created = User.objects.get_or_create(
        username='test_shop',
        defaults={
            'email': 'test@example.com',
            'first_name': 'Test',
            'last_name': 'Shop'
        }
    )

    if created:
        user.set_password('testpass123')
        user.save()
        print("✅ Создан тестовый пользователь")

    # Загрузка данных из файла
    file_path = '/home/askar/PycharmProjects/orders/Data/shop1.yaml'

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            file_content = f.read()

        # Парсинг файла
        data = parse_file_content(file_content, 'yaml')
        print("✅ Файл успешно распарсен")

        # Загрузка товаров
        result = load_products_from_data(data, user)

        if result['status']:
            print("✅ Товары успешно загружены!")
            print(f"   Магазин ID: {result['shop_id']}")
            print(f"   Категорий загружено: {result['categories_loaded']}")
            print(f"   Товаров загружено: {result['products_loaded']}")
        else:
            print(f"❌ Ошибка загрузки: {result.get('error', 'Неизвестная ошибка')}")

    except FileNotFoundError:
        print(f"❌ Файл не найден: {file_path}")
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")

if __name__ == '__main__':
    test_load_products()
