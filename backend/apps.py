from django.apps import AppConfig


class BackendConfig(AppConfig):
    name = 'backend'

    def ready(self):
        from django.db.models.signals import post_migrate
        post_migrate.connect(_ensure_roles_exist, sender=self)


def _ensure_roles_exist(sender, **kwargs):
    """Гарантирует наличие всех системных ролей после каждой миграции."""
    try:
        from backend.models import UserRole
        roles = [
            ('admin',         'Полный доступ к системе'),
            ('shop',          'Владелец магазина, управление товарами и прайсами'),
            ('shop_employee', 'Сотрудник магазина с ограниченным доступом'),
            ('buyer',         'Покупатель, оформление и просмотр заказов'),
        ]
        for name, description in roles:
            UserRole.objects.get_or_create(name=name, defaults={'description': description})
    except Exception:
        pass
