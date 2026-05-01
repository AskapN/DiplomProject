# Backend-приложение для автоматизации закупок

REST API для автоматизации закупок в розничной сети.

- **Покупателям** — просматривать товары, управлять корзиной, оформлять и отслеживать заказы
- **Магазинам** — загружать прайс-листы (YAML/JSON), управлять изображениями, обрабатывать заказы
- **Администраторам** — полное управление пользователями, заказами и системой

---

## Технологии

| Компонент | Стек |
|---|---|
| API | Django 6.0 + Django REST Framework 3.17 |
| Аутентификация | JWT (simplejwt) + Social Auth (Google) |
| База данных | PostgreSQL 16 / SQLite (локальная разработка) |
| Кэш и брокер | Redis 7 |
| Очередь задач | Celery 5 |
| Документация | drf-spectacular (OpenAPI 3, Swagger UI) |
| Изображения | django-imagekit (авто-миниатюры) |
| Профилирование | django-silk (только при DEBUG=True) |
| Мониторинг | Sentry / GlitchTip |
| WSGI-сервер | Gunicorn |

---

## Структура проекта

```
orders/
├── backend/
│   ├── migrations/          # Миграции БД
│   ├── admin.py             # Django Admin
│   ├── apps.py              # Конфигурация приложения + post_migrate хук
│   ├── filters.py           # Фильтры ProductListAPIView
│   ├── models.py            # Модели данных
│   ├── permission.py        # Кастомные права доступа
│   ├── serializers.py       # Сериализаторы DRF
│   ├── social_pipeline.py   # OAuth pipeline (JWT -> Redis cache)
│   ├── tasks.py             # Celery-задачи (email, миниатюры)
│   ├── throttling.py        # Кастомный тротлинг
│   ├── urls.py              # URL-маршруты приложения
│   └── views.py             # API-представления
├── orders/
│   ├── celery.py            # Инициализация Celery
│   ├── settings.py          # Настройки проекта
│   └── urls.py              # Корневые URL-маршруты
├── Data/                    # Примеры YAML-прайсов
├── .env.example             # Шаблон переменных окружения
├── manage.py
└── requirements.txt
```

---

## Роли пользователей

| Роль | Права |
|---|---|
| `admin` | Полный доступ: все заказы и все пользователи |
| `shop` | Загрузка прайса, управление изображениями, заказы своего магазина |
| `shop_employee` | Просмотр и обработка заказов магазина |
| `buyer` | Просмотр товаров, корзина, оформление заказов |

---

## Быстрый старт (локально)

### 1. Виртуальное окружение

```bash
python3 -m venv .venv
source .venv/bin/activate        # Linux/Mac
# .venv\Scripts\activate         # Windows
pip install -r requirements.txt
```

### 2. Переменные окружения

```bash
cp .env.example .env
```

Для локальной разработки достаточно задать только `SECRET_KEY`:

```env
SECRET_KEY=any-local-dev-secret
DEBUG=True
```

При `DEBUG=True` используется SQLite, письма выводятся в консоль, Celery работает синхронно — отдельный воркер не нужен.

### 3. Миграции и суперпользователь

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 4. Запуск

```bash
python manage.py runserver
```

| URL | Описание |
|---|---|
| http://127.0.0.1:8000/api/ | REST API |
| http://127.0.0.1:8000/api/docs/ | Swagger UI |
| http://127.0.0.1:8000/api/redoc/ | ReDoc |
| http://127.0.0.1:8000/admin/ | Django Admin |
| http://127.0.0.1:8000/silk/ | Silk (только DEBUG=True) |

---

## Переменные окружения

Полный список в `.env.example`. Ключевые:

| Переменная | По умолчанию | Описание |
|---|---|---|
| `SECRET_KEY` | — | **Обязательно.** Django secret key |
| `DEBUG` | `False` | Режим отладки (True = SQLite + console email) |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Разрешённые хосты через запятую |
| `DB_ENGINE` | sqlite3 | `django.db.backends.postgresql` для Postgres |
| `DB_NAME` | `db.sqlite3` | Имя БД |
| `DB_USER` | — | Пользователь БД |
| `DB_PASSWORD` | — | Пароль БД |
| `DB_HOST` | — | Хост БД |
| `DB_PORT` | `5432` | Порт БД |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Брокер задач |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/0` | Backend для результатов Celery |
| `REDIS_URL` | `redis://localhost:6379/1` | Redis для кэша |
| `DEFAULT_FROM_EMAIL` | `noreply@localhost` | Email отправителя |
| `EMAIL_HOST` | — | SMTP-сервер |
| `EMAIL_PORT` | `587` | SMTP-порт |
| `EMAIL_HOST_USER` | — | SMTP-логин |
| `EMAIL_HOST_PASSWORD` | — | SMTP-пароль |
| `SENTRY_DSN` | — | DSN для Sentry/GlitchTip |
| `SOCIAL_AUTH_GOOGLE_OAUTH2_KEY` | — | Google OAuth2 Client ID |
| `SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET` | — | Google OAuth2 Client Secret |

---

## API Endpoints

Аутентификация: заголовок `Authorization: Bearer <access_token>`

### Аутентификация

| Метод | URL | Описание | Права |
|---|---|---|---|
| POST | `/api/register/` | Регистрация (роль buyer) | — |
| POST | `/api/login/` | Вход, возвращает JWT | — |
| GET | `/api/verify-email/` | Подтверждение email (`?token=&email=`) | — |
| POST | `/api/token/refresh/` | Обновление access-токена | — |
| GET | `/api/auth/social/<provider>/` | Редирект к OAuth-провайдеру | — |
| GET | `/api/auth/social/token/` | Получить JWT после OAuth (из сессии) | — |

Поддерживаемый провайдер: `google-oauth2`.  
Токен верификации email действителен **24 часа**.

### Товары

| Метод | URL | Описание | Права |
|---|---|---|---|
| GET | `/api/products/` | Список товаров с фильтрами | — |
| GET | `/api/products/<id>/images/` | Изображения товара | auth |
| POST | `/api/products/<id>/images/` | Загрузить изображение | shop, shop_employee |
| DELETE | `/api/products/<id>/images/<img_id>/` | Удалить изображение | shop, shop_employee |
| POST | `/api/partner/update/` | Загрузить прайс YAML/JSON (`url` или `file`). Лимит: 10 запросов/час | shop, shop_employee |

**Фильтры:** `name`, `price_min`, `price_max`, `in_stock`, `shop_id`, `category_name`, `model`, `parameter`, `ordering`

### Корзина

| Метод | URL | Описание |
|---|---|---|
| GET | `/api/cart/` | Просмотр текущей корзины |
| POST | `/api/cart/add/` | Добавить товар `{"product_info_id": 1, "quantity": 2}` |
| PUT | `/api/cart/update/<item_id>/` | Изменить количество |
| DELETE | `/api/cart/remove/<item_id>/` | Удалить позицию |

### Контакты

| Метод | URL | Описание |
|---|---|---|
| GET / POST | `/api/contact/` | Список / создать |
| GET / PATCH / DELETE | `/api/contact/<id>/` | Просмотр / обновление / удаление |

Поле `patronymic` — необязательное.

### Заказы

| Метод | URL | Описание | Права |
|---|---|---|---|
| POST | `/api/order/confirm/` | Подтвердить корзину | buyer |
| GET | `/api/orders/` | Список заказов (по роли, с пагинацией) | auth |
| GET | `/api/orders/<id>/` | Просмотр заказа | auth |
| PATCH | `/api/orders/<id>/` | Обновить статус | shop, admin |

Цена фиксируется в момент добавления в корзину и не меняется при изменении прайса.  
**Статусы:** `new` → `confirmed` → `shipped` → `delivered` · `cancelled`

---

## Модель данных

| Модель | Описание |
|---|---|
| `CustomUser` | Пользователь: телефон, аватар, роль, верификация email |
| `UserRole` | Роли: `admin`, `shop`, `shop_employee`, `buyer` |
| `Shop` | Магазин одного пользователя |
| `ShopEmployee` | Привязка сотрудника к магазину |
| `Category` | Категория товаров (M2M с магазинами) |
| `Product` | Базовый товар |
| `ProductInfo` | Товар в магазине: цена, РРЦ, количество, параметры |
| `ProductImage` | Изображение товара с авто-миниатюрами 150/300/800 px |
| `Parameter` | Наименование параметра (Цвет, Память и т. д.) |
| `ProductParameter` | Значение параметра для конкретного товара |
| `Contact` | Адрес доставки пользователя |
| `Order` | Заказ со статусом и привязкой к контакту |
| `OrderItem` | Позиция заказа: товар, магазин, количество, **зафиксированная цена** |

---

## Email-уведомления

Отправляются через Celery-задачи:

- **Регистрация** — ссылка подтверждения email (токен действует 24 часа)
- **Подтверждение заказа** — покупателю + администраторам + владельцам задействованных магазинов

При `DEBUG=True` — вывод в консоль. При `DEBUG=False` — SMTP из `.env`.

---

## Мониторинг (GlitchTip)

Self-hosted аналог Sentry. Запуск:

```bash
docker compose -f docker-compose.glitchtip.yml up -d
```

Создайте проект на http://localhost:8001, добавьте DSN в `.env`:

```env
SENTRY_DSN=http://...@localhost:8001/<project-id>
```

Эндпоинт проверки: `GET /api/sentry-test/` (только при `DEBUG=True`).

---

## Лицензия

Проект создан в рамках дипломного проекта профессии «Python-разработчик: расширенный курс».
