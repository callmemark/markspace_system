from .models import AuthRecord, Account, Application


def update_auth_activity_record(user: Account, application: Application, **fields):
    """
    Create or update an AuthRecord for the given user + application.

    Accepted keyword arguments:
        last_login          - datetime (usually now)
        last_ip             - str
        last_user_agent     - str
        last_token_refresh  - datetime
        last_change_password- datetime
        is_active           - bool

    Automatically handles:
        - first_login (set once on creation)
        - login_count incremented when last_login is provided
        - updated_at (auto field)
    """
    record, created = AuthRecord.objects.get_or_create(
        user=user,
        application=application,
        defaults={
            'first_login': fields.get('last_login', timezone.now()),
            'login_count': 1,
            **{k: v for k, v in fields.items() if k in [
                'last_ip', 'last_user_agent', 'last_token_refresh',
                'last_change_password', 'is_active'
            ]}
        }
    )

    if not created:
        # Update only provided fields
        for field in ['last_ip', 'last_user_agent', 'last_token_refresh',
                      'last_change_password', 'is_active']:
            if field in fields:
                setattr(record, field, fields[field])

        if 'last_login' in fields:
            record.last_login = fields['last_login']
            record.login_count += 1

        record.save(update_fields=[f for f in fields.keys() if hasattr(record, f)] + ['login_count'])

    return record