from rest_framework import serializers
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError

from backend.models import (
    CustomUser, UserRole, Shop, Category, Product,
    ProductInfo, ProductImage, Parameter, ProductParameter,
    Order, OrderItem, Contact
)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        if email and password:
            user = authenticate(request=self.context.get('request'),
                                username=email, password=password)

            if not user:
                raise ValidationError('Неверный email или пароль')

            if not user.is_active:
                raise ValidationError('Аккаунт отключен')

            # Проверка верификации email
            if not user.email_verified:
                raise ValidationError('Пожалуйста, подтвердите ваш email перед входом')

            attrs['user'] = user
            return attrs
        else:
            raise ValidationError('Необходимо указать email и пароль')


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'email', 'password', 'password_confirm', 'phone', 'avatar']
        extra_kwargs = {
            'email': {'required': True},
            'first_name': {'required': True},
            'last_name': {'required': True},
            'phone': {'required': False},
            'avatar': {'required': False}
        }

    def validate_email(self, value):
        if CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError('Пользователь с таким email уже существует')
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError('Пароли не совпадают')
        attrs.pop('password_confirm')  # Удаляем подтверждение пароля
        return attrs

    def create(self, validated_data):
        # Устанавливаем роль по умолчанию - покупатель
        try:
            buyer_role = UserRole.objects.get(name='buyer')
        except UserRole.DoesNotExist:
            buyer_role = None

        user = CustomUser.objects.create_user(
            username=validated_data['email'],  # Используем email как username
            email=validated_data['email'],
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            password=validated_data['password'],
            phone=validated_data.get('phone', ''),
            avatar=validated_data.get('avatar'),
            role=buyer_role
        )
        return user


class ParameterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Parameter
        fields = ['name']


class ProductParameterSerializer(serializers.ModelSerializer):
    parameter = ParameterSerializer(read_only=True)

    class Meta:
        model = ProductParameter
        fields = ['parameter', 'value']


class ShopSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shop
        fields = ['id', 'name', 'url']


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name']


class ProductImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ['id', 'image_url', 'created_at']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None


class ProductInfoSerializer(serializers.ModelSerializer):
    shop = ShopSerializer(read_only=True)
    parameters = ProductParameterSerializer(source='product_parameters', many=True, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)

    class Meta:
        model = ProductInfo
        fields = [
            'id', 'shop', 'external_id', 'model', 'name',
            'quantity', 'price', 'price_rrc', 'images', 'parameters'
        ]


class ProductImageUploadSerializer(serializers.Serializer):
    image = serializers.ImageField()


class ProductSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    product_infos = ProductInfoSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = ['id', 'category', 'name', 'product_infos']


class OrderItemSerializer(serializers.ModelSerializer):
    """Сериализатор позиции заказа с расчётной суммой"""
    product_name = serializers.CharField(source='product.name', read_only=True)
    shop_name = serializers.CharField(source='shop.name', read_only=True)
    price = serializers.DecimalField(source='product.price', read_only=True, max_digits=10, decimal_places=2)
    total = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ['id', 'product_name', 'shop_name', 'price', 'quantity', 'total']

    def get_total(self, obj):
        """Расчёт суммы позиции (цена × количество)"""
        return obj.product.price * obj.quantity


class OrderSerializer(serializers.ModelSerializer):
    """Сериализатор заказа с позициями и общей суммой"""
    items = OrderItemSerializer(source='order_items', many=True, read_only=True)
    total_price = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ['id', 'date', 'status', 'items', 'total_price']

    def get_total_price(self, obj):
        """Расчёт общей суммы заказа"""
        return obj.get_total_price()


class ContactSerializer(serializers.ModelSerializer):
    """Сериализатор контактных данных пользователя"""

    class Meta:
        model = Contact
        fields = [
            'id', 'user', 'last_name', 'first_name', 'patronymic',
            'email', 'phone', 'city', 'street', 'house',
            'building', 'structure', 'apartment'
        ]
        extra_kwargs = {
            'user': {'read_only': True}
        }

    def create(self, validated_data):
        """Автоматически привязываем контакт к текущему пользователю"""
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class ConfirmOrderSerializer(serializers.Serializer):
    """Сериализатор для подтверждения заказа с контактными данными"""
    contact_id = serializers.IntegerField(required=False, allow_null=True)
    last_name = serializers.CharField(max_length=40, required=False)
    first_name = serializers.CharField(max_length=40, required=False)
    patronymic = serializers.CharField(max_length=40, required=False)
    email = serializers.EmailField(max_length=50, required=False)
    phone = serializers.CharField(max_length=20, required=False)
    city = serializers.CharField(max_length=40, required=False)
    street = serializers.CharField(max_length=40, required=False)
    house = serializers.CharField(max_length=40, required=False)
    building = serializers.CharField(max_length=40, required=False)
    structure = serializers.CharField(max_length=40, required=False)
    apartment = serializers.CharField(max_length=40, required=False, allow_blank=True)

    def validate(self, attrs):
        """Валидация: либо указан contact_id, либо необходимые контактные данные"""
        contact_id = attrs.get('contact_id')

        if contact_id is not None:
            # Проверяем существование контакта
            try:
                contact = Contact.objects.get(id=contact_id, user=self.context['request'].user)
                attrs['contact'] = contact
            except Contact.DoesNotExist:
                raise serializers.ValidationError('Контакт не найден или не принадлежит вам')
        else:
            # Проверяем наличие всех обязательных полей для нового контакта
            required_fields = ['last_name', 'first_name', 'phone', 'email', 'city', 'street', 'house']
            for field in required_fields:
                if not attrs.get(field):
                    raise serializers.ValidationError(f'Поле {field} обязательно при создании нового контакта')

        return attrs
