from django.http import JsonResponse
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from requests import get
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

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

