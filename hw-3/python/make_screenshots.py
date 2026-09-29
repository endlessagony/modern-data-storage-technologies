"""
Собирает «скриншоты выполнения» из сохранённых выводов (*_output.txt, bench_plans.txt).

Каждый снимок - окно терминала с настоящим выводом соответствующего шага и заголовком, в котором написано,
какую проверку он подтверждает. Скрипт ничего не считает и не запускает: только рисует уже полученный текст,
поэтому его можно повторить без стенда. Требуется Pillow.
"""
import re
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "results"
SCREENSHOTS_DIR = ROOT / "screenshots"
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
    "C:/Windows/Fonts/consola.ttf",
    "/System/Library/Fonts/Menlo.ttc",
]
BG, FG, ACCENT, MUTED, BAR = (24, 26, 31), (220, 223, 228), (128, 203, 138), (140, 146, 158), (40, 43, 51)
MAX_COLUMNS = 150


def load_font(size):
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise SystemExit("не найден моноширинный шрифт с кириллицей, добавьте путь в FONT_CANDIDATES")


def read(name):
    return (RESULTS_DIR / name).read_text(encoding="utf-8").splitlines()


def between(lines, start, end=None, include_end=False):
    """Строки от первой строки, подходящей под start, до строки, подходящей под end (не включая её)."""
    begin = next(i for i, line in enumerate(lines) if re.search(start, line))
    stop = len(lines)
    if end:
        for i in range(begin + 1, len(lines)):
            if re.search(end, lines[i]):
                stop = i + (1 if include_end else 0)
                break
    return lines[begin:stop]


def plan(name_in_file):
    """План одной пары (запрос, вариант) из bench_plans.txt без текста самого запроса."""
    lines = read("bench_plans.txt")
    block = between(lines, re.escape(f"===== {name_in_file}"), r"^===== ")
    start = next(i for i, line in enumerate(block) if line.endswith(";")) + 1
    return [block[0]] + [line for line in block[start:] if line.strip()]


def trim(lines):
    result = []
    for line in lines:
        line = line.rstrip()
        result.extend(textwrap.wrap(line, MAX_COLUMNS, subsequent_indent="    ", replace_whitespace=False,
                                    drop_whitespace=False) or [""])
    return result


def render(target, title, confirms, lines):
    font, small = load_font(15), load_font(14)
    body = trim(lines)
    line_h = 21
    columns = max(max(len(x) for x in body), len(confirms) + 15)
    width = int(columns * font.getlength("M") + 48)
    header_h = 74
    image = Image.new("RGB", (max(width, 900), header_h + line_h * len(body) + 28), BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, image.width, header_h - 8], fill=BAR)
    for i, color in enumerate([(237, 106, 94), (245, 191, 79), (97, 197, 84)]):
        draw.ellipse([16 + i * 22, 14, 28 + i * 22, 26], fill=color)
    draw.text((100, 11), title, font=small, fill=FG)
    draw.text((16, 40), "Подтверждает: " + confirms, font=small, fill=ACCENT)
    y = header_h
    for line in body:
        draw.text((16, y), line, font=font, fill=FG)
        y += line_h
    image.save(SCREENSHOTS_DIR / target)
    print("сохранено", target)


def main():
    bench = read("bench_output.txt")
    equal = read("equality_output.txt")
    partitions = read("partitions_output.txt")
    independent = read("independent_output.txt")
    backup = read("backup_output.txt")
    mvcc = read("mvcc_output.txt")
    cluster = read("cluster_demo_output.txt")
    pruning_start = r"== план без стоимости: запрос narrow, таблица dds.fact_shot_part =="

    shots = [
        ("plan_narrow_before", "EXPLAIN (ANALYZE, BUFFERS): узкий запрос, исходная таблица",
         "план ДО оптимизации: Seq Scan по всей таблице (1535 буферов), 78 строк в ответе",
         plan("narrow / plain")),
        ("plan_narrow_after_index", "EXPLAIN (ANALYZE, BUFFERS): узкий запрос, таблица с индексом",
         "план ПОСЛЕ добавления составного B-tree: Index Scan, читается около 6% буферов",
         plan("narrow / idx")),
        ("plan_narrow_partitioned", "EXPLAIN (ANALYZE, BUFFERS): узкий запрос, секционированные таблицы",
         "план ПОСЛЕ секционирования: остаётся одна секция (2024), без индекса и с индексом",
         plan("narrow / part:") + [""] + plan("narrow / part_idx")),
        ("plan_wide_before_after", "EXPLAIN (ANALYZE, BUFFERS): широкий запрос, исходная таблица и таблица с индексом",
         "план широкого запроса ДО и ПОСЛЕ индекса (сканирование ~70% строк таблицы)",
         plan("wide / plain") + [""] + plan("wide / idx")),
        ("partitions_bounds", "partitions_check.sh: секции, границы и края интервала",
         "границы [начало; конец), данные лежат в 12 секциях, 2023-12-31 и 2024-01-01 попадают в разные секции",
         between(partitions, r"== секции и границы", pruning_start)),
        ("partitions_pruning", "partitions_check.sh: какие секции остались в планах",
         "узкий запрос читает 1 секцию из 13, широкий - 9 из 13 (остальные отсечены)",
         between(partitions, pruning_start, None)),
        ("measurements", "bench.py: девять повторов после прогрева, медианы",
         "измерения: серверное время, время планирования, клиентское время и cost - отдельными колонками", bench),
        ("results_equal", "check_equal.py: EXCEPT ALL в обе стороны",
         "после каждого изменения таблицы и результаты обоих запросов совпадают с исходными", equal),
        ("control_slice", "independent_check.py: контрольный срез (866 ударов) против расчёта по CSV",
         "смысл результата: независимый расчёт по CSV и итоги ДЗ-2 совпадают с SQL на всех вариантах", independent),
        ("patroni_roles", "cluster_demo.sh: роли узлов до switchover",
         "фактические роли узлов определены средствами Patroni, REST API и SQL (pg_is_in_recovery)",
         between(cluster, r"### 1\. Роли", r"### 2\.")),
        ("marker_on_replica", "cluster_demo.sh: маркер и отставание",
         "запись с уникальным маркером на лидере прочитана на реплике; контрольный срез реплицирован",
         between(cluster, r"### 3\. Маркер", r"### 5\.")),
        ("switchover_roles_marker", "cluster_demo.sh: switchover, роли и маркеры после смены лидера",
         "роли поменялись, старый маркер виден на новом лидере, клиент пишет в текущий лидер, новый маркер доехал",
         between(cluster, r"### 5\. Плановая", r"### 9\.")),
        ("replica_rejects_write", "cluster_demo.sh: запись в реплику",
         "обычная запись в реплику отклонена сообщением базы, изменения нет ни на одном узле",
         between(cluster, r"### 9\.", None)),
        ("backup_and_restore", "backup_restore.sh: копия и восстановление",
         "версии утилит, формат и команда pg_dump, код возврата pg_restore = 0",
         between(backup, r"### Версии утилит", r"### 3\.")),
        ("restored_db_checks", "verify_restore.py и independent_check.py на восстановленной базе",
         "итог проверки восстановленной базы: структура, строки, ключи, ограничения, контрольные строки, запросы",
         between(backup, r"### 3\.", None)),
        ("mvcc_isolation", "mvcc_two_sessions.py: опыт 1 и 2",
         "MVCC: чужая незавершённая транзакция не видна; READ COMMITTED и REPEATABLE READ",
         between(mvcc, r"ОПЫТ 1", r"ОПЫТ 3")[:-1]),
        ("lock_wait", "mvcc_two_sessions.py: опыт 3",
         "блокировка при изменении той же строки и поиск ожидающей сессии через pg_stat_activity и pg_locks",
         between(mvcc, r"ОПЫТ 3", None)),
    ]
    for number, (name, title, confirms, lines) in enumerate(shots, 1):
        render(f"screenshot_{number:02d}_{name}.png", title, confirms, lines)


if __name__ == "__main__":
    main()
