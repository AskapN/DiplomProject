# Дипломный проект профессии «Python-разработчик: расширенный курс»

## Backend-приложение для автоматизации закупок

REST API приложение для автоматизации закупок в розничной сети.

- **Покупателям:** просматривать товары, управлять корзиной, оформлять заказы, отслеживать статус
- **Магазинам:** загружать прайс-листы, управлять изображениями товаров, обрабатывать заказы
- **Администраторам:** управлять пользователями, просматривать все заказы, контролировать систему

---

## Технологии

| Пакет | Версия |
|---|---|
| Python | 3.x |
| Django | 6.0.3 |
| Django REST Framework | 3.17.1 |
| djangorestframework-simplejwt | 5.5.1 |
| django-filter | 25.2 |
| Pillow | 12.2.0 |
| PyYAML | 6.0.3 |
| python-dotenv | 1.2.2 |
| requests | 2.33.1 |

База данных: **SQLite** (по умолчанию).  
Медиафайлы: хранятся локально в `media/`.

---

## Структура проекта

```
orders/
├── backend/
│   ├── migrations/        # Миграции базы данных
│   ├── admin.py           # Регистрация моделей в Django Admin
│   ├── apps.py            # Конфигурация приложения
│   ├── filters.py         # Фильтры для списка товаров
│   ├── models.py          # Модели данных
│   ├── permission.py      # Кастомные права доступа
│   ├── serializers.py     # Сериализаторы DRF
│   ├── urls.py            # URL-маршруты приложения
│   ├── utils.py           # Вспомогательные функции (email, импорт)
│   └── views.py           # API-представления
├── orders/
│   ├── settings.py        # Настройки проекта
│   └── urls.py            # Корневые URL-маршруты
├── Data/                  # Примеры YAML-файлов с товарами
├── media/                 # Загружаемые медиафайлы (avatars/, products/)
├── .env                   # Переменные окружения (не хранить в git)
├── manage.py
├── requirements.txt
└── README.md
```

---

## Роли пользователей

| Роль | Описание |
|---|---|
| `admin` | Полный доступ: все заказы, все пользователи |
| `shop` | Владелец магазина: управление прайсом, изображениями, заказы своего магазина |
| `shop_employee` | Сотрудник магазина: просмотр и обработка заказов магазина |
| `buyer` | Покупатель: просмотр товаров, корзина, оформление заказов |

---

## Установка и запуск

### 1. Клонирование репозитория

```bash
git clone <repository-url>
cd orders
```

### 2. Виртуальное окружение

```bash
python3 -m venv .venv
source .venv/bin/activate      # Linux/Mac
# или
.venv\Scripts\activate         # Windows
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 4. Файл `.env`

Создайте файл `.env` в корне проекта:

```env
SECRET_KEY=your-secret-key-here
DEBUG=True

# Email (используется только при DEBUG=False)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=your-email@gmail.com
```

> При `DEBUG=True` письма выводятся в консоль, SMTP не используется.

### 5. Миграции

```bash
python manage.py makemigrations
python manage.py migrate
```

### 6. Создание суперпользователя

```bash
python manage.py createsuperuser
```

### 7. Запуск сервера

```bash
python manage.py runserver
```

API доступен по адресу: `http://127.0.0.1:8000/api/`  
Панель администратора: `http://127.0.0.1:8000/admin/`

---

## API Endpoints

### Аутентификация

API использует JWT-токены. Токен передаётся в заголовке:

```
Authorization: Bearer <access_token>
```

#### Регистрация
```
POST /api/register/
```
```json
{
    "first_name": "Иван",
    "last_name": "Иванов",
    "email": "ivan@example.com",
    "password": "Password123",
    "password_confirm": "Password123",
    "phone": "+79001234567"
}
```

#### Вход
```
POST /api/login/
```
```json
{
    "email": "ivan@example.com",
    "password": "Password123"
}
```

**Ответ:**
```json
{
    "status": "success",
    "user": { "id": 1, "email": "...", "role": "buyer", ... },
    "tokens": { "refresh": "...", "access": "..." }
}
```

#### Подтверждение email
```
GET /api/verify-email/?token=<token>&email=<email>
```

---

### Товары

#### Список товаров
```
GET /api/products/
```

Доступен без аутентификации. Поддерживает пагинацию (10 записей на страницу).

**Query-параметры:**

| Параметр | Описание |
|---|---|
| `name` | Поиск по названию |
| `price_min` / `price_max` | Диапазон цены |
| `price_rrc_min` / `price_rrc_max` | Диапазон РРЦ |
| `quantity_min` / `quantity_max` | Диапазон количества |
| `in_stock` | Только в наличии (`true`/`false`) |
| `shop_id` / `shop_name` | Фильтр по магазину |
| `category_id` / `category_name` | Фильтр по категории |
| `model` | Поиск по модели |
| `external_id` | Поиск по внешнему ID |
| `parameter` | Поиск по характеристикам |
| `ordering` | Сортировка (`price`, `-price`, `name`, `-name` и др.) |

Каждый товар в ответе содержит поле `images` — список изображений с абсолютными URL.

---

### Изображения товаров

Доступно для владельцев магазинов и сотрудников. Один товар может иметь несколько изображений.

#### Получить список изображений
```
GET /api/products/<product_info_id>/images/
```

#### Загрузить новое изображение
```
POST /api/products/<product_info_id>/images/
```
`Content-Type: multipart/form-data`, поле: `image`

**Ответ:**
```json
{
    "status": "success",
    "image": { "id": 1, "image_url": "http://...", "created_at": "..." }
}
```

#### Удалить изображение
```
DELETE /api/products/<product_info_id>/images/<image_id>/
```

---

### Корзина

| Метод | URL | Описание |
|---|---|---|
| `GET` | `/api/cart/` | Просмотр корзины |
| `POST` | `/api/cart/add/` | Добавить товар |
| `PUT` | `/api/cart/update/<item_id>/` | Изменить количество |
| `DELETE` | `/api/cart/remove/<item_id>/` | Удалить позицию |

**Добавление товара:**
```json
{ "product_info_id": 1, "quantity": 2 }
```

**Обновление количества:**
```json
{ "quantity": 3 }
```

---

### Контакты (адреса доставки)

| Метод | URL | Описание |
|---|---|---|
| `GET` | `/api/contact/` | Список контактов пользователя |
| `POST` | `/api/contact/` | Создать контакт |
| `GET` | `/api/contact/<id>/` | Просмотр контакта |
| `PATCH` | `/api/contact/<id>/` | Частичное обновление |
| `DELETE` | `/api/contact/<id>/` | Удаление |

**Тело запроса (создание):**
```json
{
    "last_name": "Иванов",
    "first_name": "Иван",
    "patronymic": "Иванович",
    "email": "ivan@example.com",
    "phone": "+79001234567",
    "city": "Москва",
    "street": "Ленина",
    "house": "10",
    "building": "1",
    "structure": "2",
    "apartment": "100"
}
```

> `building`, `structure`, `apartment` — опциональные поля.

---

### Заказы

#### Подтверждение заказа
```
POST /api/order/confirm/
```

Подтверждает корзину (статус `new` → `confirmed`), списывает остатки, отправляет email.

**С новым контактом:**
```json
{
    "last_name": "Иванов", "first_name": "Иван", "patronymic": "Иванович",
    "email": "ivan@example.com", "phone": "+79001234567",
    "city": "Москва", "street": "Ленина", "house": "10"
}
```

**С существующим контактом:**
```json
{ "contact_id": 1 }
```

#### Список заказов
```
GET /api/orders/
```

Выборка зависит от роли пользователя:
- `buyer` — только свои заказы
- `shop` — заказы с товарами из своего магазина
- `shop_employee` — заказы из магазинов, где работает
- `admin` — все заказы

#### Просмотр заказа
```
GET /api/orders/<order_id>/
```

#### Обновление статуса заказа
```
PATCH /api/orders/<order_id>/
```
```json
{ "status": "shipped" }
```

**Доступные статусы:** `new` · `confirmed` · `shipped` · `delivered` · `cancelled`

Права: `admin`, `shop`, `shop_employee`.

---

### Партнеры — импорт прайс-листа

```
POST /api/partner/update/
```

`Content-Type: multipart/form-data`

**Параметры:** `url` (ссылка на файл) или `file` (загружаемый файл).  
**Форматы:** YAML, JSON.

**Пример YAML:**
```yaml
shop: Название магазина
categories:
  - id: 1
    name: Электроника
goods:
  - id: 101
    category: 1
    name: Смартфон X
    model: X-2024
    price: 29990.00
    price_rrc: 34990.00
    quantity: 15
    parameters:
      Цвет: Чёрный
      Память: 128 ГБ
```

> Старые товары магазина удаляются перед загрузкой новых. Вся операция выполняется в транзакции.

---

## Модель данных

| Модель | Описание |
|---|---|
| `CustomUser` | Расширенная модель пользователя (телефон, аватар, роль, верификация email) |
| `UserRole` | Роли: `admin`, `shop`, `shop_employee`, `buyer` |
| `Shop` | Магазин, принадлежит одному `CustomUser` |
| `ShopEmployee` | Привязка сотрудника к магазину с должностью |
| `Category` | Категория товаров (ManyToMany с магазинами) |
| `Product` | Базовый товар (название + категория) |
| `ProductInfo` | Товар в конкретном магазине (цена, РРЦ, количество, параметры, изображения) |
| `ProductImage` | Изображение товара, привязано к `ProductInfo` (несколько на товар) |
| `Parameter` | Наименование параметра (например: «Цвет», «Память») |
| `ProductParameter` | Значение параметра для конкретного `ProductInfo` |
| `Contact` | Адрес доставки пользователя (ФИО, email, телефон, адрес) |
| `Order` | Заказ пользователя со статусом и привязкой к контакту |
| `OrderItem` | Позиция в заказе: товар, магазин, количество |

---

## Email-уведомления

Отправляются автоматически в двух случаях:

- **Регистрация** — письмо со ссылкой для подтверждения email
- **Подтверждение заказа** — персональное письмо покупателю; уведомления администраторам и владельцам магазинов

При `DEBUG=True` все письма выводятся в консоль (backend `console.EmailBackend`).  
При `DEBUG=False` используется SMTP — настройки берутся из `.env`.

---

## Разработка

### Проверка системы
```bash
python manage.py check
```

### Создание и применение миграций
```bash
python manage.py makemigrations
python manage.py migrate
```

### Запуск тестов
```bash
python manage.py test
```

### Линтинг
```bash
pip install flake8
flake8 backend/ --max-line-length=120 --exclude=migrations
```

---

## Лицензия

Проект создан в рамках дипломного проекта профессии «Python-разработчик: расширенный курс».

