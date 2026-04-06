from rest_framework import serializers
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError

from .models import CustomUser, UserRole


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