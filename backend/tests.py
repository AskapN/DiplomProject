from django.test import TestCase, override_settings
from django.core.cache import cache
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from rest_framework.test import APITestCase
from rest_framework import status

from unittest.mock import patch, MagicMock
from io import BytesIO
from PIL import Image as PILImage

from backend.models import CustomUser, UserRole, Shop, Category, Product, ProductInfo, ProductImage
from backend.throttling import (
    RegisterRateThrottle, LoginRateThrottle,
    VerifyEmailRateThrottle, PartnerUpdateRateThrottle,
)

def _make_image_file(name='test.jpg', size=(100, 100), fmt='JPEG'):
    """Вспомогательная функция: создаёт in-memory JPEG для загрузки."""
    buf = BytesIO()
    img = PILImage.new('RGB', size, color=(100, 150, 200))
    img.save(buf, format=fmt)
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type='image/jpeg')


_LOCMEM_CACHE = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}


@override_settings(CACHES=_LOCMEM_CACHE)
class RegisterThrottleTest(APITestCase):
    """Тесты тротлинга для регистрации (RegisterRateThrottle, 3/hour)"""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    @patch.object(RegisterRateThrottle, 'THROTTLE_RATES', {'register': '3/minute'})
    def test_allowed_within_limit(self):
        url = reverse('register')
        for i in range(3):
            response = self.client.post(url, {}, format='json')
            self.assertNotEqual(
                response.status_code, status.HTTP_429_TOO_MANY_REQUESTS,
                f'Запрос {i + 1} заблокирован раньше лимита'
            )

    @patch.object(RegisterRateThrottle, 'THROTTLE_RATES', {'register': '3/minute'})
    def test_blocked_after_limit(self):
        url = reverse('register')
        for _ in range(3):
            self.client.post(url, {}, format='json')
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    @patch.object(RegisterRateThrottle, 'THROTTLE_RATES', {'register': '3/minute'})
    def test_retry_after_header_present(self):
        url = reverse('register')
        for _ in range(3):
            self.client.post(url, {}, format='json')
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertTrue(response.has_header('Retry-After'))


@override_settings(CACHES=_LOCMEM_CACHE)
class LoginThrottleTest(APITestCase):
    """Тесты тротлинга для аутентификации (LoginRateThrottle, 10/minute)"""

    def setUp(self):
        cache.clear()
        buyer_role, _ = UserRole.objects.get_or_create(name=UserRole.RoleChoices.BUYER)
        self.user = CustomUser.objects.create_user(
            username='logintest',
            email='logintest@example.com',
            password='testpass123',
        )
        self.user.role = buyer_role
        self.user.save()

    def tearDown(self):
        cache.clear()

    @patch.object(LoginRateThrottle, 'THROTTLE_RATES', {'login': '3/minute'})
    def test_anonymous_blocked_after_limit(self):
        url = reverse('login')
        data = {'email': 'nobody@example.com', 'password': 'wrong'}
        for i in range(3):
            response = self.client.post(url, data, format='json')
            self.assertNotEqual(
                response.status_code, status.HTTP_429_TOO_MANY_REQUESTS,
                f'Запрос {i + 1} заблокирован раньше лимита'
            )
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    @patch.object(LoginRateThrottle, 'THROTTLE_RATES', {'login': '3/minute'})
    def test_authenticated_user_also_throttled(self):
        """Аутентифицированный пользователь тоже должен тротлироваться (исправление)"""
        self.client.force_authenticate(user=self.user)
        url = reverse('login')
        data = {'email': self.user.email, 'password': 'testpass123'}
        for i in range(3):
            response = self.client.post(url, data, format='json')
            self.assertNotEqual(
                response.status_code, status.HTTP_429_TOO_MANY_REQUESTS,
                f'Запрос {i + 1} заблокирован раньше лимита'
            )
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    @patch.object(LoginRateThrottle, 'THROTTLE_RATES', {'login': '3/minute'})
    def test_retry_after_header_present(self):
        url = reverse('login')
        data = {'email': 'nobody@example.com', 'password': 'wrong'}
        for _ in range(3):
            self.client.post(url, data, format='json')
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertTrue(response.has_header('Retry-After'))


@override_settings(CACHES=_LOCMEM_CACHE)
class VerifyEmailThrottleTest(APITestCase):
    """Тесты тротлинга для верификации email (VerifyEmailRateThrottle, 5/hour)"""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    @patch.object(VerifyEmailRateThrottle, 'THROTTLE_RATES', {'verify_email': '3/minute'})
    def test_allowed_within_limit(self):
        url = reverse('verify-email')
        for i in range(3):
            response = self.client.get(url)
            self.assertNotEqual(
                response.status_code, status.HTTP_429_TOO_MANY_REQUESTS,
                f'Запрос {i + 1} заблокирован раньше лимита'
            )

    @patch.object(VerifyEmailRateThrottle, 'THROTTLE_RATES', {'verify_email': '3/minute'})
    def test_blocked_after_limit(self):
        url = reverse('verify-email')
        for _ in range(3):
            self.client.get(url)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    @patch.object(VerifyEmailRateThrottle, 'THROTTLE_RATES', {'verify_email': '3/minute'})
    def test_retry_after_header_present(self):
        url = reverse('verify-email')
        for _ in range(3):
            self.client.get(url)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertTrue(response.has_header('Retry-After'))


@override_settings(CACHES=_LOCMEM_CACHE)
class PartnerUpdateThrottleTest(APITestCase):
    """Тесты тротлинга для загрузки прайса (PartnerUpdateRateThrottle, 10/hour)"""

    def setUp(self):
        cache.clear()
        shop_role, _ = UserRole.objects.get_or_create(name=UserRole.RoleChoices.SHOP)
        self.user = CustomUser.objects.create_user(
            username='shopowner',
            email='shopowner@example.com',
            password='testpass123',
        )
        self.user.role = shop_role
        self.user.save()
        Shop.objects.create(name='Test Shop', user=self.user)
        self.client.force_authenticate(user=self.user)

    def tearDown(self):
        cache.clear()

    @patch.object(PartnerUpdateRateThrottle, 'THROTTLE_RATES', {'partner_update': '3/minute'})
    def test_allowed_within_limit(self):
        url = reverse('partner-update')
        for i in range(3):
            response = self.client.post(url, {}, format='json')
            self.assertNotEqual(
                response.status_code, status.HTTP_429_TOO_MANY_REQUESTS,
                f'Запрос {i + 1} заблокирован раньше лимита'
            )

    @patch.object(PartnerUpdateRateThrottle, 'THROTTLE_RATES', {'partner_update': '3/minute'})
    def test_blocked_after_limit(self):
        url = reverse('partner-update')
        for _ in range(3):
            self.client.post(url, {}, format='json')
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    @patch.object(PartnerUpdateRateThrottle, 'THROTTLE_RATES', {'partner_update': '3/minute'})
    def test_retry_after_header_present(self):
        url = reverse('partner-update')
        for _ in range(3):
            self.client.post(url, {}, format='json')
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertTrue(response.has_header('Retry-After'))


class ImageKitModelFieldsTest(TestCase):
    """Тесты корректности полей imagekit на моделях."""

    def test_no_circular_import(self):
        """Импорт models не вызывает ошибок (нет кругового импорта)."""
        from backend import models  # noqa
        self.assertTrue(True)

    def test_customuser_avatar_is_processed_image_field(self):
        """avatar у CustomUser — ProcessedImageField."""
        from imagekit.models import ProcessedImageField
        field = CustomUser._meta.get_field('avatar')
        self.assertIsInstance(field, ProcessedImageField)

    def test_customuser_has_avatar_spec_fields(self):
        """У CustomUser есть ImageSpecField: avatar_thumbnail и avatar_medium."""
        from imagekit.models.fields.utils import ImageSpecFileDescriptor
        for attr in ('avatar_thumbnail', 'avatar_medium'):
            descriptor = CustomUser.__dict__.get(attr)
            self.assertIsNotNone(descriptor, f'{attr} отсутствует на CustomUser')
            self.assertIsInstance(descriptor, ImageSpecFileDescriptor, f'{attr} должен быть ImageSpecFileDescriptor')

    def test_productimage_is_processed_image_field(self):
        """image у ProductImage — ProcessedImageField."""
        from imagekit.models import ProcessedImageField
        field = ProductImage._meta.get_field('image')
        self.assertIsInstance(field, ProcessedImageField)

    def test_productimage_has_spec_fields(self):
        """У ProductImage есть ImageSpecField: image_small, image_medium, image_large."""
        from imagekit.models.fields.utils import ImageSpecFileDescriptor
        for attr in ('image_small', 'image_medium', 'image_large'):
            descriptor = ProductImage.__dict__.get(attr)
            self.assertIsNotNone(descriptor, f'{attr} отсутствует на ProductImage')
            self.assertIsInstance(descriptor, ImageSpecFileDescriptor, f'{attr} должен быть ImageSpecFileDescriptor')

    def test_smart_resize_not_imported(self):
        """SmartResize не должен импортироваться (его нет в imagekit)."""
        import backend.models as m
        self.assertFalse(hasattr(m, 'SmartResize'))


class ImageKitSignalTest(TestCase):
    """Тесты сигналов post_save для генерации миниатюр."""

    def setUp(self):
        buyer_role, _ = UserRole.objects.get_or_create(name=UserRole.RoleChoices.BUYER)
        self.user = CustomUser.objects.create_user(
            username='imgtest', email='imgtest@example.com', password='pass1234'
        )
        self.user.role = buyer_role
        self.user.save()

    @patch('backend.tasks.generate_all_thumbnails_for_user.delay')
    def test_signal_fires_when_avatar_set(self, mock_delay):
        """Сигнал запускает Celery-таску при сохранении аватара."""
        self.user.avatar = _make_image_file()
        self.user.save(update_fields=['avatar'])
        mock_delay.assert_called_once_with(self.user.id)

    @patch('backend.tasks.generate_all_thumbnails_for_user.delay')
    def test_signal_not_fired_when_avatar_unchanged(self, mock_delay):
        """Сигнал НЕ запускает таску, если avatar не в update_fields."""
        self.user.save(update_fields=['first_name'])
        mock_delay.assert_not_called()

    @patch('backend.tasks.generate_all_thumbnails_for_user.delay')
    def test_signal_not_fired_when_avatar_empty(self, mock_delay):
        """Сигнал НЕ запускает таску, если аватара нет."""
        self.user.avatar = None
        self.user.save(update_fields=['avatar'])
        mock_delay.assert_not_called()

    @patch('backend.tasks.generate_all_thumbnails_for_product.delay')
    def test_product_image_signal_fires(self, mock_delay):
        """Сигнал запускает таску при сохранении ProductImage."""
        shop = Shop.objects.create(name='TestShop', user=self.user)
        category = Category.objects.create(name='TestCat')
        category.shops.add(shop)
        product = Product.objects.create(name='TestProduct', category=category)
        product_info = ProductInfo.objects.create(
            product=product, shop=shop, name='TestInfo',
            quantity=10, price='100.00', price_rrc='120.00'
        )
        img = ProductImage(product_info=product_info, image=_make_image_file())
        img.save()
        mock_delay.assert_called_once_with(img.id)


class ImageKitTaskTest(TestCase):
    """Тесты Celery-тасок для генерации миниатюр."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='tasktest', email='tasktest@example.com', password='pass1234'
        )

    @patch('backend.tasks.ImageCacheFile')
    def test_generate_all_thumbnails_for_user_calls_generate(self, mock_cache_cls):
        """generate_all_thumbnails_for_user вызывает ImageCacheFile.generate для каждого spec."""
        mock_instance = MagicMock()
        mock_cache_cls.return_value = mock_instance
        self.user.avatar = _make_image_file()
        self.user.save(update_fields=['avatar'])

        from backend.tasks import generate_all_thumbnails_for_user
        generate_all_thumbnails_for_user(self.user.id)

        self.assertEqual(mock_cache_cls.call_count, 2)
        self.assertEqual(mock_instance.generate.call_count, 2)

    @patch('backend.tasks.ImageCacheFile')
    def test_generate_thumbnails_for_nonexistent_user_does_not_raise(self, mock_cache_cls):
        """Таска не падает, если пользователь не найден."""
        from backend.tasks import generate_all_thumbnails_for_user
        generate_all_thumbnails_for_user(999999)
        mock_cache_cls.assert_not_called()


class ImageKitSerializerTest(TestCase):
    """Тесты сериализаторов: наличие URL-полей миниатюр, отсутствие дублирования."""

    def test_product_image_serializer_has_url_fields(self):
        """ProductImageSerializer содержит поля *_url для миниатюр."""
        from backend.serializers import ProductImageSerializer
        fields = ProductImageSerializer().fields
        for field_name in ('image_url', 'image_small_url', 'image_medium_url', 'image_large_url'):
            self.assertIn(field_name, fields, f'Поле {field_name} отсутствует')

    def test_product_image_serializer_no_raw_image_fields(self):
        """ProductImageSerializer не содержит сырых ImageField для миниатюр."""
        from rest_framework.fields import ImageField
        from backend.serializers import ProductImageSerializer
        fields = ProductImageSerializer().fields
        for field_name in ('image_small', 'image_medium', 'image_large'):
            if field_name in fields:
                self.assertNotIsInstance(
                    fields[field_name], ImageField,
                    f'{field_name} не должен быть ImageField'
                )

    def test_user_serializer_has_url_fields(self):
        """UserSerializer содержит поля *_url для миниатюр аватара."""
        from backend.serializers import UserSerializer
        fields = UserSerializer().fields
        for field_name in ('avatar_thumbnail_url', 'avatar_medium_url'):
            self.assertIn(field_name, fields, f'Поле {field_name} отсутствует')