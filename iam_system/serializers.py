from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode

from .models import Application, AppApiToken, Membership, EmailMessage, Organization, Invitation

User = get_user_model()


# ----------------------------------------------------------------------
# REGISTRATION – supports account_type + extra fields
# ----------------------------------------------------------------------
class AccountRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True, required=True, validators=[validate_password]
    )
    password2 = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = (
            'id',
            'email',
            'display_name',
            'account_type',          # new: personal / professional / developer
            'company',               # professional
            'job_title',             # professional
            'website',               # developer
            'description',           # developer
            'password',
            'password2',
        )
        extra_kwargs = {
            'company': {'required': False},
            'job_title': {'required': False},
            'website': {'required': False},
            'description': {'required': False},
            'account_type': {'default': 'personal'},
        }

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        return attrs


    def create(self, validated_data):
        validated_data.pop('password2')
        # Extract non-account fields that are passed to create_user
        extra_fields = {}
        for field in ['company', 'job_title', 'website', 'description', 'account_type']:
            if field in validated_data:
                extra_fields[field] = validated_data.pop(field)

        user = User.objects.create_user(**validated_data, **extra_fields)

        # If developer, create a default Organization and make the user owner
        if extra_fields.get('account_type') == 'developer':
            # Generate a unique slug from email or display name
            base_slug = user.email.split('@')[0].lower()
            slug = base_slug
            counter = 1
            while Organization.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            org = Organization.objects.create(
                legal_name=f"{user.display_name}'s Workspace",
                slug=slug,
                plan='free'
            )
            Membership.objects.create(
                organization=org,
                account=user,
                role=Membership.Role.OWNER
            )

        return user


# ----------------------------------------------------------------------
# ACCOUNT DETAIL (read‑only view of the logged‑in user)
# ----------------------------------------------------------------------
class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            'id',
            'email',
            'display_name',
            'account_type',
            'company',
            'job_title',
            'website',
            'description',
            'avatar',
            'is_active',
            'date_joined',
        )
        read_only_fields = ('id', 'email', 'account_type', 'date_joined', 'is_active')


# ----------------------------------------------------------------------
# ACCOUNT UPDATE (for the Account Settings page)
# ----------------------------------------------------------------------
class AccountUpdateSerializer(serializers.ModelSerializer):
    membership_role = serializers.SerializerMethodField()

    def get_membership_role(self, obj):
        # A user can only belong to one organisation
        membership = obj.memberships.first()
        return membership.role if membership else None
    
    class Meta:
        model = User
        fields = (
            'id', 'email', 'display_name', 'account_type',
            'company', 'job_title', 'website', 'description', 'avatar',
            'is_active', 'date_joined', 'membership_role'
        )
        read_only_fields = ('id', 'email', 'account_type', 'date_joined', 'is_active', 'membership_role')

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


# ----------------------------------------------------------------------
# PASSWORD RESET (unchanged, but using User model)
# ----------------------------------------------------------------------
class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        try:
            user = User.objects.get(email=value, is_active=True)
        except User.DoesNotExist:
            return value
        self.user = user
        return value

    def save(self):
        request = self.context.get('request')
        user = self.user
        token_generator = PasswordResetTokenGenerator()
        token = token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))

        reset_url = f"{request.scheme}://{request.get_host()}/reset-password/{uid}/{token}/"

        user.email_user(
            subject="Password Reset Request",
            message=f"Click the link to reset your password: {reset_url}",
            html_message=f"<p>Click <a href='{reset_url}'>here</a> to reset your password.</p>",
        )
        return user


class PasswordResetConfirmSerializer(serializers.Serializer):
    uidb64 = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    new_password2 = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password2']:
            raise serializers.ValidationError({"new_password": "Passwords don't match."})

        try:
            uid = urlsafe_base64_decode(attrs['uidb64']).decode()
            self.user = User.objects.get(pk=uid)
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            raise serializers.ValidationError({"uidb64": "Invalid reset link."})

        token_generator = PasswordResetTokenGenerator()
        if not token_generator.check_token(self.user, attrs['token']):
            raise serializers.ValidationError({"token": "Invalid or expired token."})

        return attrs

    def save(self):
        self.user.set_password(self.validated_data['new_password'])
        self.user.save()
        return self.user



# serializers.py – updated EmailMessageSerializer
class EmailMessageSerializer(serializers.ModelSerializer):
    sender = serializers.StringRelatedField(read_only=True)
    sender_email = serializers.EmailField(source='sender.email', read_only=True)  

    invitation_id = serializers.ReadOnlyField(source='invitation.id', allow_null=True)
    invitation_token = serializers.ReadOnlyField(source='invitation.token', allow_null=True)
    invitation_status = serializers.ReadOnlyField(source='invitation.status', allow_null=True)

    recipients = serializers.ListField(
        child=serializers.EmailField(), write_only=True, required=True
    )
    cc = serializers.ListField(
        child=serializers.EmailField(), write_only=True, required=False, default=[]
    )
    recipients_detail = AccountSerializer(source='recipients', many=True, read_only=True)
    cc_detail = AccountSerializer(source='cc', many=True, read_only=True)
    is_read = serializers.SerializerMethodField()
    is_starred = serializers.SerializerMethodField()

    reply_to = serializers.PrimaryKeyRelatedField(
        queryset=EmailMessage.objects.all(),
        required=False,
        allow_null=True,
        write_only=True
    )
    reply_to_id = serializers.ReadOnlyField(source='reply_to.id')

    class Meta:
        model = EmailMessage
        fields = (
            'id', 'sender', 'sender_email',        # ← added sender_email
            'recipients', 'cc', 'subject', 'body',
            'sent_at', 'has_attachment', 'is_read', 'is_starred',
            'recipients_detail', 'cc_detail',
            'reply_to', 'reply_to_id', 'invitation_id',
            'invitation_token',
            'invitation_status',
        )
        read_only_fields = (
            'sender', 'sender_email', 'sent_at',    # ← added sender_email
            'is_read', 'is_starred',
            'recipients_detail', 'cc_detail',
            'reply_to_id', 'invitation_id',
            'invitation_token',
            'invitation_status',
        )

    def get_is_read(self, obj):
        request = self.context.get('request')
        return request and request.user in obj.read_by.all()

    def get_is_starred(self, obj):
        request = self.context.get('request')
        return request and request.user in obj.starred_by.all()

    def create(self, validated_data):
        recipient_emails = validated_data.pop('recipients')
        cc_emails = validated_data.pop('cc', [])
        reply_to = validated_data.pop('reply_to', None)
        validated_data.pop('sender', None)  # safety

        sender = self.context['request'].user
        email = EmailMessage.objects.create(
            sender=sender,
            reply_to=reply_to,
            **validated_data
        )

        recipients = User.objects.filter(email__in=recipient_emails)
        email.recipients.set(recipients)
        if cc_emails:
            cc_users = User.objects.filter(email__in=cc_emails)
            email.cc.set(cc_users)
        return email


class ApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Application
        fields = ('id', 'name', 'client_id', 'description', 'website', 'created_at')
        read_only_fields = ('id', 'client_id', 'created_at', 'owner')


class AppApiTokenListSerializer(serializers.ModelSerializer):
    """Used for GET (list) – never exposes the full token."""
    application_name = serializers.ReadOnlyField(source='application.name')
    token_preview = serializers.SerializerMethodField()

    class Meta:
        model = AppApiToken
        fields = (
            'id', 'name', 'token_preview', 'permissions', 'is_active',
            'expires_at', 'last_used_at', 'created_at',
            'application', 'application_name'
        )
        read_only_fields = ('last_used_at', 'created_at')

    def get_token_preview(self, obj):
        return f"••••{obj.token[-4:]}"


class AppApiTokenCreateSerializer(serializers.ModelSerializer):
    """Used for POST (create) – returns the full token once."""
    application_name = serializers.ReadOnlyField(source='application.name')

    class Meta:
        model = AppApiToken
        fields = (
            'id', 'name', 'token', 'permissions', 'is_active',
            'expires_at', 'last_used_at', 'created_at',
            'application', 'application_name'
        )
        read_only_fields = ('token', 'last_used_at', 'created_at')
        extra_kwargs = {
            'application': {'required': True},
        }


class AppApiTokenSerializer(serializers.ModelSerializer):
    token = serializers.CharField(read_only=True)
    token_preview = serializers.SerializerMethodField()

    def get_token_preview(self, obj):
        return f"••••{obj.token[-4:]}"

    class Meta:
        model = AppApiToken
        fields = ('id', 'name', 'token', 'token_preview', 'permissions', 'is_active',
                  'expires_at', 'last_used_at', 'created_at', 'application', 'application_name')
        read_only_fields = ('token', 'last_used_at', 'created_at')
        extra_kwargs = {
            'application': {'required': True},
        }


class AppApiTokenSerializer(serializers.ModelSerializer):
    token_preview = serializers.SerializerMethodField(read_only=True)

    def get_token_preview(self, obj):
        return f"••••{obj.token[-4:]}"

    class Meta:
        model = AppApiToken
        fields = ('id', 'name', 'token', 'token_preview', 'permissions', ...)
        extra_kwargs = {
            'token': {'write_only': True},   # full token only accepted on creation, never returned in responses
        }


class MembershipSerializer(serializers.ModelSerializer):
    account_email = serializers.ReadOnlyField(source='account.email')
    account_name = serializers.ReadOnlyField(source='account.display_name')
    role = serializers.ChoiceField(choices=Membership.Role.choices)

    # For inviting – accept email instead of account ID
    email = serializers.EmailField(write_only=True, required=False)

    class Meta:
        model = Membership
        fields = ('id', 'account_email', 'account_name', 'role', 'joined_at', 'email')
        read_only_fields = ('joined_at', 'account_email', 'account_name')

    def validate(self, attrs):
        if self.instance is None:  # creation
            email = attrs.get('email')
            if not email:
                raise serializers.ValidationError({"email": "This field is required."})
            try:
                account = User.objects.get(email=email)
            except User.DoesNotExist:
                raise serializers.ValidationError({"email": "No account found with this email."})
            # Check if already a member
            org = self.context['organization']
            if Membership.objects.filter(organization=org, account=account).exists():
                raise serializers.ValidationError({"email": "User is already a member of this organization."})
            self.context['account'] = account
        return attrs

    def validate_role(self, value):
        request = self.context.get('request')
        if not request:
            return value
        request_user_role = self.context.get('request_user_role')
        # When creating or updating, admin cannot assign admin role
        if request_user_role == 'admin' and value == 'admin':
            raise serializers.ValidationError("Only the owner can assign the admin role.")
        # Also prevent changing owner to anything else
        if self.instance and self.instance.role == 'owner' and value != 'owner':
            raise serializers.ValidationError("Cannot change the owner's role.")
        return value

    def create(self, validated_data):
        validated_data.pop('email', None)
        account = self.context['account']
        org = self.context['organization']
        return Membership.objects.create(organization=org, account=account, role=validated_data['role'])



class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    new_password2 = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password2']:
            raise serializers.ValidationError({"new_password": "Passwords don't match."})
        return attrs



# serializers.py
class InvitationSerializer(serializers.ModelSerializer):
    organization_name = serializers.ReadOnlyField(source='organization.legal_name')
    inviter_email = serializers.ReadOnlyField(source='inviter.email')
    # Accept 'email' from frontend, write to model's 'invitee_email'
    email = serializers.EmailField(write_only=True, source='invitee_email')

    class Meta:
        model = Invitation
        fields = (
            'id', 'organization', 'inviter', 'organization_name', 'inviter_email',
            'email', 'role', 'status', 'token', 'created_at'
        )
        read_only_fields = ('token', 'status', 'created_at', 'organization', 'inviter')

    def validate_invitee_email(self, value):
        try:
            user = User.objects.get(email=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("No account found with this email.")
        if user.account_type != 'personal':
            raise serializers.ValidationError("Only personal accounts can be invited.")
        return value


class InvitationAcceptSerializer(serializers.Serializer):
    token = serializers.UUIDField()