import os
import mysql.connector
from mysql.connector import pooling
from contextlib import contextmanager
from config import Config

_pool = mysql.connector.pooling.MySQLConnectionPool(
    pool_name='finsight_pool',
    pool_size=20,
    pool_reset_session=True,
    host=Config.DB_HOST,
    port=Config.DB_PORT,
    user=Config.DB_USER,
    password=Config.DB_PASSWORD,
    database=Config.DB_NAME,
    charset='utf8mb4',
    autocommit=False,
    connection_timeout=10,
)

@contextmanager
def get_connection():
    conn = _pool.get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

@contextmanager
def transaction():
    conn = _pool.get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        yield conn, cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

def query_one(sql, params=()):
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(sql, params)
            return cursor.fetchone()
        finally:
            cursor.close()

def query_all(sql, params=()):
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(sql, params)
            return cursor.fetchall()
        finally:
            cursor.close()

def execute(sql, params=()):
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(sql, params)
            return cursor.lastrowid
        finally:
            cursor.close()

def init_db():
    schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
    if not os.path.exists(schema_path):
        return

    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = f.read()

    conn = mysql.connector.connect(
        host=Config.DB_HOST, port=Config.DB_PORT,
        user=Config.DB_USER, password=Config.DB_PASSWORD,
    )
    cursor = conn.cursor()
    cursor.execute(f"USE {Config.DB_NAME}")

    cursor.execute("SET FOREIGN_KEY_CHECKS=0;")
    for statement in schema.split(';'):
        stmt = statement.strip()
        if stmt and not stmt.startswith('--'):
            try:
                cursor.execute(stmt)
            except mysql.connector.Error as e:
                if e.errno != 1050:
                    print(f"Schema warning: {e}")
    cursor.execute("SET FOREIGN_KEY_CHECKS=1;")

    conn.commit()
    cursor.close()
    conn.close()
    print("✅ Database schema initialized")