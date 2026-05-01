from decimal import Decimal

from django.db import migrations, models


def populate_order_item_prices(apps, schema_editor):
    OrderItem = apps.get_model('backend', 'OrderItem')
    for item in OrderItem.objects.select_related('product').all():
        item.price = item.product.price if item.product else Decimal('0.00')
        item.save(update_fields=['price'])


class Migration(migrations.Migration):

    dependencies = [
        ('backend', '0005_seed_user_roles'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='email_verification_token_created_at',
            field=models.DateTimeField(
                blank=True, null=True,
                verbose_name='Дата создания токена верификации'
            ),
        ),
        migrations.AddField(
            model_name='orderitem',
            name='price',
            field=models.DecimalField(
                decimal_places=2, max_digits=10,
                verbose_name='Цена на момент добавления',
                default=Decimal('0.00'),
            ),
            preserve_default=False,
        ),
        migrations.RunPython(
            populate_order_item_prices,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='contact',
            name='patronymic',
            field=models.CharField(blank=True, max_length=40, verbose_name='Отчество'),
        ),
    ]
