from django.test import TestCase, override_settings
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from unittest.mock import patch

from backend.models import CustomUser, UserRole, Shop
from backend.throttling import (
    RegisterRateThrottle, LoginRateThrottle,
    VerifyEmailRateThrottle, PartnerUpdateRateThrottle,
)

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