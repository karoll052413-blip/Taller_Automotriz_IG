import os
import subprocess
import time
from datetime import datetime
from database import obtener_conexion

DIR_BACKUPS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups")
os.makedirs(DIR_BACKUPS, exist_ok=True)

class BackupService:
    @staticmethod
    def _obtener_credenciales_db():
        """Obtiene la configuración actual de conexión a MySQL."""
        con = obtener_conexion()
        config = con._host, con._user, con._password, con._database, con._port
        con.close()
        return config

    @staticmethod
    def buscar_ejecutable(nombre):
        """Busca ejecutable mysqldump/mysql en PATH o rutas comunes de XAMPP."""
        rutas_comunes = [
            r"C:\xampp\mysql\bin",
            r"C:\Program Files\MySQL\MySQL Server 8.0\bin",
            r"C:\Program Files\MySQL\MySQL Server 5.7\bin",
            r"/usr/bin",
            r"/usr/local/bin"
        ]
        for carpeta in rutas_comunes:
            ruta_exe = os.path.join(carpeta, f"{nombre}.exe" if os.name == "nt" else nombre)
            if os.path.isfile(ruta_exe):
                return ruta_exe
        return nombre

    @classmethod
    def crear_backup(cls):
        """Genera una copia de seguridad en formato .sql de la base de datos."""
        host, user, password, dbname, port = cls._obtener_credenciales_db()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre_archivo = f"backup_{dbname}_{timestamp}.sql"
        ruta_salida = os.path.join(DIR_BACKUPS, nombre_archivo)

        dump_exe = cls.buscar_ejecutable("mysqldump")
        cmd = [
            dump_exe,
            f"--host={host}",
            f"--port={port}",
            f"--user={user}",
            f"--result-file={ruta_salida}",
            "--databases", dbname,
            "--routines",
            "--triggers",
            "--add-drop-table"
        ]
        if password:
            cmd.append(f"--password={password}")

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if res.returncode == 0 and os.path.exists(ruta_salida) and os.path.getsize(ruta_salida) > 0:
                return True, nombre_archivo, ruta_salida
            return cls._crear_backup_nativo_python(ruta_salida, dbname)
        except Exception:
            return cls._crear_backup_nativo_python(ruta_salida, dbname)

    @classmethod
    def _crear_backup_nativo_python(cls, ruta_salida, dbname):
        """Fallback: Genera un volcado SQL nativo en Python."""
        try:
            con = obtener_conexion()
            cur = con.cursor()
            with open(ruta_salida, "w", encoding="utf-8") as f:
                f.write(f"-- Backup generado automáticamente para {dbname}\n")
                f.write(f"-- Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("SET FOREIGN_KEY_CHECKS=0;\n\n")

                cur.execute("SHOW TABLES")
                tablas = [t[0] for t in cur.fetchall()]

                for tabla in tablas:
                    cur.execute(f"SHOW CREATE TABLE `{tabla}`")
                    create_sql = cur.fetchone()[1]
                    f.write(f"DROP TABLE IF EXISTS `{tabla}`;\n")
                    f.write(f"{create_sql};\n\n")

                    cur.execute(f"SELECT * FROM `{tabla}`")
                    rows = cur.fetchall()
                    for row in rows:
                        valores = []
                        for val in row:
                            if val is None:
                                valores.append("NULL")
                            elif isinstance(val, (int, float)):
                                valores.append(str(val))
                            else:
                                val_str = str(val).replace("'", "''").replace("\\", "\\\\")
                                valores.append(f"'{val_str}'")
                        f.write(f"INSERT INTO `{tabla}` VALUES ({', '.join(valores)});\n")
                    f.write("\n")

                f.write("SET FOREIGN_KEY_CHECKS=1;\n")
            con.close()
            return True, os.path.basename(ruta_salida), ruta_salida
        except Exception as err:
            return False, f"Error creando backup: {str(err)}", None

    @classmethod
    def restaurar_backup(cls, ruta_archivo_sql):
        """Restaura la base de datos a partir de un archivo .sql."""
        if not os.path.isfile(ruta_archivo_sql):
            return False, "El archivo de backup especificado no existe."

        host, user, password, dbname, port = cls._obtener_credenciales_db()
        mysql_exe = cls.buscar_ejecutable("mysql")

        cmd = [
            mysql_exe,
            f"--host={host}",
            f"--port={port}",
            f"--user={user}",
            dbname
        ]
        if password:
            cmd.append(f"--password={password}")

        try:
            with open(ruta_archivo_sql, "r", encoding="utf-8", errors="ignore") as f:
                res = subprocess.run(cmd, stdin=f, capture_output=True, text=True, timeout=180)
            
            if res.returncode == 0:
                return True, "Base de datos restaurada con éxito."
            return cls._restaurar_nativo_python(ruta_archivo_sql)
        except Exception:
            return cls._restaurar_nativo_python(ruta_archivo_sql)

    @classmethod
    def _restaurar_nativo_python(cls, ruta_archivo_sql):
        """Fallback: Procesa la restauración ejecutando comandos SQL."""
        try:
            con = obtener_conexion()
            cur = con.cursor()
            cur.execute("SET FOREIGN_KEY_CHECKS=0;")
            
            with open(ruta_archivo_sql, "r", encoding="utf-8", errors="ignore") as f:
                sql_script = f.read()

            comandos = sql_script.split(";")
            for cmd in comandos:
                cmd_limpio = cmd.strip()
                if cmd_limpio and not cmd_limpio.startswith("--"):
                    try:
                        cur.execute(cmd_limpio)
                    except Exception:
                        pass
            
            cur.execute("SET FOREIGN_KEY_CHECKS=1;")
            con.commit()
            con.close()
            return True, "Base de datos restaurada correctamente."
        except Exception as err:
            return False, f"Error al restaurar: {str(err)}"

    @classmethod
    def listar_backups(cls):
        """Devuelve la lista de backups generados."""
        archivos = []
        if os.path.exists(DIR_BACKUPS):
            for f in os.listdir(DIR_BACKUPS):
                if f.endswith(".sql"):
                    ruta = os.path.join(DIR_BACKUPS, f)
                    stats = os.stat(ruta)
                    archivos.append({
                        "nombre": f,
                        "tamano": f"{stats.st_size / 1024:.1f} KB",
                        "fecha": datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                    })
        archivos.sort(key=lambda x: x["fecha"], reverse=True)
        return archivos