from rest_framework import permissions


class IsAdminUser(permissions.IsAdminUser):
    """
    Разрешает доступ только администраторам.
    """
    def has_permission(self, request, view):
        return (
                request.user and
                request.user.is_authenticated and
                request.user.role and
                request.user.role.name == 'admin'
        )


class IsShopUser(permissions.BasePermission):
    """
    Разрешает доступ только владельцам магазинов.
    """
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.role and
            request.user.role.name == 'shop'
        )


class IsShopEmployee(permissions.BasePermission):
    """
    Разрешает доступ только сотрудникам магазинов.
    """
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.role and
            request.user.role.name == 'shop_employee'
        )


class IsBuyer(permissions.BasePermission):
    """
    Разрешает доступ только покупателям.
    """
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.role and
            request.user.role.name == 'buyer'
        )


class IsShopOrShopEmployee(permissions.BasePermission):
    """
    Разрешает доступ владельцам магазинов и их сотрудникам.
    """
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.role and
            request.user.role.name in ['shop', 'shop_employee']
        )


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Разрешает доступ к объекту только его владельцу на запись,
    остальным только на чтение.
    """

    def has_object_permission(self, request, view, obj):
        # Разрешаем чтение всем
        if request.method in permissions.SAFE_METHODS:
            return True

        # Разрешаем запись только владельцу
        if hasattr(obj, 'user'):
            return obj.user == request.user
        elif hasattr(obj, 'owner'):
            return obj.owner == request.user
        elif hasattr(obj, 'shop') and hasattr(obj.shop, 'user'):
            return obj.shop.user == request.user

        return False


class IsShopOwnerOrEmployee(permissions.BasePermission):
    """
    Разрешает доступ к объекту магазина владельцу или сотрудникам этого магазина.
    """

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False

        # Владелец магазина
        if hasattr(obj, 'user') and obj.user == request.user:
            return True

        # Сотрудник магазина
        if hasattr(obj, 'employees'):
            return obj.employees.filter(
                user=request.user,
                is_active=True
            ).exists()

        # Если объект связан с магазином
        if hasattr(obj, 'shop'):
            if obj.shop.user == request.user:
                return True
            return obj.shop.employees.filter(
                user=request.user,
                is_active=True
            ).exists()

        return False


class IsOrderOwner(permissions.BasePermission):
    """
    Разрешает доступ к заказу только его владельцу или администратору.
    """

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False

        # Администратор имеет доступ ко всем заказам
        if request.user.role and request.user.role.name == 'admin':
            return True

        # Владелец заказа
        if hasattr(obj, 'user') and obj.user == request.user:
            return True

        # Владелец магазина, если товары из его магазина
        if hasattr(obj, 'order_items'):
            shop_ids = obj.order_items.values_list('shop_id', flat=True).distinct()
            from backend.models import Shop
            return Shop.objects.filter(
                id__in=shop_ids,
                user=request.user
            ).exists()

        return False
