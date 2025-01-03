# db_utils.py
import streamlit as st
import psycopg2
from psycopg2 import OperationalError

def get_db_connection():
    """
    Returns a new database connection.
    """
    try:
        conn = psycopg2.connect(
            host=st.secrets["db"]["host"],
            database=st.secrets["db"]["name"],
            user=st.secrets["db"]["user"],
            password=st.secrets["db"]["password"],
            port=st.secrets["db"]["port"]
        )
        return conn
    except OperationalError:
        st.error("Não foi possível conectar ao banco de dados.")
        return None

def run_query(query, values=None):
    """
    Executes a SELECT query and returns fetched data.
    """
    conn = get_db_connection()
    if conn is None:
        return []
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, values or ())
            return cursor.fetchall()
    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao executar a consulta: {e}")
        return []
    finally:
        conn.close()

def run_insert(query, values):
    """
    Executes an INSERT, UPDATE, or DELETE query.
    """
    conn = get_db_connection()
    if conn is None:
        return False
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, values)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao executar a consulta: {e}")
        return False
    finally:
        conn.close()
