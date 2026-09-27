#!/usr/bin/env python3
"""Генератор учебного датасета «события онлайн-сервиса».

Создаёт CSV-файл с событиями пользователей (просмотры, клики, покупки),
напоминающий выгрузку источника данных в реальном DWH. Набор данных
синтетический, персональных данных не содержит.

Использование:
    python3 generate_dataset.py [--rows 200000] [--out data/events_demo.csv]

Размер файла измеряется после генерации; фиксированный размер не обещается.
Одинаковые seed, число строк и реализация генератора воспроизводят строки.
Повторный запуск с тем же seed начинает те же события заново, а не создаёт
новую независимую поставку. Даты условные, по договорённости UTC; CSV не
содержит суффикса часового пояса. Ограничения набора описаны в DATASET.md.
"""

import argparse
import csv
import datetime as dt
import os
import random

SEED = 20260910

EVENT_TYPES = ["page_view", "item_view", "click", "search", "add_to_cart",
               "remove_from_cart", "purchase", "refund"]
EVENT_WEIGHTS = [30, 25, 20, 10, 6, 2, 6, 1]

PLATFORMS = ["web", "android", "ios"]
PLATFORM_WEIGHTS = [45, 35, 20]

DEVICES = ["smartphone", "desktop", "tablet"]
DEVICE_BY_PLATFORM = {
    "web": ["desktop", "smartphone", "tablet"],
    "android": ["smartphone", "tablet"],
    "ios": ["smartphone", "tablet"],
}

OS_VERSIONS = ["13", "14", "15", "16", "17", "18"]
APP_VERSIONS = ["9.1.0", "9.2.0", "9.3.0", "9.4.0", "10.0.0", "10.1.0"]

REGIONS = ["Москва", "Санкт-Петербург", "Московская область",
           "Новосибирская область", "Свердловская область", "Татарстан",
           "Краснодарский край", "Нижегородская область", "Челябинская область",
           "Самарская область", "Ростовская область", "Башкортостан",
           "Пермский край", "Воронежская область", "Волгоградская область",
           "Саратовская область", "Тюменская область", "Иркутская область"]
REGION_WEIGHTS = [22, 11, 8, 5, 5, 4, 4, 3, 3, 3, 3, 3, 2, 2, 2, 2, 2, 2]

CITIES = ["Москва", "Санкт-Петербург", "Химки", "Новосибирск", "Екатеринбург",
          "Казань", "Краснодар", "Нижний Новгород", "Челябинск", "Самара",
          "Ростов-на-Дону", "Уфа", "Пермь", "Воронеж", "Волгоград", "Саратов",
          "Тюмень", "Иркутск"]

CATEGORIES = ["смартфоны", "ноутбуки", "планшеты", "наушники", "колонки",
              "телевизоры", "часы", "фотоаппараты", "аксессуары", "зарядные устройства",
              "powerbank", "чехлы", "стёкла", "клавиатуры", "мыши",
              "мониторы", "принтеры", "роутеры", "видеорегистраторы", "экшн-камеры"]

REFERRERS = ["vk.com", "yandex.ru", "google.com", "mail.ru", "ok.ru",
             "dzen.ru", "telegram.org", "direct", "instagram.com", "tiktok.com"]
REFERRER_WEIGHTS = [25, 25, 15, 10, 8, 5, 4, 20, 4, 4]

CURRENCIES = ["RUB"]
PAYMENT_METHODS = ["card", "sbp", "wallet", "cash_on_delivery", "installment"]

START = dt.datetime(2026, 9, 1, 0, 0, 0)
PERIOD_DAYS = 90


def parse_args():
    p = argparse.ArgumentParser(description="Генератор датасета событий")
    p.add_argument("--rows", type=int, default=200_000,
                   help="положительное количество строк (по умолчанию 200 000)")
    p.add_argument("--out", default=os.path.join("data", "events_demo.csv"),
                   help="путь к итоговому CSV-файлу")
    p.add_argument("--seed", type=int, default=SEED,
                   help="seed генератора (менять не рекомендуется)")
    args = p.parse_args()
    if args.rows <= 0:
        p.error("--rows должен быть положительным целым числом")
    return args


def main():
    args = parse_args()
    rng = random.Random(args.seed)

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)

    users = list(range(100_000, 400_000))
    sessions_per_user_pool = 1_000_000

    header = ["event_id", "user_id", "session_id", "event_ts", "event_date",
              "event_type", "platform", "device_type", "os_version", "app_version",
              "region", "city", "referrer", "category_id", "category_name",
              "price_rub", "quantity", "currency", "payment_method",
              "duration_ms", "ab_group"]

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)

        for i in range(args.rows):
            ts = START + dt.timedelta(seconds=rng.randrange(PERIOD_DAYS * 86400))
            event_type = rng.choices(EVENT_TYPES, weights=EVENT_WEIGHTS, k=1)[0]
            platform = rng.choices(PLATFORMS, weights=PLATFORM_WEIGHTS, k=1)[0]
            device = rng.choice(DEVICE_BY_PLATFORM[platform])

            region_idx = rng.choices(range(len(REGIONS)),
                                     weights=REGION_WEIGHTS, k=1)[0]

            category_idx = rng.randrange(len(CATEGORIES))
            is_purchase = event_type == "purchase"
            is_refund = event_type == "refund"

            price = ""
            quantity = ""
            payment = ""
            if is_purchase or is_refund:
                price = f"{rng.randrange(290, 299_990)}.{rng.randrange(0, 100):02d}"
                quantity = rng.randrange(1, 5)
                payment = rng.choice(PAYMENT_METHODS)

            row = [
                f"{args.seed:010d}-{i:010d}",
                rng.choice(users),
                f"s{rng.randrange(sessions_per_user_pool):010d}",
                ts.strftime("%Y-%m-%d %H:%M:%S"),
                ts.strftime("%Y-%m-%d"),
                event_type,
                platform,
                device,
                rng.choice(OS_VERSIONS),
                rng.choice(APP_VERSIONS),
                REGIONS[region_idx],
                CITIES[region_idx],
                rng.choices(REFERRERS, weights=REFERRER_WEIGHTS, k=1)[0],
                1000 + category_idx * 7,
                CATEGORIES[category_idx],
                price,
                quantity,
                rng.choice(CURRENCIES),
                payment,
                rng.randrange(100, 600_000),
                rng.choice("AB"),
            ]
            w.writerow(row)

            if (i + 1) % 500_000 == 0:
                print(f"  записано {i + 1:,} строк...")

    size_mb = os.path.getsize(args.out) / 1024 / 1024
    print(f"Готово: {args.out}")
    print(f"Строк: {args.rows:,}; размер: {size_mb:.1f} МиБ")


if __name__ == "__main__":
    main()
