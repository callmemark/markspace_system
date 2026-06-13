from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView as SimpleJWTTokenRefreshView, TokenBlacklistView
from .views import (
    RegisterView,
    LoginView,
    UserProfileView,
    PasswordResetRequestView,
    PasswordResetConfirmView,
    ComposeEmailView,
    InboxListView,
    EmailDetailView,
    MarkReadView,
    ToggleStarView,
    ApplicationListCreateView,
    ApplicationRetrieveUpdateDestroyView,
    DevTeamMemberListCreateView,
    DevTeamMemberUpdateDestroyView,
    AppApiTokenListCreateView,
    AppApiTokenRevokeView,
    UserSearchView,
    SentListView,
    TrashEmailView,
    ChangePasswordView,
    DeleteAccountView
)

urlpatterns = [
    # -------------------- Authentication --------------------
    path('api/auth/register/', RegisterView.as_view(), name='auth-register'),
    path('api/auth/login/', LoginView.as_view(), name='auth-login'),
    path('api/auth/token/refresh/', SimpleJWTTokenRefreshView.as_view(), name='token-refresh'),
    path('api/auth/me/', UserProfileView.as_view(), name='user-profile'),

    # -------------------- Password Reset --------------------
    path('api/auth/password-reset/', PasswordResetRequestView.as_view(), name='password-reset'),
    path('api/auth/password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),

    # -------------------- Email System --------------------
    path('api/email/compose/', ComposeEmailView.as_view(), name='email-compose'),
    path('api/email/inbox/', InboxListView.as_view(), name='email-inbox'),
    path('api/email/<uuid:pk>/', EmailDetailView.as_view(), name='email-detail'),
    path('api/email/<uuid:pk>/read/', MarkReadView.as_view(), name='email-read'),
    path('api/email/<uuid:pk>/star/', ToggleStarView.as_view(), name='email-star'),
    path('api/users/', UserSearchView.as_view(), name='user-search'),
    path('api/email/sent/', SentListView.as_view(), name='email-sent'),
    path('api/email/<uuid:pk>/trash/', TrashEmailView.as_view(), name='email-trash'),
    

    path('api/auth/change-password/', ChangePasswordView.as_view(), name='change-password'),
    path('api/auth/me/delete/', DeleteAccountView.as_view(), name='delete-account'),

    # -------------------- Developer – Applications --------------------
    path('api/dev/apps/', ApplicationListCreateView.as_view(), name='app-list-create'),
    path('api/dev/apps/<uuid:pk>/', ApplicationRetrieveUpdateDestroyView.as_view(), name='app-detail'),

    # -------------------- Developer – Team Members --------------------
    path('api/dev/team/', DevTeamMemberListCreateView.as_view(), name='team-list-create'),
    path('api/dev/team/<uuid:pk>/', DevTeamMemberUpdateDestroyView.as_view(), name='team-detail'),

    # -------------------- Developer – API Tokens --------------------
    path('api/dev/tokens/', AppApiTokenListCreateView.as_view(), name='token-list-create'),
    path('api/dev/tokens/<uuid:pk>/', AppApiTokenRevokeView.as_view(), name='token-revoke'),
]