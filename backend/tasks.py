from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site
import logging

from backend.models import CustomUser, Order

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def send_verification_email_task(self, user_id, site_domain):
    """
    Асинхронная задача для отправки письма подтверждения email.

    Args:
        user_id: ID пользователя
        site_domain: Домен сайта для формирования ссылки
    """
    try:
        user = CustomUser.objects.get(id=user_id)
        token = user.generate_email_verification_token()

        verify_url = f"http://{site_domain}/api/verify-email/?token={token}&email={user.email}"

        subject = 'Подтверждение email'
        message = f'''
Здравствуйте, {user.first_name}!

Пожалуйста, подтвердите ваш email, перейдя по ссылке:
{verify_url}

Эта ссылка действительна в течение 24 часов.

Если вы не регистрировались на нашем сайте, просто проигнорируйте это письмо.
'''

        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        logger.info(f"Письмо подтверждения отправлено на {user.email}")
        return {'status': 'success', 'email': user.email}

    except CustomUser.DoesNotExist:
        logger.error(f"Пользователь с ID {user_id} не найден")
        return {'status': 'error', 'message': 'User not found'}
    except Exception as e:
        logger.error(f"Ошибка отправки email: {e}")
        # Повторная попытка с экспоненциальной задержкой
        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))


@shared_task(bind=True, max_retries=3)
def send_order_confirmation_email_task(self, order_id):
    """
    Асинхронная задача для отправки email-уведомлений о подтверждении заказа.

    Args:
        order_id: ID подтверждённого заказа
    """
    try:
        order = Order.objects.get(id=order_id)

        # Получаем товары заказа с оптимизацией запросов
        order_items = list(
            order.order_items.select_related('product', 'shop__user').all()
        )

        # Формируем информацию о заказе
        items_info = ""
        shops_in_order = set()
        for item in order_items:
            items_info += (
                f"- {item.product.name} (Магазин: {item.shop.name})"
                f" × {item.quantity} шт. = {item.get_price()} руб.\n"
            )
            if item.shop.user.email:
                shops_in_order.add(item.shop.user.email)

        total_price = order.get_total_price()

        # Информация о контакте
        contact_info = ""
        if order.contact:
            contact_info = f"""
Контактные данные:
ФИО: {order.contact.last_name} {order.contact.first_name} {order.contact.patronymic}
Email: {order.contact.email}
Телефон: {order.contact.phone}
Адрес: г.{order.contact.city}, ул.{order.contact.street},
д.{order.contact.house}, корп.{order.contact.building},
стр.{order.contact.structure}, кв.{order.contact.apartment}
ID контакта: {order.contact.id}
"""

        # Тема и сообщение для пользователя
        subject_user = f'Заказ #{order.id} подтвержден'
        message_user = f'''
Здравствуйте, {order.user.first_name}!

Ваш заказ #{order.id} успешно подтвержден.

ID корзины: {order.id}
ID контакта: {order.contact.id if order.contact else 'Не указан'}
Дата заказа: {order.date}
Статус: {order.get_status_display()}

Товары в заказе:
{items_info}

Общая сумма: {total_price} руб.
{contact_info}
Спасибо за ваш заказ!
'''

        # Тема и сообщение для администраторов
        subject_admin = f'Новый заказ #{order.id}'
        message_admin = f'''
Поступил новый заказ #{order.id} от пользователя {order.user.email} ({order.user.get_full_name()})

ID корзины: {order.id}
ID контакта: {order.contact.id if order.contact else 'Не указан'}
Дата заказа: {order.date}
Статус: {order.get_status_display()}

Товары в заказе:
{items_info}

Общая сумма: {total_price} руб.
{contact_info}
'''

        # Список email для отправки
        recipients = [order.user.email]

        # Добавляем администраторов
        admins = CustomUser.objects.filter(role__name='admin')
        recipients.extend([admin.email for admin in admins if admin.email])

        # Добавляем владельцев магазинов
        recipients.extend(list(shops_in_order))

        # Удаляем дубликаты
        recipients = list(set(recipients))

        # Отправляем email каждому получателю
        sent_count = 0
        for recipient in recipients:
            if recipient == order.user.email:
                message = message_user
                subject = subject_user
            else:
                message = message_admin
                subject = subject_admin

            try:
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [recipient],
                    fail_silently=True,
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Ошибка отправки email на {recipient}: {e}")

        logger.info(f"Отправлено {sent_count} писем для заказа #{order.id}")
        return {'status': 'success', 'sent_count': sent_count, 'order_id': order.id}

    except Order.DoesNotExist:
        logger.error(f"Заказ с ID {order_id} не найден")
        return {'status': 'error', 'message': 'Order not found'}
    except Exception as e:
        logger.error(f"Ошибка отправки email для заказа {order_id}: {e}")
        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))