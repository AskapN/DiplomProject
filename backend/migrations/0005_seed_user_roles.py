from django.db import migrations


ROLES = [
    ('admin',         'Администратор',         'Полный доступ к системе'),
    ('shop',          'Магазин',               'Владелец магазина, управление товарами и прайсами'),
    ('shop_employee', 'Сотрудник магазина',     'Сотрудник магазина с ограниченным доступом'),
    ('buyer',         'Покупатель',             'Покупатель, оформление и просмотр заказов'),
]


def seed_roles(apps, schema_editor):
    UserRole = apps.get_model('backend', 'UserRole')
    for name, _, description in ROLES:
        UserRole.objects.get_or_create(name=name, defaults={'description': description})


def remove_roles(apps, schema_editor):
    UserRole = apps.get_model('backend', 'UserRole')
    UserRole.objects.filter(name__in=[r[0] for r in ROLES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('backend', '0004_alter_customuser_avatar_alter_productimage_image'),
    ]

    operations = [
        migrations.RunPython(seed_roles, reverse_code=remove_roles),
    ]
