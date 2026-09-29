"""
Опыт двух сессий на маленькой таблице: что видит вторая сессия, пока первая не завершила транзакцию (MVCC),
и что происходит, когда вторая сессия пытается изменить ту же строку (блокировка и как найти ожидающего).

Опыты выполняются на одиночном сервере, в схеме demo. Все транзакции завершаются.
"""
import os
import threading
import time

import psycopg2

PORT = int(os.environ.get("MAIN_PORT", 5440))
DB = os.environ.get("MAIN_DB", "shots")


def connect(isolation=None):
    conn = psycopg2.connect(host="127.0.0.1", port=PORT, dbname=DB, user="postgres")
    if isolation:
        conn.set_session(isolation_level=isolation)
    return conn


def show(who, cur, sql, params=None):
    """Выполняет запрос от имени сессии и печатает результат строками."""
    text = " ".join((cur.mogrify(sql, params).decode() if params else sql).split())
    cur.execute(sql, params)
    print(f"  [{who}] {text}")
    if cur.description:
        names = [d[0] for d in cur.description]
        for row in cur.fetchall():
            print("        " + ", ".join(f"{n}={v}" for n, v in zip(names, row)))
    return cur


def step(text):
    print(f"\n--- {text}")


def main():
    admin = connect()
    admin.autocommit = True
    acur = admin.cursor()
    acur.execute("drop schema if exists demo cascade")
    acur.execute("create schema demo")
    acur.execute("create table demo.team_goals (team_id bigint primary key, team_name text not null, goals int not null)")
    acur.execute("insert into demo.team_goals values (779, 'Argentina', 3), (771, 'France', 3), (1, 'Test FC', 0)")

    print("=" * 78)
    print("ОПЫТ 1. READ COMMITTED (уровень по умолчанию): чтение, пока чужая транзакция не завершена")
    print("=" * 78)
    s1, s2 = connect("READ COMMITTED"), connect("READ COMMITTED")
    c1, c2 = s1.cursor(), s2.cursor()
    show("сессия 1", c1, "show transaction_isolation")
    show("сессия 2", c2, "show transaction_isolation")

    step("сессия 1 меняет строку и НЕ завершает транзакцию")
    show("сессия 1", c1, "select txid_current() as my_txid")
    show("сессия 1", c1, "update demo.team_goals set goals = 4 where team_id = 779")
    show("сессия 1", c1, "select team_name, goals, xmin, xmax from demo.team_goals where team_id = 779")

    step("сессия 2 читает ту же строку: видит старое значение")
    show("сессия 2", c2, "select team_name, goals, xmin, xmax from demo.team_goals where team_id = 779")
    print("  (в xmax старой версии стоит номер транзакции сессии 1, но она не завершена, поэтому версия для сессии 2 всё ещё актуальна)")

    step("сессия 1 завершает транзакцию (COMMIT), сессия 2 повторяет чтение в своей транзакции")
    s1.commit()
    show("сессия 2", c2, "select team_name, goals, xmin, xmax from demo.team_goals where team_id = 779")
    print("  (READ COMMITTED: снимок берётся на каждый запрос, новое чтение видит зафиксированное значение; xmin новой версии = txid сессии 1)")
    s2.commit()

    print()
    print("=" * 78)
    print("ОПЫТ 2. REPEATABLE READ: снимок фиксируется на всю транзакцию")
    print("=" * 78)
    s1, s2 = connect("READ COMMITTED"), connect("REPEATABLE READ")
    c1, c2 = s1.cursor(), s2.cursor()
    show("сессия 2", c2, "show transaction_isolation")
    show("сессия 2", c2, "select team_name, goals from demo.team_goals where team_id = 779")
    step("сессия 1 меняет строку и сразу фиксирует")
    show("сессия 1", c1, "update demo.team_goals set goals = 5 where team_id = 779")
    s1.commit()
    step("сессия 2 читает снова в той же транзакции: снимок прежний")
    show("сессия 2", c2, "select team_name, goals from demo.team_goals where team_id = 779")
    s2.commit()
    step("после завершения транзакции сессии 2 новый снимок видит изменение")
    show("сессия 2", c2, "select team_name, goals from demo.team_goals where team_id = 779")
    s2.commit()
    s1.close(); s2.close()

    print()
    print("=" * 78)
    print("ОПЫТ 3. Изменение той же строки второй сессией: блокировка и поиск ожидающего")
    print("=" * 78)
    s1, s2 = connect("READ COMMITTED"), connect("READ COMMITTED")
    c1, c2 = s1.cursor(), s2.cursor()
    c2.execute("select pg_backend_pid()"); pid2 = c2.fetchone()[0]
    c1.execute("select pg_backend_pid()"); pid1 = c1.fetchone()[0]
    show("сессия 1", c1, "update demo.team_goals set goals = 6 where team_id = 779")
    print(f"  (сессия 1: pid {pid1}, держит блокировку строки и не завершена)")

    outcome = {}

    def blocked_update():
        c2.execute("set lock_timeout = '20s'")
        started = time.perf_counter()
        c2.execute("update demo.team_goals set goals = goals + 100 where team_id = 779")
        outcome["waited_s"] = time.perf_counter() - started

    step(f"сессия 2 (pid {pid2}) пытается изменить ту же строку и повисает")
    worker = threading.Thread(target=blocked_update)
    worker.start()

    watcher = connect()
    watcher.autocommit = True
    wcur = watcher.cursor()
    for _ in range(50):     # ждём, пока сессия 2 действительно окажется в ожидании
        wcur.execute("select wait_event_type from pg_stat_activity where pid = %s", (pid2,))
        if wcur.fetchone()[0] == "Lock":
            break
        time.sleep(0.1)

    time.sleep(1.5)
    print(f"  через 1,5 с сессия 2 всё ещё ждёт: {worker.is_alive()}")

    step("наблюдатель (третье соединение) находит ожидающую сессию")
    show("наблюдатель", wcur, """
        select pid, state, wait_event_type, wait_event, pg_blocking_pids(pid) as blocked_by, left(query, 60) as query
        from pg_stat_activity where pid = %s""", (pid2,))
    show("наблюдатель", wcur, """
        select l.pid, l.locktype, l.mode, l.granted
        from pg_locks l where l.pid = %s and not l.granted""", (pid2,))
    show("наблюдатель", wcur, """
        select b.pid as blocking_pid, b.state as blocking_state, left(b.query, 60) as blocking_last_query
        from pg_stat_activity b where b.pid = any(pg_blocking_pids(%s))""", (pid2,))

    step("сессия 1 завершает транзакцию, ожидание снимается, сессия 2 завершает свою")
    s1.commit()
    worker.join()
    print(f"  сессия 2 ждала {outcome['waited_s']:.2f} с, потом выполнила свой UPDATE")
    s2.commit()
    show("наблюдатель", wcur, "select team_name, goals from demo.team_goals where team_id = 779")
    print("  (6 от сессии 1, затем +100 от сессии 2: изменения применены последовательно, потерянного обновления нет)")

    step("проверка: открытых транзакций не осталось")
    show("наблюдатель", wcur, "select count(*) as idle_in_transaction from pg_stat_activity "
                              "where datname = current_database() and state like 'idle in transaction%'")
    s1.close(); s2.close(); watcher.close()
    acur.execute("drop schema demo cascade")
    admin.close()


if __name__ == "__main__":
    main()
