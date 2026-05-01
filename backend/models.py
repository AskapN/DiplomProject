from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import MinValueValidator, RegexValidator
from django.db.models.signals import post_save
from django.dispatch import receiver

from imagekit.models import ProcessedImageField, ImageSpecField
from imagekit.processors import ResizeToFill, ResizeToFit

import secrets

from decimal import Decimal


class UserRole(models.Model):
    """Модель роли пользователя.

    Определяет уровень доступа пользователя в системе.
    """

    class RoleChoices(models.TextChoices):
        ADMIN = 'admin', 'Администратор'
        SHOP = 'shop', 'Магазин'
        SHOP_EMPLOYEE = 'shop_employee', 'Сотрудник магазина'
        BUYER = 'buyer', 'Покупатель'

    name = models.CharField(
        max_length=20,
        choices=RoleChoices.choices,
        unique=True,
        verbose_name='Роль'
    )
    description = models.TextField(verbose_name='Описание', blank=True)

    class Meta:
        verbose_name = 'Роль пользователя'
        verbose_name_plural = 'Роли пользователей'

    def __str__(self):
        return self.get_name_display()


class CustomUser(AbstractUser):
    """Расширенная модель пользователя.

    Наследуется от AbstractUser и добавляет:
    - phone: Телефон с валидацией формата
    - avatar / avatar_thumbnail / avatar_medium: Аватар и авто-миниатюры
    - role: Роль пользователя (admin, shop, shop_employee, buyer)
    - email_verified: Флаг подтверждения email
    - email_verification_token: Одноразовый токен верификации
    - email_verification_token_created_at: Время выдачи токена (TTL 24 ч)
    - created_at / updated_at: Служебные временные метки
    """
    phone = models.CharField(
        max_length=20,
        verbose_name='Телефон',
        blank=True,
        validators=[
            RegexValidator(
                regex=r'^\+?1?\d{9,15}$',
                message='Введите корректный номер телефона'
            )
        ]
    )
    # Оригинальный аватар
    avatar = ProcessedImageField(
        upload_to='avatars/',
        processors=[ResizeToFit(400, 400)],
        format='JPEG',
        options={'quality': 90},
        verbose_name='Аватар',
        null=True,
        blank=True
    )

    # Миниатюра аватара (100x100)
    avatar_thumbnail = ImageSpecField(
        source='avatar',
        processors=[ResizeToFill(100, 100)],
        format='JPEG',
        options={'quality': 85}
    )

    # Средний размер аватара (200x200)
    avatar_medium = ImageSpecField(
        source='avatar',
        processors=[ResizeToFill(200, 200)],
        format='JPEG',
        options={'quality': 90}
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')
    role = models.ForeignKey(
        UserRole,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name='Роль',
        related_name='users'
    )
    email_verified = models.BooleanField(default=False, verbose_name='Email подтвержден')
    email_verification_token = models.CharField(max_length=255, blank=True, null=True,
                                                verbose_name='Токен верификации email')
    email_verification_token_created_at = models.DateTimeField(
        null=True, blank=True, verbose_name='Дата создания токена верификации'
    )

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Список пользователей'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_full_name() or self.username}'

    def has_role(self, role_name):
        """Проверяет, имеет ли пользователь указанную роль."""
        return (
                self.is_authenticated and
                self.role and
                self.role.name == role_name
        )

    def is_admin(self):
        """Проверяет, является ли пользователь администратором."""
        return self.has_role('admin')

    def is_shop(self):
        """Проверяет, является ли пользователь владельцем магазина."""
        return self.has_role('shop')

    def is_shop_employee(self):
        """Проверяет, является ли пользователь сотрудником магазина."""
        return self.has_role('shop_employee')

    def is_buyer(self):
        """Проверяет, является ли пользователь покупателем."""
        return self.has_role('buyer')

    def can_manage_shop(self, shop):
        """Проверяет, может ли пользователь управлять магазином."""
        if not self.is_authenticated:
            return False

        # Владелец магазина
        if hasattr(shop, 'user') and shop.user == self:
            return True

        # Сотрудник магазина
        if hasattr(shop, 'employees'):
            return shop.employees.filter(
                user=self,
                is_active=True
            ).exists()

        return False

    def generate_email_verification_token(self):
        """Генерирует и сохраняет одноразовый токен верификации email с меткой времени."""
        from django.utils import timezone
        self.email_verification_token = secrets.token_urlsafe(32)
        self.email_verification_token_created_at = timezone.now()
        self.save(update_fields=['email_verification_token', 'email_verification_token_created_at'])
        return self.email_verification_token

    def verify_email(self, token):
        """Проверяет токен и подтверждает email. Возвращает False при неверном токене или истёкшем TTL (24 ч)."""
        from django.utils import timezone
        from datetime import timedelta
        if self.email_verification_token != token:
            return False
        if not self.email_verification_token_created_at:
            return False
        if timezone.now() > self.email_verification_token_created_at + timedelta(hours=24):
            return False
        self.email_verified = True
        self.email_verification_token = None
        self.email_verification_token_created_at = None
        self.save(update_fields=['email_verified', 'email_verification_token', 'email_verification_token_created_at'])
        return True


class Shop(models.Model):
    """Модель магазина.

    Представляет торговую точку в системе. Каждый магазин принадлежит одному пользователю.

    Поля:
    - name: Название магазина (максимум 40 символов)
    - url: Ссылка на сайт магазина (опционально)
    - user: Владелец магазина (OneToOne связь с CustomUser)

    Связи:
    - ManyToMany: categories (категории товаров в магазине)
    - ForeignKey: product_infos (информация о товарах в этом магазине)
    - ForeignKey: order_items (позиции заказов из этого магазина)
    """
    name = models.CharField(max_length=40, verbose_name='Название')
    url = models.URLField(verbose_name='ссылка', null=True, blank=True)
    user = models.OneToOneField(CustomUser, verbose_name='Пользователь', on_delete=models.CASCADE, related_name='shop')

    class Meta:
        verbose_name = 'Магазин'
        verbose_name_plural = 'Список магазинов'
        ordering = ['name']

    def __str__(self):
        return self.name


class ShopEmployee(models.Model):
    """Модель сотрудника магазина.

    Связывает пользователя-сотрудника с конкретным магазином.
    """
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        verbose_name='Сотрудник',
        related_name='shop_employments'
    )
    shop = models.ForeignKey(
        Shop,
        on_delete=models.CASCADE,
        verbose_name='Магазин',
        related_name='employees'
    )
    position = models.CharField(max_length=100, verbose_name='Должность')
    is_active = models.BooleanField(default=True, verbose_name='Активен')

    class Meta:
        verbose_name = 'Сотрудник магазина'
        verbose_name_plural = 'Сотрудники магазинов'
        unique_together = ['user', 'shop']

    def __str__(self):
        return f'{self.user} - {self.shop} ({self.position})'


class Category(models.Model):
    """Модель категории товаров.

    Представляет категорию или группу товаров. Категории могут быть связаны с несколькими магазинами.

    Поля:
    - name: Название категории (максимум 40 символов)
    - shops: Магазины, в которых продаются товары этой категории (ManyToMany)

    Связи:
    - ForeignKey: products (товары в этой категории)
    """
    name = models.CharField(max_length=40, verbose_name='Название')
    shops = models.ManyToManyField(Shop, verbose_name='магазины', related_name='categories')

    class Meta:
        verbose_name = 'Категория'
        verbose_name_plural = 'Список категорий'
        ordering = ['name']

    def __str__(self):
        return self.name


class Product(models.Model):
    """Модель товара.

    Представляет базовую информацию о товаре. Один товар может иметь разные характеристики
    в разных магазинах (цена, количество и т.д.).

    Поля:
    - category: Категория товара (ForeignKey на Category)
    - name: Название товара (максимум 40 символов)

    Связи:
    - ForeignKey: product_infos (информация о товаре в разных магазинах)
    """
    category = models.ForeignKey(Category, verbose_name='категория', on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=40, verbose_name='Название')

    class Meta:
        verbose_name = 'Продукт'
        verbose_name_plural = 'Список продуктов'
        ordering = ['name']

    def __str__(self):
        return self.name


class ProductInfo(models.Model):
    """Модель информации о товаре в конкретном магазине.

    Содержит специфическую информацию о товаре в конкретном магазине:
    цена, количество, название (может отличаться от базового).

    Поля:
    - product: Ссылка на базовый товар (ForeignKey на Product)
    - shop: Магазин, в котором продается товар (ForeignKey на Shop)
    - external_id: Внешний ID товара из файла поставщика
    - model: Модель товара
    - name: Название товара в этом магазине (максимум 40 символов)
    - quantity: Количество товара на складе (положительное целое)
    - price: Цена продажи (DecimalField с 2 знаками после запятой)
    - price_rrc: Рекомендуемая розничная цена (DecimalField с 2 знаками после запятой)

    Связи:
    - ForeignKey: product_parameters (параметры этого товара)
    - ForeignKey: order_items (позиции заказов этого товара)
    - ForeignKey: images (изображения товара, см. ProductImage)

    Ограничения:
    - unique_together: ('product', 'shop') - один товар в одном магазине только один раз
    """
    product = models.ForeignKey(Product, verbose_name='продукт', on_delete=models.CASCADE, related_name='product_infos')
    shop = models.ForeignKey(Shop, verbose_name='магазин', on_delete=models.CASCADE, related_name='product_infos')
    external_id = models.PositiveIntegerField(verbose_name='Внешний ID', blank=True, null=True)
    model = models.CharField(max_length=80, verbose_name='Модель', blank=True)
    name = models.CharField(max_length=40, verbose_name='Название')
    quantity = models.PositiveIntegerField(verbose_name='Количество')
    price = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name='Цена', validators=[MinValueValidator(0)]
    )
    price_rrc = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name='Цена РРЦ', validators=[MinValueValidator(0)]
    )

    class Meta:
        verbose_name = 'Информация о продукте'
        verbose_name_plural = 'Список информации о продуктах'
        unique_together = ['product', 'shop']


class ProductImage(models.Model):
    """Модель изображения товара в магазине с поддержкой миниатюр.

    Один товар (ProductInfo) может иметь несколько изображений.
    Файлы сохраняются в директорию media/products/.

    Поля:
    - product_info: Ссылка на товар в магазине (ForeignKey на ProductInfo)
    - image: Файл изображения (ProcessedImageField с авто-обработкой)
    - image_small: Миниатюра 150x150
    - image_medium: Миниатюра 300x300
    - image_large: Миниатюра 800x800
    - created_at: Дата и время добавления (автоматически при создании)
    """
    product_info = models.ForeignKey(
        ProductInfo, on_delete=models.CASCADE,
        related_name='images', verbose_name='Товар'
    )

    # Оригинальное изображение с авто-ресайзом до макс. 1200x1200
    image = ProcessedImageField(
        upload_to='products/',
        processors=[ResizeToFit(1200, 1200)],
        format='JPEG',
        options={'quality': 95},
        verbose_name='Изображение'
    )

    # Миниатюра для списка товаров (150x150)
    image_small = ImageSpecField(
        source='image',
        processors=[ResizeToFill(150, 150)],
        format='JPEG',
        options={'quality': 80}
    )

    # Средний размер для карточки товара (300x300)
    image_medium = ImageSpecField(
        source='image',
        processors=[ResizeToFill(300, 300)],
        format='JPEG',
        options={'quality': 85}
    )

    # Большой размер для галереи (800x800)
    image_large = ImageSpecField(
        source='image',
        processors=[ResizeToFit(800, 800)],
        format='JPEG',
        options={'quality': 90}
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата добавления')

    class Meta:
        verbose_name = 'Изображение товара'
        verbose_name_plural = 'Изображения товара'
        ordering = ['created_at']

    def __str__(self):
        return f'Фото #{self.id} — {self.product_info.name}'


class Parameter(models.Model):
    """Модель параметра товара.

    Представляет наименование параметра товара (например: "Цвет", "Размер", "Вес", "Материал").

    Поля:
    - name: Название параметра (максимум 40 символов)

    Связи:
    - ForeignKey: product_parameters (значения этого параметра для разных товаров)
    """
    name = models.CharField(max_length=40, verbose_name='Название')

    class Meta:
        verbose_name = 'Наименование параметра'
        verbose_name_plural = 'Список параметров'
        ordering = ['name']

    def __str__(self):
        return self.name


class ProductParameter(models.Model):
    """Модель значения параметра товара.

    Связывает конкретный товар в магазине с параметром и его значением.
    Например: товар "Футболка" имеет параметр "Цвет" со значением "Красный".

    Поля:
    - product_info: Ссылка на товар в магазине (ForeignKey на ProductInfo)
    - parameter: Ссылка на параметр (ForeignKey на Parameter)
    - value: Значение параметра (максимум 40 символов)

    Связи:
    - Нет прямых связей (промежуточная модель)

    Ограничения:
    - unique_together: ('product_info', 'parameter') - один параметр для товара только один раз
    """
    product_info = models.ForeignKey(
        ProductInfo, verbose_name='продукт', on_delete=models.CASCADE, related_name='product_parameters'
    )
    parameter = models.ForeignKey(
        Parameter, verbose_name='параметр', on_delete=models.CASCADE, related_name='product_parameters'
    )
    value = models.CharField(max_length=40, verbose_name='Значение')

    class Meta:
        verbose_name = 'Параметр продукта'
        verbose_name_plural = 'Список параметров продукта'
        unique_together = ['product_info', 'parameter']


class Contact(models.Model):
    """Модель контактных данных пользователя.

    Содержит адрес доставки и контактный телефон пользователя.

    Поля:
    - user: Ссылка на пользователя (ForeignKey на CustomUser)
    - last_name: Фамилия получателя (максимум 40 символов)
    - first_name: Имя получателя (максимум 40 символов)
    - patronymic: Отчество получателя (максимум 40 символов)
    - email: Email получателя (максимум 50 символов)
    - phone: Телефон с валидацией международного формата (максимум 20 символов)
    - city: Город доставки (максимум 40 символов)
    - street: Улица доставки (максимум 40 символов)
    - house: Номер дома (максимум 40 символов)
    - building: Корпус (максимум 40 символов, опционально)
    - structure: Строение (максимум 40 символов, опционально)
    - apartment: Квартира (максимум 40 символов, опционально)

    Связи:
    - ForeignKey: orders (заказы, привязанные к этому контакту)
    """
    user = models.ForeignKey(CustomUser, verbose_name='Пользователь', on_delete=models.CASCADE, related_name='contacts')
    last_name = models.CharField(max_length=40, verbose_name='Фамилия')
    first_name = models.CharField(max_length=40, verbose_name='Имя')
    patronymic = models.CharField(max_length=40, verbose_name='Отчество', blank=True)
    city = models.CharField(max_length=40, verbose_name='Город')
    street = models.CharField(max_length=40, verbose_name='Улица')
    house = models.CharField(max_length=40, verbose_name='Дом')
    building = models.CharField(max_length=40, verbose_name='Корпус', blank=True)
    structure = models.CharField(max_length=40, verbose_name='Строение', blank=True)
    apartment = models.CharField(max_length=40, verbose_name='Квартира', blank=True)
    email = models.EmailField(max_length=50, verbose_name='Email')
    phone = models.CharField(
        max_length=20,
        verbose_name='Телефон',
        validators=[
            RegexValidator(
                regex=r'^\+?1?\d{9,15}$',
                message='Введите корректный номер телефона'
            )
        ]
    )

    class Meta:
        verbose_name = 'Контакты пользователя'
        verbose_name_plural = 'Список контактов пользователя'

    def __str__(self):
        return f'г.{self.city}, ул.{self.street}, д.{self.house}, кв.{self.apartment}, тел.:{self.phone}'


class Order(models.Model):
    """Модель заказа.

    Представляет заказ пользователя, содержащий одну или несколько позиций товаров.

    Поля:
    - user: Пользователь, сделавший заказ (ForeignKey на CustomUser)
    - date: Дата и время создания заказа (автоматически при создании)
    - status: Статус заказа (выбор из StatusChoices)

    Статусы заказа:
    - NEW: Новый заказ
    - CONFIRMED: Заказ подтвержден
    - SHIPPED: Заказ отправлен
    - DELIVERED: Заказ доставлен
    - CANCELLED: Заказ отменен

    Связи:
    - ForeignKey: order_items (позиции в этом заказе)

    Методы:
    - get_total_price(): Возвращает общую сумму заказа
    """
    class StatusChoices(models.TextChoices):
        NEW = 'new', 'Новый'
        CONFIRMED = 'confirmed', 'Подтвержден'
        SHIPPED = 'shipped', 'Отправлен'
        DELIVERED = 'delivered', 'Доставлен'
        CANCELLED = 'cancelled', 'Отменен'

    user = models.ForeignKey(CustomUser, verbose_name='Пользователь', on_delete=models.CASCADE, related_name='orders')
    date = models.DateTimeField(auto_now_add=True, verbose_name='Дата')
    status = models.CharField(
        max_length=20,
        verbose_name='Статус',
        choices=StatusChoices.choices,
        default=StatusChoices.NEW
    )
    contact = models.ForeignKey(Contact, verbose_name='Контакт', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='orders')

    class Meta:
        verbose_name = 'Заказ'
        verbose_name_plural = 'Список заказов'
        ordering = ['-date']

    def __str__(self):
        return f'Заказ от {self.date} для {self.user.username}'

    def get_total_price(self):
        """Возвращает общую сумму заказа по ценам, зафиксированным в момент добавления в корзину."""
        total = Decimal('0.00')
        for item in self.order_items.all():
            total += item.price * item.quantity
        return total


class OrderItem(models.Model):
    """Позиция заказа: конкретный товар определённого магазина в заданном количестве.

    Поля:
    - order: Заказ (ForeignKey → Order)
    - product: Товар в магазине (ForeignKey → ProductInfo)
    - shop: Магазин (ForeignKey → Shop)
    - quantity: Количество (≥ 1)
    - price: Цена единицы, зафиксированная на момент добавления в корзину.
      Не изменяется при последующем редактировании прайса магазина.

    Методы:
    - get_price(): Возвращает стоимость позиции (price × quantity)
    """
    order = models.ForeignKey(Order, verbose_name='Заказ', on_delete=models.CASCADE, related_name='order_items')
    product = models.ForeignKey(
        ProductInfo, verbose_name='продукт', on_delete=models.CASCADE, related_name='order_items'
    )
    shop = models.ForeignKey(Shop, verbose_name='магазин', on_delete=models.CASCADE, related_name='order_items')
    quantity = models.PositiveIntegerField(verbose_name='Количество', validators=[MinValueValidator(1)])
    price = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name='Цена на момент добавления'
    )

    class Meta:
        verbose_name = 'Позиция в заказе'
        verbose_name_plural = 'Список позиций в заказе'

    def get_price(self):
        """Возвращает стоимость позиции (зафиксированная цена × количество)"""
        return self.price * self.quantity


@receiver(post_save, sender=ProductImage)
def generate_product_image_thumbnails(sender, instance, created, **kwargs):
    """Автоматическая генерация миниатюр после сохранения изображения товара."""
    if instance.image:
        from backend.tasks import generate_all_thumbnails_for_product
        generate_all_thumbnails_for_product.delay(instance.id)


@receiver(post_save, sender=CustomUser)
def generate_user_avatar_thumbnails(sender, instance, created, **kwargs):
    """Автоматическая генерация миниатюр после сохранения аватара пользователя."""
    update_fields = kwargs.get('update_fields')
    avatar_changed = update_fields is None or 'avatar' in (update_fields or [])
    if instance.avatar and avatar_changed:
        from backend.tasks import generate_all_thumbnails_for_user
        generate_all_thumbnails_for_user.delay(instance.id)