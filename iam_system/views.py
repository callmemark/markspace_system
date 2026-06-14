from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from rest_framework import filters
from rest_framework.generics import ListAPIView
from django.db import models
from iam_system import serializers
from rest_framework.exceptions import ValidationError
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

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
    ChangePasswordSerializer,
    AppApiTokenListSerializer,
    AppApiTokenCreateSerializer,
    InvitationSerializer
)
from .models import (
    EmailMessage,
    Application,
    AppApiToken,
    Invitation,
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
    serializer_class = ApplicationSerializer
    permission_classes = (permissions.IsAuthenticated, IsDeveloperAccount)

    def get_queryset(self):
        org_ids = self.request.user.memberships.values_list('organization_id', flat=True)
        return Application.objects.filter(organization_id__in=org_ids)

    def perform_create(self, serializer):
        membership = self.request.user.memberships.filter(role__in=['owner', 'admin']).first()
        org = membership.organization if membership else None
        serializer.save(owner=self.request.user, organization=org)


class ApplicationRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ApplicationSerializer
    permission_classes = (permissions.IsAuthenticated, IsDeveloperAccount)

    def get_queryset(self):
        membership = get_org_membership(self.request.user)
        return Application.objects.filter(organization=membership.organization)

    def perform_update(self, serializer):
        # owner/admin can update, member can only update app details
        membership = require_role(self.request.user, 'owner', 'admin', 'member')
        # If member, restrict updateable fields? Not strictly needed if serializer has limited fields.
        serializer.save()

    def perform_destroy(self, instance):
        require_role(self.request.user, 'owner', 'admin')
        instance.delete()

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
    serializer_class = MembershipSerializer
    permission_classes = (permissions.IsAuthenticated, IsDeveloperAccount)

    def get_queryset(self):
        membership = require_role(self.request.user, 'owner', 'admin')
        return membership.organization.memberships.all()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['organization'] = get_org_membership(self.request.user).organization
        context['request_user_role'] = get_org_membership(self.request.user).role
        return context

    def perform_update(self, serializer):
        require_role(self.request.user, 'owner', 'admin')
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        membership = require_role(request.user, 'owner', 'admin')

        # Owner cannot be removed
        if instance.role == 'owner':
            raise PermissionDenied("Cannot remove the organisation owner.")
        # Admin can only remove members
        if membership.role == 'admin' and instance.role in ('admin', 'owner'):
            raise PermissionDenied("You do not have permission to remove this member.")

        account = instance.account
        instance.delete()  # Remove the membership

        # If the user no longer belongs to any org, revert to personal
        if not Membership.objects.filter(account=account).exists():
            account.account_type = 'personal'
            account.save()
            try:
                send_mail(
                    subject="Your team access has been removed",
                    message=(
                        "Hello,\n\n"
                        "Your membership in a Tangerine organization has been removed. "
                        "Your account is now a personal account."
                    ),
                    from_email=None,
                    recipient_list=[account.email],
                    fail_silently=True,
                )
            except Exception:
                pass  # Notify via logs in production

        return Response(status=status.HTTP_204_NO_CONTENT)

# ----------------------------------------------------------------------
# DEVELOPER – API Tokens (per application)
# ----------------------------------------------------------------------
class AppApiTokenListCreateView(generics.ListCreateAPIView):
    permission_classes = (permissions.IsAuthenticated, IsDeveloperAccount)

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return AppApiTokenCreateSerializer
        return AppApiTokenListSerializer

    def get_queryset(self):
        membership = get_org_membership(self.request.user)
        return AppApiToken.objects.filter(application__organization=membership.organization)

    def perform_create(self, serializer):
        membership = require_role(self.request.user, 'owner', 'admin', 'member')
        application_id = self.request.data.get('application')
        if application_id:
            application = get_object_or_404(
                Application, pk=application_id, organization=membership.organization
            )
            serializer.save(application=application)
        else:
            raise serializers.ValidationError({'application': 'This field is required.'})


    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        # Return full token ONLY in the creation response
        response_data = AppApiTokenCreateSerializer(instance).data
        return Response(response_data, status=status.HTTP_201_CREATED)


class AppApiTokenRevokeView(generics.DestroyAPIView):
    serializer_class = AppApiTokenListSerializer
    permission_classes = (permissions.IsAuthenticated, IsDeveloperAccount)

    def get_queryset(self):
        membership = get_org_membership(self.request.user)
        return AppApiToken.objects.filter(application__organization=membership.organization)

    def perform_destroy(self, instance):
        require_role(self.request.user, 'owner', 'admin', 'member')
        instance.delete()




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




class DevTeamMemberListCreateView(generics.ListCreateAPIView):
    serializer_class = MembershipSerializer
    permission_classes = (permissions.IsAuthenticated, IsDeveloperAccount)

    def get_queryset(self):
        org = self._get_developer_org()
        return org.memberships.all()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['organization'] = self._get_developer_org()
        return context

    def _get_developer_org(self):
        membership = self.request.user.memberships.filter(role='owner').first()
        if not membership:
            raise ValidationError("Developer organization not found.")
        return membership.organization

class DevTeamMemberUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = MembershipSerializer
    permission_classes = (permissions.IsAuthenticated, IsDeveloperAccount)

    def get_queryset(self):
        org = self._get_developer_org()
        return org.memberships.all()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['organization'] = self._get_developer_org()
        return context

    def _get_developer_org(self):
        org = self.request.user.memberships.filter(role='owner').first()
        if not org:
            raise ValidationError("Developer organization not found.")
        return org.organization


class SendInvitationView(generics.CreateAPIView):
    """
    POST /api/dev/invitations/
    Body: { "email": "...", "role": "developer" }
    The developer's organization is determined automatically.
    """
    serializer_class = InvitationSerializer
    permission_classes = (permissions.IsAuthenticated, IsDeveloperAccount)

    def perform_create(self, serializer):
        dev_membership = self.request.user.memberships.filter(role='owner').first()
        if not dev_membership:
            raise ValidationError("You don't have a developer organization.")
        org = dev_membership.organization
        email = self.request.data.get('email')
        if Invitation.objects.filter(organization=org, invitee_email=email, status='pending').exists():
            raise serializers.ValidationError({"email": "An invitation has already been sent to this email."})

        invitation = serializer.save(organization=org, inviter=self.request.user)

        # ---- Send external email (dev fallback) ----
        invite_link = f"{self.request.scheme}://{self.request.get_host()}/invitation?token={invitation.token}"
        try:
            from django.core.mail import send_mail
            send_mail(
                f"You're invited to join {org.legal_name} on Tangerine",
                f"Click the link to accept or decline: {invite_link}",
                None,
                [email],
                html_message=f"<p>You're invited to join <strong>{org.legal_name}</strong> as a <strong>{invitation.role}</strong>.</p><p><a href='{invite_link}'>Accept or Decline</a></p>"
            )
        except Exception:
            #logger = logging.getLogger(__name__)
            #logger.info(f"External email could not be sent. Invitation link: {invite_link}")
            print("External email could not be sent. Invitation link: {invite_link}")

        # ---- Send internal Tangerine email to invitee's inbox ----
        try:
            invitee = User.objects.get(email=email)
            internal_body = (
                f"Hello {invitee.display_name},\n\n"
                f"You have been invited to join {org.legal_name} as a {invitation.role}.\n\n"
                f"Accept or Decline using the link below:\n{invite_link}\n\n"
                f"Best regards,\nTangerine System"
            )
            internal_message = EmailMessage.objects.create(
                sender=self.request.user,
                subject=f"Invitation to join {org.legal_name}",
                body=internal_body,
                invitation=invitation
            )
            internal_message.recipients.add(invitee)
        except User.DoesNotExist:
            # The invited email is not yet a Tangerine account – skip internal email
            pass


class InvitationDetailView(generics.RetrieveAPIView):
    """
    GET /api/invitations/<token>/ – get invitation details (public, but filtered by token)
    """
    serializer_class = InvitationSerializer
    lookup_field = 'token'
    queryset = Invitation.objects.filter(status='pending')


class AcceptInvitationView(generics.GenericAPIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, token):
        invitation = get_object_or_404(Invitation, token=token, status='pending')
        user = request.user

        if user.email != invitation.invitee_email:
            return Response({"detail": "Not the intended recipient."}, status=403)
        if user.account_type != 'personal':
            return Response({"detail": "Only personal accounts can join."}, status=400)
        if Membership.objects.filter(account=user).exists():
            return Response({"detail": "Already a member of an organization."}, status=400)

        Membership.objects.create(
            organization=invitation.organization,
            account=user,
            role=invitation.role
        )

        # Upgrade to developer
        user.account_type = 'developer'
        user.save()

        invitation.status = 'accepted'
        invitation.accepted_at = timezone.now()
        invitation.save()

        return Response({"detail": "Invitation accepted. You are now a developer."})


class DeclineInvitationView(generics.GenericAPIView):
    """
    POST /api/invitations/<token>/decline/ – decline (must be logged in, email match)
    """
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, token):
        invitation = get_object_or_404(Invitation, token=token, status='pending')
        if request.user.email != invitation.invitee_email:
            return Response({"detail": "You are not the intended recipient of this invitation."},
                            status=status.HTTP_403_FORBIDDEN)
        invitation.status = 'declined'
        invitation.save()
        return Response({"detail": "Invitation declined."})


class DevInvitationListView(generics.ListAPIView):
    serializer_class = InvitationSerializer
    permission_classes = (permissions.IsAuthenticated, IsDeveloperAccount)

    def get_queryset(self):
        membership = self.request.user.memberships.filter(role='owner').first()
        if not membership:
            return Invitation.objects.none()
        return Invitation.objects.filter(organization=membership.organization, status='pending')


class InvitationDeleteView(generics.DestroyAPIView):
    permission_classes = (permissions.IsAuthenticated, IsDeveloperAccount)
    queryset = Invitation.objects.all()




def get_org_membership(user):
    """Return the user’s Membership object, or raise PermissionDenied."""
    membership = user.memberships.first()
    if not membership:
        raise PermissionDenied("You are not part of an organisation.")
    return membership


def require_role(user, *roles):
    """Check that the user’s membership role is one of the allowed roles."""
    membership = get_org_membership(user)
    if membership.role not in roles:
        raise PermissionDenied("You do not have the required role.")
    return membership


class ApplicationListCreateView(generics.ListCreateAPIView):
    serializer_class = ApplicationSerializer
    permission_classes = (permissions.IsAuthenticated, IsDeveloperAccount)

    def get_queryset(self):
        membership = get_org_membership(self.request.user)
        return Application.objects.filter(organization=membership.organization)

    def perform_create(self, serializer):
        membership = require_role(self.request.user, 'owner', 'admin')
        serializer.save(owner=self.request.user, organization=membership.organization)


class DevTeamMemberListCreateView(generics.ListCreateAPIView):
    serializer_class = MembershipSerializer
    permission_classes = (permissions.IsAuthenticated, IsDeveloperAccount)

    def get_queryset(self):
        membership = require_role(self.request.user, 'owner', 'admin')
        return membership.organization.memberships.all()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        membership = get_org_membership(self.request.user)
        context['organization'] = membership.organization
        context['request_user_role'] = membership.role  # for validation
        return context

    def perform_create(self, serializer):
        membership = require_role(self.request.user, 'owner', 'admin')
        # The serializer will validate role based on request_user_role
        serializer.save(organization=membership.organization)



class DevTeamMemberUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = MembershipSerializer
    permission_classes = (permissions.IsAuthenticated, IsDeveloperAccount)

    def get_queryset(self):
        membership = require_role(self.request.user, 'owner', 'admin')
        return membership.organization.memberships.all()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['organization'] = get_org_membership(self.request.user).organization
        context['request_user_role'] = get_org_membership(self.request.user).role
        return context

    def perform_update(self, serializer):
        require_role(self.request.user, 'owner', 'admin')
        serializer.save()

    def perform_destroy(self, instance):
        membership = require_role(self.request.user, 'owner', 'admin')
        # Owner cannot be removed
        if instance.role == 'owner':
            raise PermissionDenied("Cannot remove the organisation owner.")
        if membership.role == 'admin' and instance.role in ('admin', 'owner'):
            raise PermissionDenied("You do not have permission to remove this member.")

        account = instance.account

        # If this is the account's only membership, revert to personal
        if account.memberships.count() == 1:
            account.account_type = 'personal'
            account.save()

            # Send internal Tangerine email notification
            try:
                email = EmailMessage.objects.create(
                    sender=self.request.user,
                    subject="Team access removed",
                    body=(
                        f"Hello {account.display_name},\n\n"
                        "Your team access has been removed. "
                        "Your account is now a personal Tangerine account.\n\n"
                        "Best regards,\nTangerine System"
                    ),
                )
                email.recipients.add(account)
            except Exception:
                pass  

        # Delete the membership
        instance.delete()