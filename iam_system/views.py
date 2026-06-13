from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from rest_framework import filters
from rest_framework.generics import ListAPIView
from django.db import models

from .serializers import (
    AccountRegistrationSerializer,
    AccountSerializer,
    AccountUpdateSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    EmailMessageSerializer,
    ApplicationSerializer,
    AppApiTokenSerializer,
    MembershipSerializer,
    ChangePasswordSerializer
)
from .models import (
    EmailMessage,
    Application,
    AppApiToken,
    Organization,
    Membership,
)

User = get_user_model()


# ----------------------------------------------------------------------
# Custom Permissions
# ----------------------------------------------------------------------
class IsDeveloperAccount(permissions.BasePermission):
    """Allow only users with account_type == 'developer'."""
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.account_type == 'developer'
        )


# ----------------------------------------------------------------------
# AUTHENTICATION (unchanged)
# ----------------------------------------------------------------------
class RegisterView(generics.CreateAPIView):
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
    permission_classes = (permissions.AllowAny,)


class TokenRefreshView(TokenRefreshView):
    pass


# ----------------------------------------------------------------------
# PASSWORD RESET (unchanged)
# ----------------------------------------------------------------------
class PasswordResetRequestView(generics.GenericAPIView):
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
# PROFILE (updated – now uses update serializer for PATCH/PUT)
# ----------------------------------------------------------------------
class UserProfileView(generics.RetrieveUpdateAPIView):
    """
    GET /api/auth/me/   – get own profile
    PATCH /api/auth/me/ – update display_name, company, website, etc.
    Requires valid JWT.
    """
    permission_classes = (permissions.IsAuthenticated,)

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        if self.request.method in ('PUT', 'PATCH'):
            return AccountUpdateSerializer
        return AccountSerializer


# ----------------------------------------------------------------------
# EMAIL SYSTEM
# ----------------------------------------------------------------------
class ComposeEmailView(generics.CreateAPIView):
    """
    POST /api/email/compose/
    Body: {
        "recipients": ["id1", "id2"],
        "cc": ["id3"],
        "subject": "...",
        "body": "...",
        "has_attachment": false
    }
    """
    serializer_class = EmailMessageSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def perform_create(self, serializer):
        serializer.save(sender=self.request.user)


class InboxListView(generics.ListAPIView):
    """
    GET /api/email/inbox/   – list received emails for the current user.
    Supports optional query params: ?unread=true, ?starred=true
    """
    serializer_class = EmailMessageSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        user = self.request.user
        queryset = user.received_emails.exclude(trashed_by=user)
        unread = self.request.query_params.get('unread')
        starred = self.request.query_params.get('starred')
        if unread is not None:
            queryset = queryset.exclude(read_by=user)
        if starred is not None:
            queryset = queryset.filter(starred_by=user)
        return queryset.order_by('-sent_at')


class EmailDetailView(generics.RetrieveAPIView):
    """
    GET /api/email/<pk>/   – get a single email (must be sender or recipient).
    """
    serializer_class = EmailMessageSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        user = self.request.user
        return EmailMessage.objects.filter(
            models.Q(sender=user) | models.Q(recipients=user)
        ).distinct()


class MarkReadView(generics.GenericAPIView):
    """
    POST /api/email/<pk>/read/   – mark as read (no body needed).
    """
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, pk):
        email = get_object_or_404(
            EmailMessage,
            pk=pk,
            recipients=request.user
        )
        email.read_by.add(request.user)
        return Response({"status": "marked read"})


class ToggleStarView(generics.GenericAPIView):
    """
    POST /api/email/<pk>/star/   – toggle star on/off.
    """
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, pk):
        email = get_object_or_404(
            EmailMessage,
            pk=pk,
            recipients=request.user
        )
        if request.user in email.starred_by.all():
            email.starred_by.remove(request.user)
            starred = False
        else:
            email.starred_by.add(request.user)
            starred = True
        return Response({"starred": starred})


# ----------------------------------------------------------------------
# DEVELOPER – Applications
# ----------------------------------------------------------------------
class ApplicationListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/dev/apps/          – list developer's applications
    POST /api/dev/apps/          – create new application
    """
    serializer_class = ApplicationSerializer
    permission_classes = (permissions.IsAuthenticated, IsDeveloperAccount)

    def get_queryset(self):
        return self.request.user.applications.all()

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class ApplicationRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/dev/apps/<pk>/
    PATCH  /api/dev/apps/<pk>/
    DELETE /api/dev/apps/<pk>/
    """
    serializer_class = ApplicationSerializer
    permission_classes = (permissions.IsAuthenticated, IsDeveloperAccount)

    def get_queryset(self):
        return self.request.user.applications.all()


# ----------------------------------------------------------------------
# DEVELOPER – Team Members (via Organization)
# ----------------------------------------------------------------------
class DevTeamMemberListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/dev/team/          – list members of developer's org
    POST /api/dev/team/          – invite new member (email, role)
    """
    serializer_class = MembershipSerializer
    permission_classes = (permissions.IsAuthenticated, IsDeveloperAccount)

    def get_queryset(self):
        # Get the developer's organization (auto‑created on sign‑up, or first one)
        org = self.request.user.memberships.filter(role='owner').first().organization
        return org.memberships.all()

    def perform_create(self, serializer):
        # The serializer should accept 'email' and 'role', then find/create the account
        org = self.request.user.memberships.filter(role='owner').first().organization
        email = self.request.data.get('email')
        role = self.request.data.get('role', 'member')
        # In a real scenario, you'd handle invitation properly.
        # For simplicity, we require the account to already exist.
        user = get_object_or_404(User, email=email)
        serializer.save(organization=org, account=user, role=role)


class DevTeamMemberUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/dev/team/<pk>/    – retrieve membership
    PATCH  /api/dev/team/<pk>/    – update role
    DELETE /api/dev/team/<pk>/    – remove member
    """
    serializer_class = MembershipSerializer
    permission_classes = (permissions.IsAuthenticated, IsDeveloperAccount)

    def get_queryset(self):
        org = self.request.user.memberships.filter(role='owner').first().organization
        return org.memberships.all()


# ----------------------------------------------------------------------
# DEVELOPER – API Tokens (per application)
# ----------------------------------------------------------------------
class AppApiTokenListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/dev/tokens/         – list tokens for all apps of this developer
    POST /api/dev/tokens/         – generate new token (body: application, name, permissions)
    """
    serializer_class = AppApiTokenSerializer
    permission_classes = (permissions.IsAuthenticated, IsDeveloperAccount)

    def get_queryset(self):
        # Return tokens for all apps owned by the developer
        return AppApiToken.objects.filter(
            application__owner=self.request.user
        )

    def perform_create(self, serializer):
        # Ensure the application belongs to the current developer
        application_id = self.request.data.get('application')
        if application_id:
            application = get_object_or_404(
                Application, pk=application_id, owner=self.request.user
            )
            serializer.save(application=application)
        else:
            # let the serializer handle validation, but prevent cross‑owner
            serializer.save()


class AppApiTokenRevokeView(generics.DestroyAPIView):
    """
    DELETE /api/dev/tokens/<pk>/   – revoke (delete) a token.
    """
    serializer_class = AppApiTokenSerializer
    permission_classes = (permissions.IsAuthenticated, IsDeveloperAccount)

    def get_queryset(self):
        return AppApiToken.objects.filter(
            application__owner=self.request.user
        )




class UserSearchView(ListAPIView):
    """
    GET /api/users/?search=alice   – returns list of {id, email, display_name}
    """
    serializer_class = AccountSerializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [filters.SearchFilter]
    search_fields = ['email', 'display_name']
    queryset = User.objects.all()


class SentListView(generics.ListAPIView):
    """
    GET /api/email/sent/ – list emails sent by the current user.
    """
    serializer_class = EmailMessageSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        user = self.request.user
        return user.sent_emails.exclude(trashed_by=user).order_by('-sent_at')
    

class TrashEmailView(generics.GenericAPIView):
    """
    POST /api/email/<pk>/trash/
    Moves the email to trash for the current user (works for sender or recipient).
    """
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, pk):
        email = get_object_or_404(
            EmailMessage,
            models.Q(sender=request.user) | models.Q(recipients=request.user),
            pk=pk
        )
        email.trashed_by.add(request.user)
        return Response({"status": "trashed"})



class ChangePasswordView(generics.GenericAPIView):
    serializer_class = ChangePasswordSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data['old_password']):
            return Response({"old_password": "Current password is incorrect."},
                            status=status.HTTP_400_BAD_REQUEST)
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        return Response({"detail": "Password updated successfully."})



class DeleteAccountView(generics.DestroyAPIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get_object(self):
        return self.request.user

    def perform_destroy(self, instance):
        instance.delete()