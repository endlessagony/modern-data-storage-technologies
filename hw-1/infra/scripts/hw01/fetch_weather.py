#!/usr/bin/env python3
"""Получение исторической погоды с Open-Meteo для своего источника ДЗ.

Источник: Open-Meteo Historical Weather API (архив на основе ERA5),
условия использования CC BY 4.0, официальный сайт https://open-meteo.com/.

Запуск (из infra/, на хосте, python3 не требует Spark):
    python3 scripts/hw01/fetch_weather.py

Скрипт делает по одному запросу на город и сохраняет ответ API как есть
в data/hw01/raw_json/<city>.json (это и есть raw без изменений). Затем
отдельным шагом в этом же файле собирает табличный CSV
data/hw01/weather.csv из восьми JSON-ответов. CSV дальше загружается в
raw-бакет и является входом для pipeline.py.

Период и города фиксированы, чтобы результат можно было повторить.
"""

import csv
import json
import os
import time
import urllib.parse
import urllib.request

BASE_URL = "https://archive-api.open-meteo.com/v1/archive"
START_DATE = "2023-01-01"
END_DATE = "2024-12-31"
HOURLY_VARS = ["temperature_2m", "relative_humidity_2m", "precipitation", "wind_speed_10m"]

# (slug для файла, название города, широта, долгота)
CITIES = [
    ("moscow", "Москва", 55.7558, 37.6176),
    ("spb", "Санкт-Петербург", 59.9343, 30.3351),
    ("novosibirsk", "Новосибирск", 55.0084, 82.9357),
    ("ekaterinburg", "Екатеринбург", 56.8389, 60.6057),
    ("kazan", "Казань", 55.7887, 49.1221),
    ("krasnodar", "Краснодар", 45.0355, 38.9753),
    ("vladivostok", "Владивосток", 43.1155, 131.8855),
    ("murmansk", "Мурманск", 68.9585, 33.0827),
]

RAW_DIR = os.path.join("data", "hw01", "raw_json")
OUT_CSV = os.path.join("data", "hw01", "weather.csv")


def fetch_city(slug, name, lat, lon):
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "hourly": ",".join(HOURLY_VARS),
        "timezone": "UTC",
    }
    url = BASE_URL + "?" + urllib.parse.urlencode(params)
    print(f"Запрос {name}: {url}")
    with urllib.request.urlopen(url, timeout=60) as resp:
        raw = resp.read()

    path = os.path.join(RAW_DIR, f"{slug}.json")
    with open(path, "wb") as f:
        f.write(raw)
    print(f"  сохранено {len(raw) / 1024:.1f} КиБ -> {path}")
    return json.loads(raw)


def main():
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)

    rows_written = 0
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow([
            "city", "latitude", "longitude", "event_ts", "event_date",
            "temperature_2m", "relative_humidity_2m", "precipitation_mm",
            "wind_speed_10m",
        ])
        for slug, name, lat, lon in CITIES:
            data = fetch_city(slug, name, lat, lon)
            hourly = data["hourly"]
            times = hourly["time"]
            temp = hourly.get("temperature_2m", [None] * len(times))
            hum = hourly.get("relative_humidity_2m", [None] * len(times))
            prec = hourly.get("precipitation", [None] * len(times))
            wind = hourly.get("wind_speed_10m", [None] * len(times))

            for i, ts in enumerate(times):
                writer.writerow([
                    name, lat, lon,
                    ts.replace("T", " ") + ":00",
                    ts[:10],
                    temp[i], hum[i], prec[i], wind[i],
                ])
                rows_written += 1

            time.sleep(1)  # не перегружаем бесплатный публичный API

    size_mb = os.path.getsize(OUT_CSV) / 1024 / 1024
    print(f"\nГотово: {OUT_CSV}")
    print(f"Городов: {len(CITIES)}; строк без заголовка: {rows_written:,}; размер: {size_mb:.2f} МиБ")


if __name__ == "__main__":
    main()
