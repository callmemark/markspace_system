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