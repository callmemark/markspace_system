
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView, TokenBlacklistView
from .views import RegisterView, LoginView, TokenRefreshView, UserProfileView, PasswordResetRequestView, PasswordResetConfirmView



urlpatterns = [
    # ------- Authentication Endpoints --------------------------------------------------------
    path('api/auth/register/', RegisterView.as_view(), name='auth-register'),
    path('api/auth/login/', LoginView.as_view(), name='auth-login'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('api/auth/me/', UserProfileView.as_view(), name='user-profile'),

    
    # ------- Password Reset Endpoints --------------------------------------------------------
    path('api/auth/password-reset/', PasswordResetRequestView.as_view(), name='password-reset'),
    path('api/auth/password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
]