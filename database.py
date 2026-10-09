import mysql.connector
from configparser import ConfigParser
import os
from contextlib import contextmanager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.ini")

def cargar_configuracion():
    config = ConfigParser()
    if os.path.exists(CONFIG_PATH):
        config.read(CONFIG_PATH, encoding='utf-8')
    return config

def obtener_conexion():
    config = cargar_configuracion()
    
    sec = 'database' if config.has_section('database') else ('DATABASE' if config.has_section('DATABASE') else None)
    
    if sec:
        host = config.get(sec, 'host', fallback='localhost')
        port = config.getint(sec, 'port', fallback=3306)
        user = config.get(sec, 'user', fallback='root')
        password = config.get(sec, 'password', fallback='')
        db_name = config.get(sec, 'database', fallback=config.get(sec, 'db_name', fallback='taller_automotriz_db'))
    else:
        host, port, user, password, db_name = 'localhost', 3306, 'root', '', 'taller_automotriz_db'

    return mysql.connector.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=db_name
    )

@contextmanager
def conexion_db(diccionario=True):
    conexion = obtener_conexion()
    cursor = conexion.cursor(dictionary=diccionario)
    try:
        yield conexion, cursor
    finally:
        cursor.close()
        conexion.close()