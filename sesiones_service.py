import mysql.connector
from database import obtener_conexion

def registrar_inicio_sesion(id_usuario, token, origen='ESCRITORIO'):
    """Guarda o actualiza el token de sesión activa del usuario."""
    try:
        con = obtener_conexion()
        cur = con.cursor()
        cur.execute("""
            UPDATE usuarios 
            SET token_sesion = %s, origen_sesion = %s, ultima_actividad = NOW() 
            WHERE id_usuario = %s
        """, (token, origen, id_usuario))
        con.commit()
        cur.close()
        con.close()
    except Exception as e:
        print(f"Error al registrar inicio de sesión: {e}")

def validar_sesion_activa(id_usuario, token_actual):
    """Verifica si el token de la sesión coincide con el registrado en MySQL."""
    try:
        con = obtener_conexion()
        cur = con.cursor(dictionary=True)
        cur.execute("SELECT token_sesion FROM usuarios WHERE id_usuario = %s", (id_usuario,))
        row = cur.fetchone()
        cur.close()
        con.close()
        
        if row and row['token_sesion']:
            return row['token_sesion'] == token_actual
        return True
    except Exception as e:
        print(f"Error al validar sesión activa: {e}")
        return True

def retomar_sesion(id_usuario, nuevo_token, origen):
    """Actualiza el token en la BD para reclamar la sesión desde el dispositivo actual."""
    try:
        con = obtener_conexion()
        cur = con.cursor()
        cur.execute("""
            UPDATE usuarios 
            SET token_sesion = %s, origen_sesion = %s, ultima_actividad = NOW() 
            WHERE id_usuario = %s
        """, (nuevo_token, origen, id_usuario))
        con.commit()
        cur.close()
        con.close()
        return True
    except Exception as e:
        print(f"Error al retomar sesión: {e}")
        return False