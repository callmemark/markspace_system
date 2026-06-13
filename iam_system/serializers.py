from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode

from .models import Application, AppApiToken, Membership, EmailMessage

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
    class Meta:
        model = User
        fields = (
            'display_name',
            'company',
            'job_title',
            'website',
            'description',
            'avatar',
        )
        # All fields are optional – only provided fields will be updated
        extra_kwargs = {field: {'required': False} for field in fields}

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
    sender_email = serializers.EmailField(source='sender.email', read_only=True)   # ← new field

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
            'reply_to', 'reply_to_id',
        )
        read_only_fields = (
            'sender', 'sender_email', 'sent_at',    # ← added sender_email
            'is_read', 'is_starred',
            'recipients_detail', 'cc_detail',
            'reply_to_id',
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


class AppApiTokenSerializer(serializers.ModelSerializer):
    application_name = serializers.ReadOnlyField(source='application.name')

    class Meta:
        model = AppApiToken
        fields = ('id', 'name', 'token', 'permissions', 'is_active',
                  'expires_at', 'last_used_at', 'created_at', 'application', 'application_name')
        read_only_fields = ('token', 'last_used_at', 'created_at')
        extra_kwargs = {
            'application': {'required': True},
        }


class MembershipSerializer(serializers.ModelSerializer):
    account_email = serializers.ReadOnlyField(source='account.email')
    account_name = serializers.ReadOnlyField(source='account.display_name')
    role = serializers.ChoiceField(choices=Membership.Role.choices)

    class Meta:
        model = Membership
        fields = ('id', 'account_email', 'account_name', 'role', 'joined_at')
        read_only_fields = ('joined_at',)





class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    new_password2 = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password2']:
            raise serializers.ValidationError({"new_password": "Passwords don't match."})
        return attrs