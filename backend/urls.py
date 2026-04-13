from django.urls import path
from backend.views import (
    PartnerUpdate, LoginView, RegisterView, VerifyEmailView, ProductListAPIView,
    CartAPIView, AddToCartAPIView, UpdateCartItemAPIView, RemoveFromCartAPIView,
    ContactAPIView, ContactDetailView, ConfirmOrderAPIView, OrderListAPIView, OrderDetailView
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
    path('contact/', ContactAPIView.as_view(), name='contact'),
    path('contact/<int:contact_id>/', ContactDetailView.as_view(), name='contact-detail'),
    path('order/confirm/', ConfirmOrderAPIView.as_view(), name='confirm-order'),
    path('orders/', OrderListAPIView.as_view(), name='order-list'),
    path('orders/<int:order_id>/', OrderDetailView.as_view(), name='order-detail'),
]
