from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import mark_safe
from backend.models import (
    CustomUser, UserRole, Shop, ShopEmployee,
    Category, Product, ProductInfo, ProductImage, Parameter,
    ProductParameter, Contact, Order, OrderItem
)


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'email_verified', 'is_active')
    list_filter = ('role', 'email_verified', 'is_active', 'is_staff')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at', 'avatar_preview')
    fieldsets = UserAdmin.fieldsets + (
        ('Дополнительно', {
            'fields': ('phone', 'avatar', 'avatar_preview', 'role', 'email_verified', 'created_at', 'updated_at')
        }),
    )

    def avatar_preview(self, obj):
        if obj.avatar:
            return mark_safe(f'<img src="{obj.avatar.url}" height="80" style="border-radius:50%" />')
        return '—'
    avatar_preview.short_description = 'Аватар'


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'url')
    search_fields = ('name', 'user__email', 'user__username')
    list_select_related = ('user',)


@admin.register(ShopEmployee)
class ShopEmployeeAdmin(admin.ModelAdmin):
    list_display = ('user', 'shop', 'position', 'is_active')
    list_filter = ('is_active', 'shop')
    search_fields = ('user__email', 'user__username', 'position')
    list_select_related = ('user', 'shop')


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    filter_horizontal = ('shops',)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category')
    list_filter = ('category',)
    search_fields = ('name',)
    list_select_related = ('category',)


class ProductParameterInline(admin.TabularInline):
    model = ProductParameter
    extra = 0


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


@admin.register(ProductInfo)
class ProductInfoAdmin(admin.ModelAdmin):
    list_display = ('name', 'product', 'shop', 'price', 'price_rrc', 'quantity')
    list_filter = ('shop', 'product__category')
    search_fields = ('name', 'model', 'product__name', 'shop__name')
    list_select_related = ('product', 'shop')
    list_per_page = 50
    inlines = (ProductParameterInline, ProductImageInline)


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'product_info', 'image_preview', 'created_at')
    list_select_related = ('product_info',)
    readonly_fields = ('created_at', 'image_preview')

    def image_preview(self, obj):
        if obj.image:
            return mark_safe(f'<img src="{obj.image.url}" height="60" />')
        return '—'
    image_preview.short_description = 'Превью'


@admin.register(Parameter)
class ParameterAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(ProductParameter)
class ProductParameterAdmin(admin.ModelAdmin):
    list_display = ('product_info', 'parameter', 'value')
    list_filter = ('parameter',)
    search_fields = ('product_info__name', 'parameter__name', 'value')
    list_select_related = ('product_info', 'parameter')


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ('user', 'city', 'street', 'house', 'phone')
    search_fields = ('user__email', 'city', 'phone')
    list_select_related = ('user',)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('get_price',)
    fields = ('product', 'shop', 'quantity', 'get_price')

    def get_price(self, obj):
        return obj.get_price()
    get_price.short_description = 'Сумма'


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'colored_status', 'date', 'get_total_price')
    list_filter = ('status', 'date')
    search_fields = ('user__email', 'user__username')
    readonly_fields = ('date', 'get_total_price')
    list_select_related = ('user', 'contact')
    list_per_page = 25
    date_hierarchy = 'date'
    inlines = (OrderItemInline,)
    actions = ['mark_confirmed', 'mark_shipped', 'mark_cancelled']

    def colored_status(self, obj):
        colors = {
            'new': '#3498db',
            'confirmed': '#2ecc71',
            'shipped': '#f39c12',
            'delivered': '#27ae60',
            'cancelled': '#e74c3c',
        }
        color = colors.get(obj.status, '#95a5a6')
        return mark_safe(
            f'<span style="color:{color}; font-weight:bold;">'
            f'{obj.get_status_display()}</span>'
        )
    colored_status.short_description = 'Статус'

    def get_total_price(self, obj):
        return obj.get_total_price()
    get_total_price.short_description = 'Сумма заказа'

    @admin.action(description='Подтвердить выбранные заказы')
    def mark_confirmed(self, request, queryset):
        updated = queryset.update(status=Order.StatusChoices.CONFIRMED)
        self.message_user(request, f'{updated} заказов подтверждено.')

    @admin.action(description='Отметить как отправленные')
    def mark_shipped(self, request, queryset):
        updated = queryset.update(status=Order.StatusChoices.SHIPPED)
        self.message_user(request, f'{updated} заказов отправлено.')

    @admin.action(description='Отменить выбранные заказы')
    def mark_cancelled(self, request, queryset):
        updated = queryset.update(status=Order.StatusChoices.CANCELLED)
        self.message_user(request, f'{updated} заказов отменено.')


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'product', 'shop', 'quantity', 'get_price')
    list_filter = ('shop',)
    search_fields = ('order__id', 'product__name')
    list_select_related = ('order', 'product', 'shop')

    def get_price(self, obj):
        return obj.get_price()
    get_price.short_description = 'Стоимость'