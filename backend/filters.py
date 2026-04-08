import django_filters
from django_filters import rest_framework as filters
from django.db import models
from .models import ProductInfo, Product, Shop, Category, Parameter


class ProductInfoFilter(filters.FilterSet):
    """Фильтры для товаров в магазинах"""

    # Фильтрация по цене
    price_min = filters.NumberFilter(field_name='price', lookup_expr='gte')
    price_max = filters.NumberFilter(field_name='price', lookup_expr='lte')
    price_rrc_min = filters.NumberFilter(field_name='price_rrc', lookup_expr='gte')
    price_rrc_max = filters.NumberFilter(field_name='price_rrc', lookup_expr='lte')

    # Фильтрация по количеству
    quantity_min = filters.NumberFilter(field_name='quantity', lookup_expr='gte')
    quantity_max = filters.NumberFilter(field_name='quantity', lookup_expr='lte')

    # Фильтрация по наличию
    in_stock = filters.BooleanFilter(method='filter_in_stock')

    # Фильтрация по магазину
    shop_id = filters.ModelChoiceFilter(
        field_name='shop',
        queryset=Shop.objects.all(),
        method='filter_shop'
    )
    shop_name = filters.CharFilter(field_name='shop__name', lookup_expr='icontains')

    # Фильтрация по категории
    category_id = filters.NumberFilter(field_name='product__category__id')
    category_name = filters.CharFilter(field_name='product__category__name', lookup_expr='icontains')

    # Поиск по наименованию товара
    name = filters.CharFilter(method='filter_name')

    # Поиск по модели
    model = filters.CharFilter(field_name='model', lookup_expr='icontains')

    # Поиск по внешнему ID
    external_id = filters.NumberFilter(field_name='external_id')

    # Поиск по характеристикам (параметрам)
    parameter = filters.CharFilter(method='filter_parameter')

    # Поиск по поставщику (названию магазина)
    supplier = filters.CharFilter(field_name='shop__name', lookup_expr='icontains')

    class Meta:
        model = ProductInfo
        fields = [
            'price_min', 'price_max', 'price_rrc_min', 'price_rrc_max',
            'quantity_min', 'quantity_max', 'in_stock',
            'shop_id', 'shop_name', 'category_id', 'category_name',
            'name', 'model', 'external_id', 'parameter', 'supplier'
        ]

    def filter_in_stock(self, queryset, name, value):
        """Фильтрация по наличию товара"""
        if value:
            return queryset.filter(quantity__gt=0)
        return queryset.filter(quantity=0)

    def filter_shop(self, queryset, name, value):
        """Фильтрация по магазину"""
        if isinstance(value, str):
            if value.isdigit():
                return queryset.filter(shop_id=int(value))
            else:
                # Если строка не является числом, ищем по имени
                return queryset.filter(shop__name__icontains=value)
        return queryset.filter(shop=value)

    def filter_name(self, queryset, name, value):
        """Поиск по наименованию товара (в ProductInfo и Product)"""
        if value:
            return queryset.filter(
                models.Q(name__icontains=value) |
                models.Q(product__name__icontains=value)
            )
        return queryset

    def filter_parameter(self, queryset, name, value):
        """Поиск по характеристикам товара"""
        if value:
            return queryset.filter(
                product_parameters__value__icontains=value
            ).distinct()
        return queryset