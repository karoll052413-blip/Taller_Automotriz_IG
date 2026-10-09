import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from functools import wraps

DIRECTORIO_RAIZ = os.path.dirname(os.path.abspath(__file__))
DIRECTORIO_PADRE = os.path.dirname(DIRECTORIO_RAIZ)
for _ruta in (DIRECTORIO_RAIZ, DIRECTORIO_PADRE):
    if _ruta not in sys.path:
        sys.path.insert(0, _ruta)

import mysql.connector
from flask import Flask, Response, abort, jsonify, request, send_file, send_from_directory, session
from werkzeug.security import safe_join

from database import obtener_conexion
from seguridad import SeguridadService, CodigoRecuperacion, MAX_INTENTOS_LOGIN, BLOQUEO_MINUTOS
from sesiones_service import registrar_inicio_sesion, validar_sesion_activa, retomar_sesion
from backup_service import BackupService  # <-- AQUÍ VA LA IMPORTACIÓN DEL SERVICIO DE BACKUP

try:
    from reportes_service import ReportesService
except ImportError:
    try:
        from servicios.reportes_service import ReportesService
    except ImportError:
        ReportesService = None

# ---------------------------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------------------------
USA_HTTPS = os.environ.get("TALLER_HTTPS") == "1"
BLOQUEO_SEG = 150            # 2.5 min sin actividad
CIERRE_SEG = 300             # 5 min sin actividad
MAX_INTENTOS_DESBLOQUEO = 3

MENSAJES_ESPECIFICOS = True
MOSTRAR_CODIGO_EN_PANTALLA = True
PLACA_RE = re.compile(r"[A-Z0-9]{5,7}")

ROLES_PWA = ("administrador", "mecanico", "cliente")
MSG_GENERICO = "Usuario o contraseña incorrectos."


def _existentes(*rutas):
    vistos, res = set(), []
    for r in rutas:
        r = os.path.normpath(r)
        if os.path.isdir(r) and r not in vistos:
            vistos.add(r)
            res.append(r)
    return res


CARPETAS_STATIC = _existentes(
    os.path.join(DIRECTORIO_RAIZ, "static"),
    os.path.join(DIRECTORIO_RAIZ, "vistas", "static"),
    os.path.join(DIRECTORIO_PADRE, "static"),
    os.path.join(DIRECTORIO_PADRE, "vistas", "static"),
)
if not CARPETAS_STATIC:
    os.makedirs(os.path.join(DIRECTORIO_RAIZ, "static"), exist_ok=True)
    CARPETAS_STATIC = [os.path.join(DIRECTORIO_RAIZ, "static")]

CARPETAS_HTML = _existentes(
    os.path.join(DIRECTORIO_RAIZ, "templates"),
    os.path.join(DIRECTORIO_RAIZ, "vistas", "templates"),
    os.path.join(DIRECTORIO_PADRE, "templates"),
    os.path.join(DIRECTORIO_PADRE, "vistas", "templates"),
    DIRECTORIO_RAIZ,
    os.path.join(DIRECTORIO_RAIZ, "vistas"),
    DIRECTORIO_PADRE,
)


def buscar_archivo(carpetas, nombre):
    for carpeta in carpetas:
        ruta = safe_join(carpeta, nombre)
        if ruta and os.path.isfile(ruta):
            return ruta
    return None


def cargar_secret_key():
    env = os.environ.get("TALLER_SECRET_KEY")
    if env:
        return env
    ruta = os.path.join(DIRECTORIO_RAIZ, ".secret_key")
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8") as f:
            return f.read().strip()
    clave = secrets.token_hex(32)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(clave)
    return clave


app = Flask(__name__, static_folder=None)
app.config.update(
    SECRET_KEY=cargar_secret_key(),
    SESSION_COOKIE_NAME="taller_sid",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=USA_HTTPS,
    PERMANENT_SESSION_LIFETIME=timedelta(seconds=CIERRE_SEG),
    MAX_CONTENT_LENGTH=64 * 1024 * 1024,
)


# ---------------------------------------------------------------------------
# UTILIDADES
# ---------------------------------------------------------------------------
@contextmanager
def conexion_db(diccionario=False):
    con = obtener_conexion()
    cur = con.cursor(dictionary=diccionario)
    try:
        yield con, cur
    finally:
        cur.close()
        con.close()


def normalizar_rol(rol):
    r = str(rol).strip().lower()
    for con, sin in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u")):
        r = r.replace(con, sin)
    return "administrador" if r in ("admin", "administrador") else r


def registrar_log(accion, usuario=None, rol=None):
    try:
        with conexion_db() as (con, cur):
            cur.execute(
                "INSERT INTO logs_sistema (usuario, rol, accion) VALUES (%s, %s, %s)",
                (usuario or session.get("nombre") or "Sistema/Anonimo", rol or session.get("rol") or "Invitado", accion),
            )
            con.commit()
    except Exception as err:
        print(f"Error registrando log: {err}")


def respuesta(ok, mensaje, codigo=200, **extra):
    return jsonify(success=ok, message=mensaje, **extra), codigo


_LIMITES = {}


def exceso_ip(clave, maximo, ventana_seg):
    llave = (clave, request.remote_addr)
    ahora = time.time()
    lista = [t for t in _LIMITES.get(llave, []) if ahora - t < ventana_seg]
    _LIMITES[llave] = lista
    return len(lista) >= maximo


def anotar_ip(clave):
    _LIMITES.setdefault((clave, request.remote_addr), []).append(time.time())


def requiere_rol(*roles):
    def deco(f):
        @wraps(f)
        def interno(*a, **k):
            if "uid" not in session:
                return respuesta(False, "Su sesión expiró. Inicie sesión de nuevo.", 401)
            if session.get("bloqueada"):
                return respuesta(False, "Pantalla bloqueada por inactividad.", 423)
            if session.get("rol") not in roles:
                registrar_log(f"Acceso denegado en la PWA a {request.path}")
                return respuesta(False, "No tiene permisos para esta acción.", 403)
            
            token_actual = session.get("session_token")
            if token_actual and not validar_sesion_activa(session["uid"], token_actual):
                session.clear()
                return respuesta(False, "El sistema está abierto en otro dispositivo.", 401)

            session["ultima"] = time.time()
            return f(*a, **k)
        return interno
    return deco


@app.before_request
def verificar_csrf():
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        enviado = request.headers.get("X-CSRF-Token", "")
        esperado = session.get("csrf", "")
        if not esperado or not hmac.compare_digest(enviado, esperado):
            return respuesta(False, "Sesión no válida. Recargue la página e intente de nuevo.", 400)


RUTAS_SIN_VIGILANCIA = ("/api/login", "/api/registro", "/api/recuperar/", "/api/verificar_sesion")
@app.before_request
def vigilar_inactividad():
    if "uid" not in session or not request.path.startswith("/api/") or request.path.startswith(RUTAS_SIN_VIGILANCIA):
        return
    inactivo = time.time() - session.get("ultima", time.time())
    if inactivo >= CIERRE_SEG:
        registrar_log("Cierre de sesión automático por inactividad de 5 minutos (PWA)")
        session.clear()
    elif inactivo >= BLOQUEO_SEG and not session.get("bloqueada"):
        session["bloqueada"] = True
        registrar_log("Pantalla bloqueada por inactividad (2.5 min) (PWA)")


@app.after_request
def cabeceras_seguridad(resp):
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; manifest-src 'self'; worker-src 'self'; form-action 'self'; "
        "base-uri 'none'; frame-ancestors 'none'"
    )
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    if request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


# ---------------------------------------------------------------------------
# ARCHIVOS E INTERFAZ PWA
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    ruta = buscar_archivo(CARPETAS_HTML, "index.html")
    if not ruta:
        abort(404)
    resp = send_file(ruta, mimetype="text/html")
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.get("/static/<path:nombre>")
def archivos_static(nombre):
    for carpeta in CARPETAS_STATIC:
        ruta = safe_join(carpeta, nombre)
        if ruta and os.path.isfile(ruta):
            return send_from_directory(carpeta, nombre)
    abort(404)


def generar_iconos():
    logo = buscar_archivo(CARPETAS_STATIC, "Logo.png")
    if not logo:
        return
    try:
        from PIL import Image
        carpeta = os.path.dirname(logo)
        for tam in (192, 512):
            destino = os.path.join(carpeta, f"icon-{tam}.png")
            if not os.path.exists(destino):
                Image.open(logo).convert("RGBA").resize((tam, tam), Image.LANCZOS).save(destino)
    except Exception as err:
        print(f"No se pudieron generar los íconos: {err}")


@app.get("/manifest.json")
def manifest():
    iconos = []
    for tam in (192, 512):
        if buscar_archivo(CARPETAS_STATIC, f"icon-{tam}.png"):
            iconos.append({"src": f"/static/icon-{tam}.png", "sizes": f"{tam}x{tam}", "type": "image/png", "purpose": "any"})
    datos = {
        "name": "Taller Automotriz I.G",
        "short_name": "Taller I.G",
        "description": "Plataforma móvil del Taller Automotriz I.G",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": "#121214",
        "theme_color": "#D32F2F",
        "lang": "es",
        "icons": iconos,
    }
    return Response(json.dumps(datos), mimetype="application/manifest+json")


SW_PLANTILLA = """
const CACHE = "taller-__VERSION__";
const PRECACHE = __ARCHIVOS__;

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE)
      .then((c) => Promise.all(PRECACHE.map((u) => c.add(u).catch(() => null))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/")) return;

  if (req.mode === "navigate") {
    e.respondWith(fetch(req).catch(() => caches.match("/")));
    return;
  }
  if (url.pathname.startsWith("/static/")) {
    e.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((res) => {
        if (res.ok) { const copia = res.clone(); caches.open(CACHE).then((c) => c.put(req, copia)); }
        return res;
      }))
    );
  }
});
"""


@app.get("/sw.js")
def service_worker():
    nombres = ["Logo.png", "fondo_oscuro.png", "fondo_claro.png", "style.css", "app.js", "icon-192.png", "icon-512.png"]
    existentes, firma = ["/"], []
    for n in nombres:
        ruta = buscar_archivo(CARPETAS_STATIC, n)
        if ruta:
            existentes.append(f"/static/{n}")
            firma.append(f"{n}:{int(os.path.getmtime(ruta))}")
    version = hashlib.md5("|".join(firma).encode()).hexdigest()[:8]
    codigo = SW_PLANTILLA.replace("__VERSION__", version).replace("__ARCHIVOS__", json.dumps(existentes))
    resp = Response(codigo, mimetype="application/javascript")
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


# ---------------------------------------------------------------------------
# API DE SESIÓN Y CONTROL DE DISPOSITIVO ÚNICO
# ---------------------------------------------------------------------------
@app.get("/api/sesion")
def api_sesion():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    session.permanent = True
    datos = {"success": True, "autenticado": "uid" in session, "csrf": session["csrf"]}
    if "uid" in session:
        datos["usuario"] = {"nombre": session["nombre"], "rol": session["rol"]}
        datos["bloqueada"] = bool(session.get("bloqueada"))
    return jsonify(datos)


@app.get("/api/verificar_sesion")
def api_verificar_sesion():
    id_usuario = session.get("uid")
    token_actual = session.get("session_token")
    
    if not id_usuario or not token_actual:
        return jsonify({"activa": False, "autenticado": False})
        
    es_valida = validar_sesion_activa(id_usuario, token_actual)
    return jsonify({"activa": es_valida, "autenticado": True})


@app.post("/api/retomar_sesion")
def api_retomar_sesion():
    id_usuario = session.get("uid")
    if not id_usuario:
        return respuesta(False, "No hay sesión activa.", 401)
    
    nuevo_token = str(uuid.uuid4())
    if retomar_sesion(id_usuario, nuevo_token, "PWA"):
        session["session_token"] = nuevo_token
        session["ultima"] = time.time()
        registrar_log("Usuario seleccionó 'Usar aquí' la sesión en la PWA Web")
        return respuesta(True, "Sesión retomada correctamente en la PWA.")
    return respuesta(False, "No se pudo retomar la sesión.", 500)


@app.post("/api/login")
def api_login():
    datos = request.get_json(silent=True) or {}

    if str(datos.get("sitio_web", "")).strip():
        registrar_log("Posible bot detectado (honeypot) en el login de la PWA", usuario="Anónimo", rol="Invitado")
        return respuesta(False, MSG_GENERICO, 401)

    if exceso_ip("login_fallos", 15, 300):
        return respuesta(False, "Demasiados intentos desde este equipo. Espere 5 minutos.", 429)

    usr = str(datos.get("usuario", "")).strip()[:50]
    pas = str(datos.get("password", ""))
    if not usr or not pas:
        return respuesta(False, "Ingrese usuario y contraseña.", 400)
    if len(pas) > 128:
        anotar_ip("login_fallos")
        return respuesta(False, MSG_GENERICO, 401)

    resultado, user, restantes = "fallo", None, 0
    try:
        with conexion_db(True) as (con, cur):
            cur.execute(
                """SELECT id_usuario, nombre_completo, rol, password_hash, estado, intentos_fallidos,
                          (bloqueado_hasta IS NOT NULL AND bloqueado_hasta > NOW()) AS bloqueado
                   FROM usuarios WHERE usuario = %s""", (usr,))
            user = cur.fetchone()

            if not user:
                resultado = "sin_usuario"
                SeguridadService.hashear("dummy")
            elif user["bloqueado"]:
                resultado = "bloqueado"
            elif not SeguridadService.verificar(pas, user["password_hash"]):
                resultado = "fallo"
                n = (user["intentos_fallidos"] or 0) + 1
                if n >= MAX_INTENTOS_LOGIN:
                    cur.execute(
                        "UPDATE usuarios SET intentos_fallidos = 0, bloqueado_hasta = NOW() + INTERVAL %s MINUTE WHERE id_usuario = %s",
                        (BLOQUEO_MINUTOS, user["id_usuario"]))
                    resultado = "fallo_bloqueo"
                else:
                    cur.execute("UPDATE usuarios SET intentos_fallidos = %s WHERE id_usuario = %s", (n, user["id_usuario"]))
                    restantes = MAX_INTENTOS_LOGIN - n
                con.commit()
            elif user["estado"] != "Activo":
                resultado = "inactivo"
            else:
                resultado = "ok"
                if SeguridadService.es_legacy(user["password_hash"]) and len(pas.encode("utf-8")) <= 72:
                    cur.execute("UPDATE usuarios SET password_hash = %s WHERE id_usuario = %s",
                                (SeguridadService.hashear(pas), user["id_usuario"]))
                cur.execute("UPDATE usuarios SET intentos_fallidos = 0, bloqueado_hasta = NULL WHERE id_usuario = %s",
                            (user["id_usuario"],))
                con.commit()
    except mysql.connector.Error:
        app.logger.exception("Error de base de datos en el login")
        return respuesta(False, "No se pudo conectar con la base de datos.", 500)

    if resultado == "bloqueado":
        registrar_log(f"Intento de acceso a cuenta bloqueada (PWA): {usr}", usuario=usr, rol="Invitado")
        return respuesta(False, f"Demasiados intentos fallidos. Intente de nuevo en {BLOQUEO_MINUTOS} minutos.", 403)

    if resultado == "sin_usuario":
        anotar_ip("login_fallos")
        registrar_log(f"Intento de login en la PWA con usuario inexistente '{usr}'", usuario=usr, rol="Invitado")
        if MENSAJES_ESPECIFICOS:
            return respuesta(False, "El usuario no está registrado.", 401, campo="usuario")
        return respuesta(False, MSG_GENERICO, 401)

    if resultado in ("fallo", "fallo_bloqueo"):
        anotar_ip("login_fallos")
        registrar_log(f"Intento de login fallido en la PWA para '{usr}'", usuario=usr, rol="Invitado")
        if resultado == "fallo_bloqueo":
            registrar_log(f"Cuenta '{usr}' bloqueada por {BLOQUEO_MINUTOS} min (intentos fallidos, PWA)", usuario=usr, rol="Invitado")
            return respuesta(False, f"Demasiados intentos fallidos. Cuenta bloqueada por {BLOQUEO_MINUTOS} minutos.", 403)
        if MENSAJES_ESPECIFICOS:
            plural = "intento" if restantes == 1 else "intentos"
            return respuesta(False, f"Contraseña incorrecta. Le quedan {restantes} {plural} antes del bloqueo.", 401, campo="password")
        return respuesta(False, MSG_GENERICO, 401)

    if resultado == "inactivo":
        return respuesta(False, "Esta cuenta ha sido desactivada por la administración.", 403)

    rol = normalizar_rol(user["rol"])
    if rol not in ROLES_PWA:
        registrar_log(f"Acceso a la PWA rechazado por rol ({user['rol']})", usuario=user["nombre_completo"], rol=user["rol"])
        return respuesta(False, "Su rol no tiene permisos para acceder a la PWA.", 403)

    nuevo_token = str(uuid.uuid4())
    registrar_inicio_sesion(user["id_usuario"], nuevo_token, "PWA")

    session.clear()
    session.permanent = True
    session["uid"] = user["id_usuario"]
    session["nombre"] = user["nombre_completo"]
    session["rol"] = rol
    session["session_token"] = nuevo_token
    session["csrf"] = secrets.token_hex(16)
    session["ultima"] = time.time()
    
    registrar_log("Inicio de sesión exitoso (PWA)")
    return jsonify(success=True, csrf=session["csrf"], usuario={"nombre": session["nombre"], "rol": rol})


@app.post("/api/logout")
def api_logout():
    if "uid" in session:
        registrar_log("Cerró la sesión (PWA)")
    session.clear()
    return respuesta(True, "Sesión cerrada.")


@app.post("/api/actividad")
def api_actividad():
    if "uid" not in session:
        return respuesta(False, "Su sesión expiró. Inicie sesión de nuevo.", 401)
    if session.get("bloqueada"):
        return respuesta(False, "Pantalla bloqueada por inactividad.", 423)
    session["ultima"] = time.time()
    return respuesta(True, "ok")


@app.post("/api/bloquear")
def api_bloquear():
    if "uid" not in session:
        return respuesta(False, "Su sesión expiró. Inicie sesión de nuevo.", 401)
    if not session.get("bloqueada"):
        session["bloqueada"] = True
        registrar_log("Pantalla bloqueada por inactividad (2.5 min) (PWA)")
    return respuesta(True, "Pantalla bloqueada.")


@app.post("/api/desbloquear")
def api_desbloquear():
    if "uid" not in session:
        return respuesta(False, "Su sesión expiró. Inicie sesión de nuevo.", 401)
    pas = str(request.get_json(silent=True, force=True).get("password", "")) if request.data else ""
    correcto = False
    if pas and len(pas) <= 128:
        try:
            with conexion_db(True) as (con, cur):
                cur.execute("SELECT password_hash FROM usuarios WHERE id_usuario = %s", (session["uid"],))
                u = cur.fetchone()
            correcto = bool(u and SeguridadService.verificar(pas, u["password_hash"]))
        except mysql.connector.Error:
            app.logger.exception("Error al desbloquear")
            return respuesta(False, "No se pudo verificar la contraseña.", 500)

    if correcto:
        session["bloqueada"] = False
        session["intentos_desbloqueo"] = 0
        session["ultima"] = time.time()
        registrar_log("Sesión desbloqueada (PWA)")
        return respuesta(True, "Sesión desbloqueada.")

    n = session.get("intentos_desbloqueo", 0) + 1
    session["intentos_desbloqueo"] = n
    if n >= MAX_INTENTOS_DESBLOQUEO:
        registrar_log("Cierre de sesión: demasiados intentos fallidos al desbloquear (PWA)")
        session.clear()
        return respuesta(False, "Demasiados intentos. Se cerró la sesión por seguridad.", 401)
    return respuesta(False, f"Contraseña incorrecta. Intentos restantes: {MAX_INTENTOS_DESBLOQUEO - n}.", 403, campo="password")


# ---------------------------------------------------------------------------
# REGISTRO Y RECUPERACIÓN DE CLIENTES
# ---------------------------------------------------------------------------
@app.post("/api/registro")
def api_registro():
    d = request.get_json(silent=True) or {}
    if str(d.get("sitio_web", "")).strip():
        registrar_log("Posible bot detectado (honeypot) en el registro de la PWA", usuario="Anónimo", rol="Invitado")
        return respuesta(False, "No se pudo completar el registro.", 400)
    if exceso_ip("registro", 10, 3600):
        return respuesta(False, "Demasiados registros desde este equipo. Intente más tarde.", 429)

    nombre = str(d.get("nombre", "")).strip()[:100]
    usuario = str(d.get("usuario", "")).strip()
    correo = str(d.get("correo", "")).strip()[:100]
    telefono = str(d.get("telefono", "")).strip()
    pass1, pass2 = str(d.get("password", "")), str(d.get("password2", ""))

    errores = []
    if len(nombre) < 3:
        errores.append("• Ingrese el nombre completo.")
    if not SeguridadService.validar_usuario(usuario):
        errores.append("• El usuario debe tener 4 a 30 caracteres (letras, números, punto, guion o guion bajo).")
    if not SeguridadService.validar_correo(correo):
        errores.append("• El correo electrónico no es válido.")
    if not SeguridadService.validar_telefono(telefono):
        errores.append("• El teléfono debe tener exactamente 10 dígitos.")
    errores += SeguridadService.validar_password(pass1)
    if pass1 != pass2:
        errores.append("• Las contraseñas no coinciden.")
    if d.get("acepta_politica") is not True:
        errores.append("• Debe aceptar la Política de Tratamiento de Datos Personales.")
    if errores:
        return respuesta(False, "\n".join(errores), 400)

    anotar_ip("registro")
    try:
        with conexion_db() as (con, cur):
            cur.execute(
                "INSERT INTO usuarios (nombre_completo, usuario, correo, telefono, password_hash, rol, estado) "
                "VALUES (%s, %s, %s, %s, %s, 'Cliente', 'Activo')",
                (nombre, usuario, correo, telefono, SeguridadService.hashear(pass1)))
            con.commit()
        registrar_log("Nuevo cliente registrado desde la PWA", usuario=usuario, rol="Cliente")
        return respuesta(True, f"¡Cuenta creada correctamente! Inicie sesión con el usuario: {usuario}")
    except mysql.connector.IntegrityError:
        return respuesta(False, "Ese nombre de usuario ya está en uso. Elija otro.", 409)
    except mysql.connector.Error:
        app.logger.exception("Error en el registro")
        return respuesta(False, "No se pudo crear la cuenta.", 500)


_RECUPERACIONES = {}


@app.post("/api/recuperar/solicitar")
def api_recuperar_solicitar():
    if exceso_ip("recuperar", 10, 3600):
        return respuesta(False, "Demasiadas solicitudes desde este equipo. Intente más tarde.", 429)
    d = request.get_json(silent=True) or {}
    usr, tel = str(d.get("usuario", "")).strip()[:50], str(d.get("telefono", "")).strip()[:20]
    if not usr or not tel:
        return respuesta(False, "Ingrese usuario y teléfono.", 400)
    anotar_ip("recuperar")
    try:
        with conexion_db(True) as (con, cur):
            cur.execute("SELECT id_usuario FROM usuarios WHERE usuario = %s AND telefono = %s AND estado = 'Activo'", (usr, tel))
            u = cur.fetchone()
    except mysql.connector.Error:
        app.logger.exception("Error en la recuperación")
        return respuesta(False, "No se pudo procesar la solicitud.", 500)

    registrar_log(f"Solicitud de recuperación de contraseña (PWA) para '{usr}'", usuario=usr, rol="Invitado")
    if not u:
        return respuesta(False, "Los datos no coinciden.", 404)

    for k in [k for k, v in _RECUPERACIONES.items() if time.time() - v.creado > 600]:
        _RECUPERACIONES.pop(k, None)
    token = secrets.token_hex(16)
    cr = CodigoRecuperacion(u["id_usuario"])
    _RECUPERACIONES[token] = cr
    session["rec_token"] = token
    extra = {"codigo": cr.codigo} if MOSTRAR_CODIGO_EN_PANTALLA else {}
    return respuesta(True, "Código generado. Vence en 5 minutos.", **extra)


@app.post("/api/recuperar/confirmar")
def api_recuperar_confirmar():
    token = session.get("rec_token")
    cr = _RECUPERACIONES.get(token) if token else None
    if not cr:
        return respuesta(False, "Primero genere un código de verificación.", 400)

    d = request.get_json(silent=True) or {}
    nueva = str(d.get("password", ""))
    errores = SeguridadService.validar_password(nueva)
    if errores:
        return respuesta(False, "\n".join(errores), 400)

    estado = cr.verificar(str(d.get("codigo", "")))
    if estado == "expirado":
        _RECUPERACIONES.pop(token, None)
        return respuesta(False, "El código expiró. Genere uno nuevo.", 400)
    if estado == "agotado":
        _RECUPERACIONES.pop(token, None)
        return respuesta(False, "Demasiados intentos. Genere un código nuevo.", 400)
    if estado == "incorrecto":
        return respuesta(False, "Código incorrecto.", 400)

    try:
        with conexion_db() as (con, cur):
            cur.execute("UPDATE usuarios SET password_hash = %s, intentos_fallidos = 0, bloqueado_hasta = NULL WHERE id_usuario = %s",
                        (SeguridadService.hashear(nueva), cr.id_usuario))
            con.commit()
        _RECUPERACIONES.pop(token, None)
        session.pop("rec_token", None)
        registrar_log(f"Contraseña restablecida desde la PWA (usuario #{cr.id_usuario})", usuario=f"#{cr.id_usuario}", rol="Invitado")
        return respuesta(True, "Contraseña cambiada correctamente. Ya puede iniciar sesión.")
    except mysql.connector.Error:
        app.logger.exception("Error actualizando la contraseña")
        return respuesta(False, "No se pudo cambiar la contraseña.", 500)


# ---------------------------------------------------------------------------
# DATOS DE NEGOCIO Y DASHBOARD
# ---------------------------------------------------------------------------
@app.get("/api/dashboard")
@requiere_rol(*ROLES_PWA)
def api_dashboard():
    uid, rol = session["uid"], session["rol"]
    try:
        with conexion_db(True) as (con, cur):
            if rol == "mecanico":
                cur.execute(
                    "SELECT COUNT(*) AS n, COALESCE(SUM(costo), 0) AS total FROM mantenimientos "
                    "WHERE id_mecanico = %s AND DATE(fecha_mantenimiento) = CURDATE()", (uid,))
                r = cur.fetchone()
                return jsonify(success=True, rol=rol, trabajos_hoy=int(r["n"]), total_hoy=float(r["total"]))

            if rol == "administrador":
                cur.execute("SELECT COUNT(*) AS n FROM vehiculos")
                v_total = cur.fetchone()["n"]
                cur.execute("SELECT COUNT(*) AS n FROM mantenimientos WHERE DATE(fecha_mantenimiento) = CURDATE()")
                m_hoy = cur.fetchone()["n"]
                return jsonify(success=True, rol=rol, trabajos_hoy=int(m_hoy), total_hoy=int(v_total), vehiculos=[])

            cur.execute("SELECT placa, marca, color, modelo FROM vehiculos WHERE id_cliente = %s ORDER BY id_vehiculo DESC", (uid,))
            vehiculos = cur.fetchall()
            citas = 0
            try:
                cur.execute("SELECT COUNT(*) AS n FROM citas WHERE id_cliente = %s AND estado IN ('Pendiente', 'Confirmada')", (uid,))
                citas = int(cur.fetchone()["n"])
            except mysql.connector.Error:
                app.logger.warning("No se pudo leer la tabla citas")
            return jsonify(success=True, rol=rol, vehiculos=vehiculos, citas_activas=citas)
    except mysql.connector.Error:
        app.logger.exception("Error en el dashboard")
        return respuesta(False, "No se pudieron cargar los datos.", 500)


@app.get("/api/vehiculo/<placa>")
@requiere_rol(*ROLES_PWA)
def api_vehiculo(placa):
    placa = placa.strip().upper()
    if not PLACA_RE.fullmatch(placa):
        return respuesta(False, "Placa inválida.", 400)
    uid, rol = session["uid"], session["rol"]
    try:
        with conexion_db(True) as (con, cur):
            sql = ("SELECT v.id_vehiculo, v.placa, v.marca, v.color, v.modelo, u.nombre_completo AS propietario, "
                   "u.telefono AS telefono FROM vehiculos v LEFT JOIN usuarios u ON v.id_cliente = u.id_usuario WHERE v.placa = %s")
            params = [placa]
            if rol == "cliente":
                sql += " AND v.id_cliente = %s"
                params.append(uid)
            cur.execute(sql, params)
            v = cur.fetchone()
            if not v:
                msg = "No se encontró un vehículo suyo con esa placa." if rol == "cliente" else "No se encontró ningún vehículo con esa placa."
                return respuesta(False, msg, 404)

            cur.execute(
                "SELECT COALESCE(m.fecha_mantenimiento, m.fecha_registro) AS fecha, u.nombre_completo AS mecanico, "
                "m.descripcion_trabajo, m.observaciones, m.costo FROM mantenimientos m "
                "LEFT JOIN usuarios u ON m.id_mecanico = u.id_usuario WHERE m.id_vehiculo = %s ORDER BY fecha DESC",
                (v["id_vehiculo"],))
            historial = [
                {"fecha": str(h["fecha"]).split(" ")[0], "mecanico": h["mecanico"] or "Taller General",
                 "descripcion": h["descripcion_trabajo"], "observaciones": h["observaciones"] or "",
                 "costo": float(h["costo"] or 0)}
                for h in cur.fetchall()
            ]
        vehiculo = {"placa": v["placa"], "marca": v["marca"], "color": v["color"], "modelo": v["modelo"]}
        if rol in ("mecanico", "administrador"):
            vehiculo["propietario"] = v["propietario"] or "Sin asignación directa"
            vehiculo["telefono"] = v["telefono"] or "N/A"
        registrar_log(f"Consultó el vehículo placa {placa} (PWA)")
        return jsonify(success=True, vehiculo=vehiculo, historial=historial)
    except mysql.connector.Error:
        app.logger.exception("Error consultando vehículo")
        return respuesta(False, "No se pudo consultar el vehículo.", 500)


@app.get("/api/clientes")
@requiere_rol("mecanico", "administrador")
def api_clientes():
    try:
        with conexion_db(True) as (con, cur):
            cur.execute("SELECT id_usuario, nombre_completo, usuario FROM usuarios WHERE LOWER(rol) = 'cliente' AND estado = 'Activo' ORDER BY nombre_completo")
            filas = cur.fetchall()
        return jsonify(success=True, clientes=[{"id": f["id_usuario"], "etiqueta": f"{f['nombre_completo']} ({f['usuario']})"} for f in filas])
    except mysql.connector.Error:
        app.logger.exception("Error listando clientes")
        return respuesta(False, "No se pudo cargar la lista de clientes.", 500)


@app.post("/api/vehiculos")
@requiere_rol(*ROLES_PWA)
def api_registrar_vehiculo():
    d = request.get_json(silent=True) or {}
    placa = str(d.get("placa", "")).strip().upper()
    marca = str(d.get("marca", "")).strip()[:100]
    color = str(d.get("color", "")).strip()[:30]
    modelo_txt = str(d.get("modelo", "")).strip()

    if not PLACA_RE.fullmatch(placa):
        return respuesta(False, "La placa debe tener entre 5 y 7 letras o números (Ej. ABC123).", 400)
    if not marca:
        return respuesta(False, "La marca es obligatoria.", 400)
    modelo = None
    if modelo_txt:
        if not (modelo_txt.isdigit() and 1950 <= int(modelo_txt) <= datetime.now().year + 1):
            return respuesta(False, "Ingrese un año válido (Ej. 2020).", 400)
        modelo = int(modelo_txt)

    id_cliente = session["uid"] if session["rol"] == "cliente" else None
    try:
        with conexion_db(True) as (con, cur):
            if session["rol"] in ("mecanico", "administrador") and str(d.get("id_cliente", "")).strip():
                cur.execute("SELECT id_usuario FROM usuarios WHERE id_usuario = %s AND LOWER(rol) = 'cliente'", (str(d["id_cliente"]),))
                fila = cur.fetchone()
                if not fila:
                    return respuesta(False, "El propietario seleccionado no es válido.", 400)
                id_cliente = fila["id_usuario"]
            cur.execute("INSERT INTO vehiculos (id_cliente, placa, marca, color, modelo) VALUES (%s, %s, %s, %s, %s)",
                        (id_cliente, placa, marca, color or None, modelo))
            con.commit()
        registrar_log(f"Registró el vehículo placa {placa} ({marca}) (PWA)")
        return respuesta(True, f"Vehículo {placa} registrado correctamente.")
    except mysql.connector.IntegrityError:
        return respuesta(False, "Esa placa ya está registrada en el sistema.", 409)
    except mysql.connector.Error:
        app.logger.exception("Error registrando vehículo")
        return respuesta(False, "No se pudo registrar el vehículo.", 500)


@app.post("/api/citas")
@requiere_rol("cliente")
def api_crear_cita():
    d = request.get_json(silent=True) or {}
    placa = str(d.get("placa", "")).strip().upper()
    motivo = str(d.get("motivo", "")).strip()[:255]
    if not PLACA_RE.fullmatch(placa):
        return respuesta(False, "Seleccione la placa de su vehículo.", 400)
    if not motivo:
        return respuesta(False, "Escriba el motivo de la revisión.", 400)
    try:
        fecha = datetime.strptime(str(d.get("fecha", "")).strip(), "%Y-%m-%d").date()
    except ValueError:
        return respuesta(False, "Seleccione una fecha válida.", 400)
    if fecha < datetime.now().date():
        return respuesta(False, "La fecha no puede ser anterior a hoy.", 400)

    try:
        with conexion_db(True) as (con, cur):
            cur.execute("SELECT id_vehiculo FROM vehiculos WHERE placa = %s AND id_cliente = %s", (placa, session["uid"]))
            if not cur.fetchone():
                return respuesta(False, "Esa placa no está registrada a su nombre.", 404)
            cur.execute("INSERT INTO citas (id_cliente, placa, fecha_cita, motivo) VALUES (%s, %s, %s, %s)",
                        (session["uid"], placa, fecha.strftime("%Y-%m-%d"), motivo))
            con.commit()
        registrar_log(f"Solicitó cita técnica para vehículo placa {placa} en la fecha {fecha.strftime('%d/%m/%Y')} (PWA)")
        return respuesta(True, f"Su cita para la placa {placa} el día {fecha.strftime('%d/%m/%Y')} quedó registrada.")
    except mysql.connector.Error:
        app.logger.exception("Error registrando cita")
        return respuesta(False, "No se pudo registrar la cita.", 500)


@app.post("/api/cierre-caja")
@requiere_rol("mecanico", "administrador")
def api_cierre_caja():
    try:
        with conexion_db(True) as (con, cur):
            cur.execute(
                "SELECT COUNT(*) AS n, COALESCE(SUM(costo), 0) AS total FROM mantenimientos "
                "WHERE id_mecanico = %s AND DATE(fecha_mantenimiento) = CURDATE()", (session["uid"],))
            r = cur.fetchone()
        n, total = int(r["n"]), float(r["total"])
        registrar_log(f"Realizó el Cierre de Caja Diario (${total:,.0f} COP, {n} trabajos) (PWA)")
        return jsonify(success=True, trabajos=n, total=total)
    except mysql.connector.Error:
        app.logger.exception("Error en el cierre de caja")
        return respuesta(False, "No se pudo realizar el cierre de caja.", 500)


# ---------------------------------------------------------------------------
# API DE BACKUP Y RESTAURACIÓN (ADMINISTRADOR)
# ---------------------------------------------------------------------------
@app.get("/api/admin/backups")
@requiere_rol("administrador")
def api_listar_backups():
    backups = BackupService.listar_backups()
    return jsonify(success=True, backups=backups)


@app.post("/api/admin/backup/crear")
@requiere_rol("administrador")
def api_crear_backup():
    ok, nombre_o_err, ruta = BackupService.crear_backup()
    if ok:
        registrar_log(f"Creó copia de seguridad de la base de datos: {nombre_o_err} (PWA)")
        return respuesta(True, f"Copia de seguridad creada correctamente: {nombre_o_err}")
    return respuesta(False, f"No se pudo crear la copia de seguridad: {nombre_o_err}", 500)


@app.post("/api/admin/backup/restaurar")
@requiere_rol("administrador")
def api_restaurar_backup():
    datos = request.get_json(silent=True) or {}
    nombre = str(datos.get("nombre", "")).strip()
    if not nombre:
        return respuesta(False, "Seleccione un archivo de backup para restaurar.", 400)

    from backup_service import DIR_BACKUPS
    ruta = os.path.join(DIR_BACKUPS, nombre)
    ok, msg = BackupService.restaurar_backup(ruta)
    if ok:
        registrar_log(f"Restauró la base de datos desde la copia: {nombre} (PWA)")
        return respuesta(True, msg)
    return respuesta(False, msg, 500)


# ---------------------------------------------------------------------------
# REPORTES (EXCEL Y PDF)
# ---------------------------------------------------------------------------
COLUMNAS_REPORTE = ["Placa", "Trabajo Realizado", "Observaciones", "Costo ($ COP)", "Fecha"]


def _generar_archivo(funcion, titulo, datos, sufijo):
    fd, ruta = tempfile.mkstemp(suffix=sufijo)
    os.close(fd)
    try:
        funcion(titulo, COLUMNAS_REPORTE, datos, ruta)
        with open(ruta, "rb") as f:
            return io.BytesIO(f.read())
    finally:
        try:
            os.remove(ruta)
        except OSError:
            pass


@app.get("/api/exportar/<formato>")
@requiere_rol(*ROLES_PWA)
def api_exportar(formato):
    if formato not in ("excel", "pdf"):
        return respuesta(False, "Formato no válido.", 400)
    if ReportesService is None:
        return respuesta(False, "El módulo de reportes no está disponible en el servidor.", 501)

    uid, rol = session["uid"], session["rol"]
    base = ("SELECT v.placa, m.descripcion_trabajo, m.observaciones, m.costo, "
            "COALESCE(m.fecha_mantenimiento, m.fecha_registro) AS fecha FROM mantenimientos m "
            "INNER JOIN vehiculos v ON m.id_vehiculo = v.id_vehiculo WHERE ")
    if formato == "pdf":
        placa = request.args.get("placa", "").strip().upper()
        if placa:
            if not PLACA_RE.fullmatch(placa):
                return respuesta(False, "Ingrese una placa válida.", 400)
            sql, params = base + "v.placa = %s", [placa]
            if rol == "cliente":
                sql += " AND v.id_cliente = %s"
                params.append(uid)
            titulo, nombre = f"Hoja de vida del vehículo {placa}", f"Hoja_de_vida_{placa}.pdf"
        elif rol == "cliente":
            sql, params = base + "v.id_cliente = %s", [uid]
            titulo, nombre = "Certificado de mantenimientos", "Certificado_Mantenimientos.pdf"
        else:
            return respuesta(False, "Ingrese una placa válida.", 400)
        sufijo, funcion, mime = ".pdf", ReportesService.exportar_pdf, "application/pdf"
        log = f"Descargó '{titulo}' (PDF) (PWA)"
    else:
        if rol in ("mecanico", "administrador"):
            sql, params = base + "m.id_mecanico = %s AND DATE(m.fecha_mantenimiento) = CURDATE()", [uid]
            titulo, nombre = "Cierre de caja diario", "Cierre_diario.xlsx"
        else:
            sql, params = base + "v.id_cliente = %s", [uid]
            titulo, nombre = "Control financiero de gastos", "Control_de_Gastos.xlsx"
        sufijo, funcion = ".xlsx", ReportesService.exportar_excel
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        log = f"Descargó el reporte Excel '{titulo}' (PWA)"
    sql += " ORDER BY fecha DESC"

    try:
        with conexion_db(True) as (con, cur):
            cur.execute(sql, params)
            filas = cur.fetchall()
        if not filas:
            return respuesta(False, "No hay mantenimientos registrados para exportar.", 404)
        datos = [[m["placa"], m["descripcion_trabajo"], m["observaciones"] or "Sin observaciones",
                  f"${float(m['costo'] or 0):,.0f}", str(m["fecha"])] for m in filas]
        if formato == "excel" and rol == "cliente":
            total = sum(float(m["costo"] or 0) for m in filas)
            datos.append(["", "TOTAL INVERTIDO", "", f"${total:,.0f}", ""])
        contenido = _generar_archivo(funcion, titulo, datos, sufijo)
        registrar_log(log)
        return send_file(contenido, as_attachment=True, download_name=nombre, mimetype=mime)
    except mysql.connector.Error:
        app.logger.exception("Error consultando datos del reporte")
        return respuesta(False, "No se pudieron consultar los datos del reporte.", 500)
    except Exception:
        app.logger.exception("Error generando el reporte")
        return respuesta(False, "No se pudo generar el reporte.", 500)


# ---------------------------------------------------------------------------
# ARRANQUE
# ---------------------------------------------------------------------------
generar_iconos()


def diagnostico():
    print("=" * 62)
    print("  DIAGNÓSTICO DE ARCHIVOS DE LA PWA")
    for carpetas, archivos in (
        (CARPETAS_STATIC, ["Logo.png", "fondo_oscuro.png", "fondo_claro.png", "style.css", "app.js"]),
        (CARPETAS_HTML, ["index.html"]),
    ):
        for a in archivos:
            ruta = buscar_archivo(carpetas, a)
            print(f"  [{'OK' if ruta else 'FALTA'}] {a}" + (f"  ->  {ruta}" if ruta else ""))
    print(f"  [{'OK' if ReportesService else 'AVISO'}] módulo de reportes")
    print("=" * 62)


if __name__ == "__main__":
    diagnostico()
    host = os.environ.get("TALLER_HOST", "127.0.0.1")
    esquema = "https" if USA_HTTPS else "http"
    print(f"  PWA activa en {esquema}://localhost:5000   (Ctrl+C para detener)")
    app.run(host=host, port=5000, debug=False, ssl_context="adhoc" if USA_HTTPS else None)