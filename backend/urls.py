from django.urls import path
from backend.views import PartnerUpdate, LoginView, RegisterView, VerifyEmailView, ProductListAPIView

urlpatterns = [
    path('partner/update/', PartnerUpdate.as_view(), name='partner-update'),
    path('login/', LoginView.as_view(), name='login'),
    path('register/', RegisterView.as_view(), name='register'),
    path('verify-email/', VerifyEmailView.as_view(), name='verify-email'),
    path('products/', ProductListAPIView.as_view(), name='product-list'),
]