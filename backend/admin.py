from django.contrib import admin
from backend.models import (
    CustomUser, UserRole, Shop, ShopEmployee,
    Category, Product, ProductInfo, ProductImage, Parameter,
    ProductParameter, Contact, Order, OrderItem
)

admin.site.register(CustomUser)
admin.site.register(UserRole)
admin.site.register(Shop)
admin.site.register(ShopEmployee)
admin.site.register(Category)
admin.site.register(Product)
admin.site.register(ProductInfo)
admin.site.register(ProductImage)
admin.site.register(Parameter)
admin.site.register(ProductParameter)
admin.site.register(Contact)
admin.site.register(Order)
admin.site.register(OrderItem)
