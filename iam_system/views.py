from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .serializers import AccountRegistrationSerializer, AccountSerializer, PasswordResetRequestSerializer, PasswordResetConfirmSerializer




# ----------------------------------------------------------------------
# AUTHENTICATIONS
# ----------------------------------------------------------------------
class RegisterView(generics.CreateAPIView):
    """
    POST /api/auth/register/
    Body: { "email": "...", "display_name": "...", "password": "...", "password2": "..." }
    Returns user data (without tokens – login afterwards to get tokens).
    """
    serializer_class = AccountRegistrationSerializer
    permission_classes = (permissions.AllowAny,)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            AccountSerializer(user).data,
            status=status.HTTP_201_CREATED
        )


class LoginView(TokenObtainPairView):
    """
    POST /api/auth/login/
    Body: { "email": "...", "password": "..." }
    Returns access & refresh tokens.
    """
    permission_classes = (permissions.AllowAny,)


class TokenRefreshView(TokenRefreshView):
    """
    POST /api/auth/token/refresh/
    Body: { "refresh": "..." }
    Returns new access token.
    """



# ----------------------------------------------------------------------
# PASSWORD RESET
# ----------------------------------------------------------------------
class PasswordResetRequestView(generics.GenericAPIView):
    """
    POST /api/auth/password-reset/
    Body: { "email": "user@example.com" }
    Sends a password reset link to the email.
    """
    serializer_class = PasswordResetRequestSerializer
    permission_classes = (permissions.AllowAny,)

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"detail": "Password reset link has been sent if the email exists."},
            status=status.HTTP_200_OK
        )


class PasswordResetConfirmView(generics.GenericAPIView):
    """
    POST /api/auth/password-reset/confirm/
    Body: { "uidb64": "...", "token": "...", "new_password": "...", "new_password2": "..." }
    Sets the new password.
    """
    serializer_class = PasswordResetConfirmSerializer
    permission_classes = (permissions.AllowAny,)

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"detail": "Password has been reset successfully."},
            status=status.HTTP_200_OK
        )
    



# ----------------------------------------------------------------------
# Profile Management Views
# ----------------------------------------------------------------------
class UserProfileView(generics.RetrieveUpdateAPIView):
    """
    GET /api/auth/me/   – get own profile
    PATCH /api/auth/me/ – update display_name (etc.)
    Requires valid JWT.
    """
    serializer_class = AccountSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_object(self):
        return self.request.user