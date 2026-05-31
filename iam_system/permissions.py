# permissions.py
from rest_framework.permissions import BasePermission
from .models import Membership

class OrganizationPermission(BasePermission):
    def has_permission(self, request, view):
        org_id = request.headers.get('X-Organization')
        if not org_id:
            return False
        return Membership.objects.filter(
            organization_id=org_id,
            individual=request.user,
        ).exists()