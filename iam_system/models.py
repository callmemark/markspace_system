from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
import uuid

class AccountManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


class Account(AbstractBaseUser, PermissionsMixin):
    """
    Represents an individual user. No longer mixed with Organizations.
    """

    ACCOUNT_TYPES = [
        ('personal', 'Personal'),
        ('professional', 'Professional'),
        ('developer', 'Developer'),
    ]
    account_type = models.CharField(
        max_length=20, choices=ACCOUNT_TYPES, default='personal', db_index=True
    )

    # Professional extras
    company = models.CharField(max_length=255, blank=True, null=True)
    job_title = models.CharField(max_length=255, blank=True, null=True)

    # Developer extras (used during sign‑up and editable in settings)
    website = models.URLField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)

    # Optional avatar
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    display_name = models.CharField(max_length=255)
    
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        related_name='iam_account_set',
        related_query_name='iam_account',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        related_name='iam_account_set',
        related_query_name='iam_account',
    )

    objects = AccountManager()
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['display_name']

    class Meta:
        db_table = 'iam_account'
        verbose_name = 'account'
        verbose_name_plural = 'accounts'

    def __str__(self):
        return f"{self.display_name} ({self.email})"


class Organization(models.Model):
    """
    Represents a tenant/workspace. Completely decoupled from Account.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    legal_name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, db_index=True)
    plan = models.CharField(max_length=50, default='free', db_index=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'iam_organization'

    def __str__(self):
        return self.legal_name


class Membership(models.Model):
    class Role(models.TextChoices):
        OWNER = 'owner', 'Owner'
        ADMIN = 'admin', 'Admin'
        MEMBER = 'member', 'Member'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='memberships')
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='memberships')
    
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER, db_index=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'iam_membership'
        unique_together = [['organization', 'account']]

    def __str__(self):
        # Avoid traversing foreign keys in __str__ to prevent N+1 queries.
        return f"Membership {self.id} - Role: {self.role}"


# -------------------------------------------------------------------------
# RBAC Models
# -------------------------------------------------------------------------

class Permission(models.Model):
    codename = models.CharField(max_length=100, unique=True, db_index=True)
    description = models.TextField(blank=True)

    class Meta:
        db_table = 'iam_permission'

    def __str__(self):
        return self.codename


class Role(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, null=True, blank=True, related_name='custom_roles'
    )
    permissions = models.ManyToManyField(Permission, related_name='roles')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'iam_role'
        unique_together = [['name', 'organization']]
        indexes = [
            models.Index(fields=['organization', 'name']),
        ]

    def __str__(self):
        return self.name


# -------------------------------------------------------------------------
# API Keys 
# -------------------------------------------------------------------------

class ApiKey(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    prefix = models.CharField(max_length=20, db_index=True) 
    key_hash = models.CharField(max_length=255) 
    
    account = models.ForeignKey(Account, on_delete=models.CASCADE, null=True, blank=True, related_name='api_keys')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True, related_name='api_keys')
    
    scopes = models.TextField(default='read')
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True) # Indexed for cleanup jobs
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'iam_api_key'
        constraints = [
            models.CheckConstraint(
                check=~(models.Q(account__isnull=True) & models.Q(organization__isnull=True)),
                name='api_key_owner_not_both_null',
                violation_error_message="An API Key must be associated with either an account or an organization."
            )
        ]

    def __str__(self):
        return f"Key {self.prefix}..."



class EmailMessage(models.Model):
    reply_to = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='replies'
    )

    trashed_by = models.ManyToManyField(
        'Account',
        related_name='trashed_emails',
        blank=True
    )

    invitation = models.ForeignKey(
        'Invitation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='email_messages'
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sender = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name='sent_emails'
    )
    recipients = models.ManyToManyField(
        Account, related_name='received_emails'
    )
    cc = models.ManyToManyField(
        Account, related_name='cc_emails', blank=True
    )
    subject = models.CharField(max_length=255)
    body = models.TextField()
    sent_at = models.DateTimeField(default=timezone.now)
    has_attachment = models.BooleanField(default=False)

    # Per‑recipient state
    read_by = models.ManyToManyField(
        Account, related_name='read_emails', blank=True
    )
    starred_by = models.ManyToManyField(
        Account, related_name='starred_emails', blank=True
    )

    class Meta:
        db_table = 'iam_email_message'
        ordering = ['-sent_at']



def generate_client_id():
    return uuid.uuid4().hex[:16]

class Application(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name='applications'
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='applications'
    )
    
    name = models.CharField(max_length=255)
    # Only one client_id field — no lambda
    client_id = models.CharField(
        max_length=32,
        unique=True,
        default=generate_client_id,
        db_index=True
    )
    description = models.TextField(blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'iam_application'


def generate_token():
    return uuid.uuid4().hex

class AppApiToken(models.Model):
    PERMISSION_CHOICES = [
        ('read', 'Read'),
        ('write', 'Write'),
        ('admin', 'Admin'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        Application, on_delete=models.CASCADE, related_name='api_tokens'
    )
    name = models.CharField(max_length=255)
    token = models.CharField(
        max_length=64,
        unique=True,
        default=generate_token
    ) # Show once, store as‑is (or hash it)
    permissions = models.CharField(
        max_length=20, choices=PERMISSION_CHOICES, default='read'
    )
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    last_used_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'iam_app_api_token'


class Invitation(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='invitations')
    inviter = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='sent_invitations')
    invitee_email = models.EmailField(db_index=True)
    token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    role = models.CharField(max_length=20, choices=Membership.Role.choices, default=Membership.Role.MEMBER)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'iam_invitation'



class AuthRecord(models.Model):
    user = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name='auth_records'
    )
    application = models.ForeignKey(
        Application, on_delete=models.CASCADE, related_name='auth_records'
    )
    
    first_login = models.DateTimeField(auto_now_add=True)               
    last_login = models.DateTimeField(null=True, blank=True)
    login_count = models.PositiveIntegerField(default=1)                
    last_change_password = models.DateTimeField(null=True, blank=True)
    last_ip = models.GenericIPAddressField(null=True, blank=True)
    last_user_agent = models.CharField(max_length=255, blank=True, null=True)
    last_token_refresh = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'iam_auth_record'
        unique_together = ('user', 'application')
        indexes = [
            models.Index(fields=['application', 'last_login']),
            models.Index(fields=['application', 'is_active']),
        ]