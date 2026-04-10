from django.urls import path
from backend.views import (
    PartnerUpdate, LoginView, RegisterView, VerifyEmailView, ProductListAPIView,
    CartAPIView, AddToCartAPIView, UpdateCartItemAPIView, RemoveFromCartAPIView
)

urlpatterns = [
    path('partner/update/', PartnerUpdate.as_view(), name='partner-update'),
    path('login/', LoginView.as_view(), name='login'),
    path('register/', RegisterView.as_view(), name='register'),
    path('verify-email/', VerifyEmailView.as_view(), name='verify-email'),
    path('products/', ProductListAPIView.as_view(), name='product-list'),
    path('cart/', CartAPIView.as_view(), name='cart'),
    path('cart/add/', AddToCartAPIView.as_view(), name='add-to-cart'),
    path('cart/update/<int:item_id>/', UpdateCartItemAPIView.as_view(), name='update-cart-item'),
    path('cart/remove/<int:item_id>/', RemoveFromCartAPIView.as_view(), name='remove-from-cart'),
]
