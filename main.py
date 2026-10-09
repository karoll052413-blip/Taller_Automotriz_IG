import os
import re
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime

import customtkinter as ctk
import mysql.connector
from PIL import Image, ImageDraw
from tkinter import messagebox

# IMPORTS DESDE NUESTROS MÓDULOS PROPIOS
from database import obtener_conexion
from seguridad import SeguridadService, CodigoRecuperacion, MAX_INTENTOS_LOGIN, BLOQUEO_MINUTOS
from sesiones_service import registrar_inicio_sesion, validar_sesion_activa, retomar_sesion
from vistas.admin_view import VistaAdministrador
from vistas.mecanico_view import VistaMecanico
from vistas.cliente_view import VistaCliente
from vistas.base_view import normalizar_rol

ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("dark-blue")

# ---------------------------------------------------------------------------
# CONSTANTES
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CARPETAS_RECURSOS = (os.path.join(BASE_DIR, "assets"), BASE_DIR)

TIEMPO_BLOQUEO_SEG = 150        # 2.5 min: bloqueo con clave
TIEMPO_EXPIRACION_SEG = 300     # 5 min: cierre de sesión forzado
MAX_INTENTOS_DESBLOQUEO = 3

MOSTRAR_CODIGO_EN_PANTALLA = True

ROJO = "#D32F2F"
ROJO_H = "#B71C1C"
CARD_BG = ("#FFFFFF", "#1E1E22")
CARD_BORDE = ("#E5E7EB", "#2A2D34")
TXT_T = ("#111827", "#F9FAFB")
TXT_S = ("#4B5563", "#9CA3AF")
BTN_GRIS = ("#E5E7EB", "#2A2D34")
BTN_GRIS_H = ("#D1D5DB", "#374151")


def buscar_recurso(*nombres):
    """Busca el archivo en assets/ y luego en la carpeta del proyecto."""
    for carpeta in CARPETAS_RECURSOS:
        for n in nombres:
            ruta = os.path.join(carpeta, n)
            if os.path.exists(ruta):
                return ruta
    return None


@contextmanager
def conexion_db(dictionary=False):
    """Abre conexión + cursor y los cierra siempre, aunque ocurra un error."""
    con = obtener_conexion()
    cur = con.cursor(dictionary=dictionary)
    try:
        yield con, cur
    finally:
        cur.close()
        con.close()


class AppTallerAutomotriz(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("TALLER AUTOMOTRIZ I.G - Software de Gestión")
        self.after(0, lambda: self.wm_state('zoomed'))

        # RUTAS RELATIVAS (assets/ o carpeta del proyecto)
        self.ruta_fondo_claro = buscar_recurso("fondo.png", "fondo.jpg")
        self.ruta_fondo_oscuro = buscar_recurso(
            "fondo_oscuro.png", "fondo Oscuro.png", "fondo_oscuro.jpg", "fondo Oscuro.jpg",
            "fondo_pantalla.png", "fondo pantalla.png"
        ) or self.ruta_fondo_claro
        self.ruta_logo = buscar_recurso("Logo.png", "Logo_Taller_Automotriz.png")
        self._cache_fondos = {}

        # VARIABLES DE SESIÓN Y CONTROL (SESIÓN ÚNICA)
        self.usuario_actual = ""
        self.rol_actual = ""
        self.id_usuario_actual = None
        self.token_sesion_actual = None

        # TEMPORIZADORES DE SEGURIDAD
        self.ultimo_actividad = time.time()
        self.bloqueo_pantalla_activo = False
        self.win_unlock_ref = None
        self.win_duplicado_ref = None
        self.ventanas_flotantes = []

        self.frame_login = None
        self.frame_registro = None
        self.frame_inicio = None
        self.body_scroll = None
        self.btn_menu_activos = {}
        self.btn_registrar_container = None

        # REGISTRO GLOBAL DE EVENTOS DE INTERACCIÓN
        self.bind_all("<Any-KeyPress>", self.detectar_actividad_usuario)
        self.bind_all("<Any-ButtonPress>", self.detectar_actividad_usuario)
        self.bind_all("<Motion>", self.detectar_actividad_usuario)

        # IMAGEN DE FONDO GLOBAL
        self.lbl_bg = ctk.CTkLabel(self, text="")
        self.lbl_bg.place(x=0, y=0, relwidth=1, relheight=1)
        self.lbl_bg.lower()

        # CONTENEDOR CENTRAL (LOGIN Y REGISTRO)
        self.card_main = ctk.CTkFrame(
            self, width=1050, height=640, corner_radius=22,
            fg_color=("#FFFFFF", "#121214"), border_width=1, border_color=("#D1D5DB", "#2A2D34")
        )
        self.card_main.place(relx=0.5, rely=0.47, anchor="center")
        self.card_main.pack_propagate(False)

        # BOTÓN Y FOOTER FLOTANTES
        self.btn_theme_login = ctk.CTkButton(
            self, text="☀️ / 🌙", width=80, height=38, corner_radius=10,
            fg_color=("#E5E7EB", "#2A2D34"), text_color=("#111827", "#F9FAFB"),
            hover_color=("#D1D5DB", "#374151"), font=("Segoe UI Emoji", 15, "bold"),
            command=self.cambiar_tema
        )
        self.btn_theme_login.place(relx=0.03, rely=0.96, anchor="w")

        self.footer = ctk.CTkFrame(
            self, fg_color=("#FFFFFF", "#1E1E1E"), corner_radius=10, border_width=1,
            border_color=("#D1D5DB", "#2A2D34")
        )
        ctk.CTkLabel(
            self.footer, text="⚙️ TALLER AUTOMOTRIZ I.G - SOFTWARE DE GESTIÓN",
            font=("Calibri", 15, "bold"), text_color=ROJO
        ).pack(padx=24, pady=8)
        self.footer.place(relx=0.5, rely=0.96, anchor="center")

        self.actualizar_visibilidad_fondo()
        self.mostrar_login()
        self.verificar_tiempos_inactividad_loop()
        self.verificar_sesion_activa_loop()

    # =========================================================================
    # INACTIVIDAD Y CONTROL DE SESIÓN ÚNICA
    # =========================================================================
    def detectar_actividad_usuario(self, event=None):
        if self.id_usuario_actual and self.frame_inicio and not self.bloqueo_pantalla_activo:
            self.ultimo_actividad = time.time()

    def verificar_tiempos_inactividad_loop(self):
        self.after(5000, self.verificar_tiempos_inactividad_loop)

        if not (self.id_usuario_actual and self.frame_inicio):
            return

        inactivo = time.time() - self.ultimo_actividad

        if inactivo >= TIEMPO_EXPIRACION_SEG:
            self.registrar_log("Cierre de sesión automático por inactividad de 5 minutos")
            self.cerrar_sesion_forzado()
            messagebox.showwarning(
                "Sesión Expirada ⏱",
                "Su sesión se ha cerrado automáticamente por superar los 5 minutos de inactividad."
            )

        elif inactivo >= TIEMPO_BLOQUEO_SEG and not self.bloqueo_pantalla_activo:
            self.bloqueo_pantalla_activo = True
            self.ultimo_actividad = time.time()
            self.registrar_log("Pantalla bloqueada por inactividad (2.5 min)")
            self.solicitar_clave_desbloqueo()

    def verificar_sesion_activa_loop(self):
        """Comprueba cada 3 segundos si el token cambió porque se inició sesión en la PWA."""
        self.after(3000, self.verificar_sesion_activa_loop)

        if self.id_usuario_actual and self.token_sesion_actual and self.frame_inicio:
            valida = validar_sesion_activa(self.id_usuario_actual, self.token_sesion_actual)
            if not valida and not self.win_duplicado_ref:
                self.mostrar_modal_sesion_duplicada()

    def mostrar_modal_sesion_duplicada(self):
        """Modal estilo WhatsApp Web con opciones 'Usar aquí' o 'Cerrar sesión'."""
        self.cerrar_modal_desbloqueo()

        win = ctk.CTkToplevel(self)
        win.title("Sesión Abierta en Otro Dispositivo")
        win.resizable(False, False)
        SeguridadService.centrar_ventana(win, 480, 260)
        win.transient(self)
        win.after(150, win.grab_set)
        self.win_duplicado_ref = win

        def cerrar_y_salir():
            try:
                win.grab_release()
                win.destroy()
            except Exception:
                pass
            self.win_duplicado_ref = None
            self.cerrar_sesion_forzado()

        def usar_aqui():
            nuevo_token = str(uuid.uuid4())
            if retomar_sesion(self.id_usuario_actual, nuevo_token, 'ESCRITORIO'):
                self.token_sesion_actual = nuevo_token
                self.ultimo_actividad = time.time()
                self.registrar_log("Usuario seleccionó 'Usar aquí' la sesión en Escritorio")
                try:
                    win.grab_release()
                    win.destroy()
                except Exception:
                    pass
                self.win_duplicado_ref = None
            else:
                messagebox.showerror("Error ❌", "No se pudo retomar la sesión.", parent=win)

        win.protocol("WM_DELETE_WINDOW", cerrar_y_salir)

        card = ctk.CTkFrame(win, fg_color=CARD_BG, corner_radius=16, border_width=1, border_color=CARD_BORDE)
        card.pack(fill="both", expand=True, padx=15, pady=15)

        ctk.CTkLabel(
            card, 
            text="📱 SESIÓN ABIERTA EN OTRA VENTANA", 
            font=("Calibri", 17, "bold"), 
            text_color=ROJO
        ).pack(pady=(15, 8))

        msg = (
            "El Taller Automotriz está abierto en otro dispositivo (PWA Web).\n"
            "¿Desea usar la aplicación aquí o cerrar la sesión?"
        )
        ctk.CTkLabel(
            card, 
            text=msg, 
            font=("Calibri", 14), 
            text_color=TXT_T, 
            justify="center",
            wraplength=420
        ).pack(pady=(0, 20))

        btn_container = ctk.CTkFrame(card, fg_color="transparent")
        btn_container.pack(fill="x", padx=10)

        ctk.CTkButton(
            btn_container, 
            text="Cerrar Sesión", 
            width=180, 
            height=40, 
            fg_color=BTN_GRIS, 
            hover_color=BTN_GRIS_H,
            text_color=TXT_T,
            font=("Calibri", 14, "bold"), 
            command=cerrar_y_salir
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            btn_container, 
            text="Usar aquí", 
            width=180, 
            height=40, 
            fg_color=ROJO, 
            hover_color=ROJO_H,
            font=("Calibri", 14, "bold"), 
            command=usar_aqui
        ).pack(side="right", padx=10)

    def cerrar_modal_desbloqueo(self):
        w = self.win_unlock_ref
        self.win_unlock_ref = None
        if w is not None:
            try:
                if w.winfo_exists():
                    w.grab_release()
                    w.destroy()
            except Exception:
                pass

    def cerrar_ventanas_flotantes(self):
        for w in self.ventanas_flotantes:
            try:
                if w.winfo_exists():
                    w.grab_release()
                    w.destroy()
            except Exception:
                pass
        self.ventanas_flotantes.clear()

    def solicitar_clave_desbloqueo(self):
        self.cerrar_modal_desbloqueo()

        win = ctk.CTkToplevel(self)
        win.title("Sesión Bloqueada")
        win.resizable(False, False)
        SeguridadService.centrar_ventana(win, 420, 290)
        win.transient(self)
        win.after(150, win.grab_set)
        self.win_unlock_ref = win
        intentos = {"n": 0}

        def al_cerrar_con_x():
            messagebox.showwarning(
                "Seguridad 🔒",
                "No puede omitir el desbloqueo. Debe ingresar su contraseña para continuar.",
                parent=win
            )
            txt_p.focus_force()

        win.protocol("WM_DELETE_WINDOW", al_cerrar_con_x)

        ctk.CTkLabel(win, text="🔒 SESIÓN BLOQUEADA", font=("Calibri", 20, "bold"), text_color=ROJO).pack(pady=(20, 5))
        ctk.CTkLabel(win, text="Sistema bloqueado por inactividad.\nIngrese su contraseña para continuar:",
                     font=("Calibri", 14), justify="center").pack(pady=(0, 15))

        txt_p = ctk.CTkEntry(win, width=320, height=42, show="•", placeholder_text="Ingrese su contraseña", font=("Calibri", 15))
        txt_p.pack(pady=(0, 15))
        txt_p.focus_force()
        txt_p.bind("<Return>", lambda e: validar())

        def validar():
            pas = txt_p.get()
            if not pas:
                messagebox.showwarning("Atención ⚠️", "Ingrese su contraseña.", parent=win)
                return
            try:
                with conexion_db(True) as (con, cur):
                    cur.execute("SELECT password_hash FROM usuarios WHERE id_usuario = %s", (self.id_usuario_actual,))
                    u = cur.fetchone()
            except mysql.connector.Error as err:
                messagebox.showerror("Error ❌", str(err), parent=win)
                return

            if u and SeguridadService.verificar(pas, u['password_hash']):
                self.bloqueo_pantalla_activo = False
                self.ultimo_actividad = time.time()
                self.registrar_log("Sesión desbloqueada")
                self.cerrar_modal_desbloqueo()
            else:
                intentos["n"] += 1
                if intentos["n"] >= MAX_INTENTOS_DESBLOQUEO:
                    self.registrar_log("Cierre de sesión: demasiados intentos fallidos al desbloquear")
                    messagebox.showerror("Seguridad 🔒", "Demasiados intentos incorrectos. Se cerrará la sesión.", parent=win)
                    self.cerrar_sesion_forzado()
                else:
                    messagebox.showerror("Error ❌", f"Contraseña incorrecta.\nIntentos restantes: {MAX_INTENTOS_DESBLOQUEO - intentos['n']}", parent=win)
                    txt_p.delete(0, "end")

        ctk.CTkButton(win, text="Desbloquear 🔓", height=42, width=320, fg_color=ROJO, hover_color=ROJO_H,
                      font=("Calibri", 15, "bold"), command=validar).pack()

    # =========================================================================
    # TEMA, FONDO Y UTILIDADES
    # =========================================================================
    def cambiar_tema(self):
        nuevo = "Dark" if ctk.get_appearance_mode() == "Light" else "Light"
        ctk.set_appearance_mode(nuevo)
        self.actualizar_visibilidad_fondo()

        for clave, btn in self.btn_menu_activos.items():
            try:
                if btn.cget("fg_color") not in ["transparent", ("transparent", "transparent")]:
                    self.seleccionar_opcion_menu(clave)
                    break
            except Exception:
                pass

    def actualizar_visibilidad_fondo(self):
        if not hasattr(self, 'lbl_bg'):
            return
        ruta = self.ruta_fondo_oscuro if ctk.get_appearance_mode() == "Dark" else self.ruta_fondo_claro
        if not ruta:
            return
        if ruta not in self._cache_fondos:
            w, h = self.winfo_screenwidth(), self.winfo_screenheight()
            img = Image.open(ruta).convert("RGB").resize((w, h), Image.Resampling.LANCZOS)
            self._cache_fondos[ruta] = ctk.CTkImage(light_image=img, dark_image=img, size=(w, h))
        self.lbl_bg.configure(image=self._cache_fondos[ruta])
        self.lbl_bg.place(x=0, y=0, relwidth=1, relheight=1)
        self.lbl_bg.lower()

    def hacer_imagen_circular(self, ruta_img, tamano):
        img = Image.open(ruta_img).convert("RGBA").resize(tamano, Image.Resampling.LANCZOS)
        mascara = Image.new("L", tamano, 0)
        ImageDraw.Draw(mascara).ellipse((0, 0, tamano[0], tamano[1]), fill=255)
        res = Image.new("RGBA", tamano, (255, 255, 255, 0))
        res.paste(img, (0, 0), mascara)
        return res

    def _logo(self, tam):
        if not self.ruta_logo:
            return None
        img = self.hacer_imagen_circular(self.ruta_logo, (tam, tam))
        return ctk.CTkImage(light_image=img, dark_image=img, size=(tam, tam))

    def registrar_log(self, accion, usuario=None, rol=None):
        try:
            with conexion_db() as (con, cur):
                cur.execute(
                    "INSERT INTO logs_sistema (usuario, rol, accion) VALUES (%s, %s, %s)",
                    (usuario or self.usuario_actual or "Sistema/Anonimo", rol or self.rol_actual or "Invitado", accion)
                )
                con.commit()
        except mysql.connector.Error as err:
            print(f"Error registrando log: {err}")

    def tiene_rol(self, *roles):
        if not self.id_usuario_actual or normalizar_rol(self.rol_actual) not in roles:
            self.registrar_log(f"Acceso denegado: rol '{self.rol_actual}' intentó una acción de {roles}")
            messagebox.showerror("Acceso denegado 🚫", "No tiene permisos para realizar esta acción.")
            return False
        return True

    def obtener_conteo_real(self, consulta_sql):
        try:
            with conexion_db() as (con, cur):
                cur.execute(consulta_sql)
                res = cur.fetchone()
                return int(res[0]) if res and res[0] is not None else 0
        except mysql.connector.Error:
            return 0

    def obtener_lista_clientes(self):
        clientes = {"Sin asignar": None}
        try:
            with conexion_db(True) as (con, cur):
                cur.execute("SELECT id_usuario, nombre_completo, usuario FROM usuarios WHERE LOWER(rol) LIKE '%cliente%'")
                for r in cur.fetchall():
                    clientes[f"#{r['id_usuario']} - {r['nombre_completo']} ({r['usuario']})"] = r['id_usuario']
        except mysql.connector.Error:
            pass
        return clientes

    def seleccionar_opcion_menu(self, clave_opcion):
        modo = ctk.get_appearance_mode()
        for clave, btn in self.btn_menu_activos.items():
            try:
                if clave == clave_opcion:
                    if modo == "Light":
                        btn.configure(fg_color="#FFF0F0", text_color=ROJO, hover_color="#FFE0E0")
                    else:
                        btn.configure(fg_color="#2B1819", text_color="#FF5252", hover_color="#3A2022")
                else:
                    btn.configure(fg_color="transparent", text_color=("#222222", "#E0E0E0"), hover_color=("#F5F5F5", "#2B2B2B"))
            except Exception:
                pass

    # ------------------ VENTANAS FLOTANTES ------------------
    def crear_ventana_flotante(self, titulo, ancho=480, alto=460):
        win = ctk.CTkToplevel(self)
        win.title(titulo)
        win.resizable(False, False)
        SeguridadService.centrar_ventana(win, ancho, alto)
        win.transient(self)
        win.after(150, win.grab_set)
        win.after(200, win.focus_force)
        self.ventanas_flotantes.append(win)

        ctk.CTkLabel(win, text=titulo, font=("Calibri", 22, "bold"), text_color=ROJO).pack(pady=(18, 8))
        cuerpo = ctk.CTkFrame(win, fg_color="transparent")
        cuerpo.pack(fill="both", expand=True, padx=28, pady=(0, 18))
        return win, cuerpo

    def _campo(self, parent, etiqueta, placeholder="", show=None, alto=38):
        ctk.CTkLabel(parent, text=etiqueta, font=("Calibri", 15, "bold"), text_color=("#111827", "#FFFFFF")).pack(anchor="w")
        e = ctk.CTkEntry(parent, height=alto, placeholder_text=placeholder, font=("Calibri", 15), show=show)
        e.pack(fill="x", pady=(2, 10))
        return e

    def _barra_botones(self, parent, texto_guardar, comando, win):
        barra = ctk.CTkFrame(parent, fg_color="transparent")
        barra.pack(fill="x", side="bottom", pady=(8, 0))
        ctk.CTkButton(barra, text="Cancelar", width=130, height=42, fg_color=BTN_GRIS, hover_color=BTN_GRIS_H,
                      text_color=TXT_T, font=("Calibri", 15, "bold"), command=win.destroy).pack(side="left")
        ctk.CTkButton(barra, text=texto_guardar, width=210, height=42, fg_color=ROJO, hover_color=ROJO_H,
                      font=("Calibri", 15, "bold"), command=comando).pack(side="right")

    def _encabezado_body(self, titulo, subtitulo):
        ctk.CTkLabel(self.body_scroll, text=titulo, font=("Calibri", 26, "bold"), text_color=TXT_T).pack(pady=(15, 2))
        ctk.CTkLabel(self.body_scroll, text=subtitulo, font=("Calibri", 16), text_color=TXT_S).pack(pady=(0, 15))

    # =========================================================================
    # LOGIN Y RECUPERACIÓN DE CONTRASEÑA
    # =========================================================================
    def mostrar_login(self):
        for attr in ("frame_registro", "frame_inicio", "frame_login"):
            f = getattr(self, attr)
            if f:
                f.destroy()
                setattr(self, attr, None)

        self.actualizar_visibilidad_fondo()
        self.btn_theme_login.place(relx=0.03, rely=0.96, anchor="w")
        self.footer.place(relx=0.5, rely=0.96, anchor="center")
        self.card_main.configure(fg_color=("#FFFFFF", "#121214"), border_color=("#D1D5DB", "#2A2D34"), border_width=1)
        self.card_main.place(relx=0.5, rely=0.47, anchor="center")

        self.frame_login = ctk.CTkFrame(self.card_main, fg_color="transparent")
        self.frame_login.pack(fill="both", expand=True, padx=25, pady=20)

        left_f = ctk.CTkFrame(self.frame_login, fg_color="transparent")
        left_f.pack(side="left", fill="both", expand=True, padx=(10, 10))

        logo_center = ctk.CTkFrame(left_f, fg_color="transparent")
        logo_center.place(relx=0.5, rely=0.46, anchor="center")

        img_l = self._logo(330)
        if img_l:
            ctk.CTkLabel(logo_center, image=img_l, text="").pack(pady=(0, 15))

        slogan = ctk.CTkFrame(logo_center, fg_color="transparent")
        slogan.pack()
        ctk.CTkFrame(slogan, width=30, height=2, fg_color=ROJO).pack(side="left", padx=6)
        ctk.CTkLabel(slogan, text="Tu vehículo en las mejores manos", font=("Calibri", 15, "italic", "bold"),
                     text_color=("#444444", "#DDDDDD")).pack(side="left")
        ctk.CTkFrame(slogan, width=30, height=2, fg_color=ROJO).pack(side="right", padx=6)

        ctk.CTkFrame(self.frame_login, width=3, fg_color=ROJO, corner_radius=1).pack(side="left", fill="y", pady=15)

        right_f = ctk.CTkFrame(self.frame_login, fg_color="transparent")
        right_f.pack(side="right", fill="both", expand=True, padx=(10, 10))

        form_c = ctk.CTkFrame(right_f, fg_color="transparent")
        form_c.place(relx=0.5, rely=0.48, anchor="center")

        ctk.CTkLabel(form_c, text="👤", font=("Segoe UI Emoji", 42), text_color=ROJO).pack(pady=(0, 2))
        ctk.CTkLabel(form_c, text="INICIO DE SESIÓN", font=("Calibri", 28, "bold"), text_color=("#000000", "#FFFFFF")).pack(pady=(0, 4))
        ctk.CTkLabel(form_c, text="Ingresa tus datos para acceder al sistema", font=("Calibri", 15),
                     text_color=("#555555", "#AAAAAA")).pack(pady=(0, 18))

        # HONEYPOT
        self.txt_honeypot = ctk.CTkEntry(form_c, width=10, height=10, border_width=0)
        self.txt_honeypot.place(x=-600, y=-600)
        try:
            self.txt_honeypot._entry.configure(takefocus=0)
        except Exception:
            pass

        ctk.CTkLabel(form_c, text="👤  Usuario:", font=("Calibri", 15, "bold"), text_color=("#000000", "#FFFFFF")).pack(anchor="w", pady=(0, 4))
        self.txt_user_login = ctk.CTkEntry(form_c, width=350, height=46, corner_radius=10, placeholder_text="Ingrese su usuario",
                                           font=("Calibri", 15), fg_color=("#FAFAFA", "#1A1A1E"), border_width=1.5,
                                           border_color=("#B0B0B0", "#333338"))
        self.txt_user_login.pack(pady=(0, 14))

        ctk.CTkLabel(form_c, text="🔒  Contraseña:", font=("Calibri", 15, "bold"), text_color=("#000000", "#FFFFFF")).pack(anchor="w", pady=(0, 4))
        pass_f = ctk.CTkFrame(form_c, fg_color="transparent")
        pass_f.pack(pady=(0, 6))

        self.txt_pass_login = ctk.CTkEntry(pass_f, width=294, height=46, corner_radius=10, show="•",
                                           placeholder_text="Ingrese su contraseña", font=("Calibri", 15),
                                           fg_color=("#FAFAFA", "#1A1A1E"), border_width=1.5,
                                           border_color=("#B0B0B0", "#333338"))
        self.txt_pass_login.pack(side="left", padx=(0, 6))
        self.txt_pass_login.bind("<Return>", lambda e: self.validar_login())

        estado_ojo = {"ver": False}

        def toggle_pass():
            estado_ojo["ver"] = not estado_ojo["ver"]
            self.txt_pass_login.configure(show="" if estado_ojo["ver"] else "•")
            btn_ojo.configure(text="🙈" if estado_ojo["ver"] else "👁️")

        btn_ojo = ctk.CTkButton(pass_f, text="👁️", width=50, height=46, corner_radius=10, fg_color=("#E0E0E0", "#25252A"),
                                text_color=("#000", "#FFF"), hover_color=("#CCCCCC", "#333338"),
                                font=("Segoe UI Emoji", 18), command=toggle_pass)
        btn_ojo.pack(side="right")

        ctk.CTkButton(form_c, text=" ¿Olvidó su contraseña?", font=("Calibri", 14, "underline"), text_color=("#444444", "#CCCCCC"),
                      hover_color=("#FFFFFF", "#121214"), fg_color="transparent", width=100,
                      command=self.recuperar_contrasena).pack(anchor="e", pady=(0, 16))
        ctk.CTkButton(form_c, text="➔  INICIAR SESIÓN", width=350, height=48, corner_radius=10, fg_color=ROJO, hover_color=ROJO_H,
                      font=("Calibri", 17, "bold"), command=self.validar_login).pack(pady=(0, 10))
        ctk.CTkButton(form_c, text="¿No tiene cuenta? Regístrese aquí", font=("Calibri", 15, "bold"), text_color=ROJO,
                      hover_color=("#FFFFFF", "#121214"), fg_color="transparent", command=self.mostrar_registro).pack()

    def validar_login(self):
        if SeguridadService.validar_honeypot(self.txt_honeypot):
            self.registrar_log("Posible bot detectado (honeypot lleno) en el login", usuario="Anónimo", rol="Invitado")
            return

        usr = self.txt_user_login.get().strip()
        pas = self.txt_pass_login.get()

        if not usr or not pas:
            messagebox.showwarning("Datos Incompletos ⚠️", "Ingrese usuario y contraseña.")
            return

        try:
            with conexion_db(True) as (con, cur):
                cur.execute(
                    """SELECT id_usuario, nombre_completo, rol, password_hash, estado, intentos_fallidos,
                              (bloqueado_hasta IS NOT NULL AND bloqueado_hasta > NOW()) AS bloqueado
                       FROM usuarios WHERE usuario = %s""", (usr,))
                user = cur.fetchone()

                # 1. EL USUARIO NO EXISTE
                if not user:
                    self.registrar_log(f"Intento de login con usuario inexistente: '{usr}'", usuario=usr, rol="Invitado")
                    messagebox.showerror("Error de Acceso ❌", f"El usuario '{usr}' no se encuentra registrado.")
                    self.txt_pass_login.delete(0, "end")
                    return

                # 2. CUENTA BLOQUEADA POR INTENTOS FALLIDOS
                if user['bloqueado']:
                    self.registrar_log(f"Intento de acceso a cuenta bloqueada: {usr}", usuario=usr, rol="Invitado")
                    messagebox.showwarning("Cuenta Bloqueada 🔒", f"Demasiados intentos fallidos.\nIntente de nuevo en {BLOQUEO_MINUTOS} minutos.")
                    self.txt_pass_login.delete(0, "end")
                    return

                # 3. CUENTA INACTIVA
                if user['estado'] != 'Activo':
                    messagebox.showwarning("Cuenta Inactiva ⚠️", "Esta cuenta ha sido desactivada por la administración.")
                    self.txt_pass_login.delete(0, "end")
                    return

                # 4. CONTRASEÑA INCORRECTA
                if not SeguridadService.verificar(pas, user['password_hash']):
                    n = (user['intentos_fallidos'] or 0) + 1
                    if n >= MAX_INTENTOS_LOGIN:
                        cur.execute(
                            """UPDATE usuarios SET intentos_fallidos = 0,
                               bloqueado_hasta = NOW() + INTERVAL %s MINUTE WHERE id_usuario = %s""",
                            (BLOQUEO_MINUTOS, user['id_usuario']))
                        con.commit()
                        self.registrar_log(f"Cuenta '{usr}' bloqueada por {BLOQUEO_MINUTOS} min (intentos fallidos)", usuario=usr, rol="Invitado")
                        messagebox.showerror(
                            "Cuenta Bloqueada 🔒",
                            f"Ha ingresado la contraseña incorrecta {MAX_INTENTOS_LOGIN} veces.\nSu cuenta ha sido bloqueada por {BLOQUEO_MINUTOS} minutos."
                        )
                    else:
                        cur.execute("UPDATE usuarios SET intentos_fallidos = %s WHERE id_usuario = %s", (n, user['id_usuario']))
                        con.commit()
                        self.registrar_log(f"Contraseña incorrecta para el usuario '{usr}' (Intento {n})", usuario=usr, rol="Invitado")
                        intentos_restantes = MAX_INTENTOS_LOGIN - n
                        messagebox.showerror(
                            "Contraseña Incorrecta ❌",
                            f"La contraseña ingresada es incorrecta.\nIntentos restantes antes de bloquear: {intentos_restantes}"
                        )
                    self.txt_pass_login.delete(0, "end")
                    return

                # --- LOGIN EXITOSO ---
                if SeguridadService.es_legacy(user['password_hash']) and len(pas.encode("utf-8")) <= 72:
                    cur.execute("UPDATE usuarios SET password_hash = %s WHERE id_usuario = %s",
                                (SeguridadService.hashear(pas), user['id_usuario']))

                cur.execute("UPDATE usuarios SET intentos_fallidos = 0, bloqueado_hasta = NULL WHERE id_usuario = %s",
                            (user['id_usuario'],))
                con.commit()

        except mysql.connector.Error as err:
            messagebox.showerror("Error ❌", f"No se pudo conectar a MySQL:\n{err}")
            return

        self.usuario_actual = user['nombre_completo']
        self.rol_actual = user['rol']
        self.id_usuario_actual = user['id_usuario']
        self.ultimo_actividad = time.time()
        self.bloqueo_pantalla_activo = False

        # Registrar Token de Sesión Única en la base de datos
        self.token_sesion_actual = str(uuid.uuid4())
        registrar_inicio_sesion(self.id_usuario_actual, self.token_sesion_actual, 'ESCRITORIO')

        self.registrar_log("Inicio de sesión exitoso")
        self.mostrar_inicio()

    def recuperar_contrasena(self):
        win, cuerpo = self.crear_ventana_flotante("🔑 Recuperar Contraseña", 500, 610)
        ctk.CTkLabel(cuerpo, text="Ingrese su usuario y teléfono para verificar su identidad", font=("Calibri", 14),
                     text_color=("#222222", "#CCCCCC"), wraplength=440).pack(pady=(0, 10))

        txt_user = self._campo(cuerpo, "Usuario:", "Ingrese su usuario")
        txt_tel = self._campo(cuerpo, "Teléfono registrado:", "Ingrese su teléfono")
        txt_cod = self._campo(cuerpo, "Código de verificación:", "Código de 6 dígitos")
        txt_pas = self._campo(cuerpo, "Nueva contraseña:", "Mín. 8 caracteres, letras y números", show="•")
        txt_cod.configure(state="disabled")
        txt_pas.configure(state="disabled")

        estado = {"cr": None}

        def bloquear_campos():
            txt_cod.configure(state="disabled")
            txt_pas.configure(state="disabled")
            btn_rest.configure(state="disabled")

        def generar_codigo():
            usr, tel = txt_user.get().strip(), txt_tel.get().strip()
            if not usr or not tel:
                messagebox.showwarning("Atención ⚠️", "Ingrese usuario y teléfono.", parent=win)
                return
            try:
                with conexion_db(True) as (con, cur):
                    cur.execute("SELECT id_usuario FROM usuarios WHERE usuario = %s AND telefono = %s AND estado = 'Activo'", (usr, tel))
                    u = cur.fetchone()
            except mysql.connector.Error as err:
                messagebox.showerror("Error ❌", str(err), parent=win)
                return

            self.registrar_log(f"Solicitud de recuperación de contraseña para '{usr}'", usuario=usr, rol="Invitado")
            if not u:
                messagebox.showerror("Error ❌", "Los datos no coinciden.", parent=win)
                return

            estado["cr"] = CodigoRecuperacion(u['id_usuario'])
            if MOSTRAR_CODIGO_EN_PANTALLA:
                messagebox.showinfo("Código Generado 📱",
                                    f"Código de verificación: {estado['cr'].codigo}\n\nVence en 5 minutos. Tiene 3 intentos.", parent=win)
            txt_cod.configure(state="normal")
            txt_pas.configure(state="normal")
            btn_rest.configure(state="normal")

        def actualizar_clave():
            cr = estado["cr"]
            if not cr:
                return
            np_ = txt_pas.get()
            errores = SeguridadService.validar_password(np_)
            if errores:
                messagebox.showwarning("Contraseña insegura ⚠️", "\n".join(errores), parent=win)
                return

            res = cr.verificar(txt_cod.get())
            if res == "expirado":
                estado["cr"] = None
                bloquear_campos()
                messagebox.showerror("Código vencido ⏱", "El código expiró. Genere uno nuevo.", parent=win)
                return
            if res == "agotado":
                estado["cr"] = None
                bloquear_campos()
                messagebox.showerror("Error ❌", "Demasiados intentos. Genere un código nuevo.", parent=win)
                return
            if res == "incorrecto":
                messagebox.showerror("Error ❌", "Código incorrecto.", parent=win)
                return

            try:
                with conexion_db() as (con, cur):
                    cur.execute("UPDATE usuarios SET password_hash = %s, intentos_fallidos = 0, bloqueado_hasta = NULL WHERE id_usuario = %s",
                                (SeguridadService.hashear(np_), cr.id_usuario))
                    con.commit()
                self.registrar_log(f"Contraseña restablecida (usuario #{cr.id_usuario})", usuario=f"#{cr.id_usuario}", rol="Invitado")
                estado["cr"] = None
                messagebox.showinfo("Éxito 🎉", "Contraseña cambiada correctamente.", parent=win)
                win.destroy()
            except mysql.connector.Error as err:
                messagebox.showerror("Error ❌", str(err), parent=win)

        ctk.CTkButton(cuerpo, text="📱 Generar Código", height=42, font=("Calibri", 15, "bold"), fg_color=ROJO,
                      hover_color=ROJO_H, command=generar_codigo).pack(fill="x", pady=(0, 8))
        btn_rest = ctk.CTkButton(cuerpo, text="Restablecer Contraseña", height=42, font=("Calibri", 15, "bold"),
                                  fg_color=ROJO_H, hover_color="#8B0000", state="disabled", command=actualizar_clave)
        btn_rest.pack(fill="x")

    # =========================================================================
    # REGISTRO DE CLIENTES
    # =========================================================================
    def mostrar_registro(self):
        for attr in ("frame_login", "frame_registro"):
            f = getattr(self, attr)
            if f:
                f.destroy()
                setattr(self, attr, None)

        self.actualizar_visibilidad_fondo()
        self.frame_registro = ctk.CTkFrame(self.card_main, fg_color="transparent")
        self.frame_registro.pack(fill="both", expand=True, padx=30, pady=20)

        left_f = ctk.CTkFrame(self.frame_registro, fg_color="transparent")
        left_f.pack(side="left", fill="both", expand=True, padx=(0, 15))
        left_c = ctk.CTkFrame(left_f, fg_color="transparent")
        left_c.place(relx=0.5, rely=0.5, anchor="center")

        img_l = self._logo(280)
        if img_l:
            ctk.CTkLabel(left_c, image=img_l, text="").pack(pady=(0, 15))
        ctk.CTkLabel(left_c, text="Taller Automotriz I.G", font=("Calibri", 26, "bold"), text_color=ROJO).pack(pady=(0, 4))
        ctk.CTkLabel(left_c, text="Crea tu cuenta de Cliente para acceder\ny consultar tus servicios automotrices.",
                     font=("Calibri", 16), text_color=("#222222", "#CCCCCC"), justify="center").pack()

        ctk.CTkFrame(self.frame_registro, width=3, fg_color=ROJO).pack(side="left", fill="y", pady=15)

        right_f = ctk.CTkFrame(self.frame_registro, fg_color="transparent")
        right_f.pack(side="right", fill="both", expand=True, padx=(15, 0))

        ctk.CTkLabel(right_f, text="👤+", font=("Segoe UI Emoji", 40), text_color=ROJO).pack(pady=(0, 2))
        ctk.CTkLabel(right_f, text="REGISTRO DE CLIENTES", font=("Calibri", 28, "bold"), text_color=("#000000", "#FFFFFF")).pack(pady=(0, 15))

        grid_f = ctk.CTkFrame(right_f, fg_color="transparent")
        grid_f.pack(fill="x", pady=5)

        def etiqueta(texto, fila, col):
            ctk.CTkLabel(grid_f, text=texto, font=("Calibri", 16, "bold"), text_color=("#000", "#FFF")).grid(row=fila, column=col, sticky="w", padx=8)

        def entrada(ph, fila, col, show=None):
            e = ctk.CTkEntry(grid_f, width=240, height=44, corner_radius=8, placeholder_text=ph, font=("Calibri", 16), show=show)
            e.grid(row=fila, column=col, padx=8, pady=(3, 12))
            return e

        etiqueta("Nombre completo:", 0, 0); etiqueta("Usuario:", 0, 1)
        self.reg_nombre = entrada("Ingrese su nombre", 1, 0)
        self.reg_usuario = entrada("Cree un usuario", 1, 1)
        etiqueta("Correo electrónico:", 2, 0); etiqueta("Teléfono:", 2, 1)
        self.reg_correo = entrada("ejemplo@correo.com", 3, 0)
        self.reg_telefono = entrada("10 dígitos", 3, 1)
        etiqueta("Contraseña:", 4, 0); etiqueta("Confirmar contraseña:", 4, 1)
        self.reg_pass1 = entrada("Contraseña", 5, 0, show="•")
        self.reg_pass2 = entrada("Confirme contraseña", 5, 1, show="•")
        ctk.CTkLabel(grid_f, text="Mínimo 8 caracteres, con letras y números.", font=("Calibri", 13),
                     text_color=("#6B7280", "#9CA3AF")).grid(row=6, column=0, columnspan=2, sticky="w", padx=8)

        btn_f = ctk.CTkFrame(right_f, fg_color="transparent")
        btn_f.pack(fill="x", padx=8, pady=(20, 5))
        ctk.CTkButton(btn_f, text="CANCELAR", width=200, height=46, fg_color=("#F2F2F2", "#333333"), hover_color=("#E5E5E5", "#444444"),
                      border_width=1, border_color="#B0B0B0", text_color=("#333333", "#FFFFFF"), font=("Calibri", 15, "bold"),
                      corner_radius=8, command=self.mostrar_login).pack(side="left")
        ctk.CTkButton(btn_f, text="👤+ CREAR CUENTA", width=230, height=46, fg_color=ROJO, hover_color=ROJO_H, text_color="#FFFFFF",
                      font=("Calibri", 16, "bold"), corner_radius=8, command=self.solicitar_politica_y_guardar).pack(side="right")

    def validar_datos_usuario(self, nombre, usuario, correo, telefono, pass1, pass2=None):
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
        if pass2 is not None and pass1 != pass2:
            errores.append("• Las contraseñas no coinciden.")
        return errores

    def solicitar_politica_y_guardar(self):
        errores = self.validar_datos_usuario(
            self.reg_nombre.get().strip(), self.reg_usuario.get().strip(), self.reg_correo.get().strip(),
            self.reg_telefono.get().strip(), self.reg_pass1.get(), self.reg_pass2.get())
        if errores:
            messagebox.showerror("Errores de Validación ❌", "\n".join(errores))
            return
        SeguridadService.mostrar_modal_politica_datos(self, self.guardar_registro)

    def guardar_registro(self):
        nombre = self.reg_nombre.get().strip()
        usuario = self.reg_usuario.get().strip()
        correo = self.reg_correo.get().strip()
        telefono = self.reg_telefono.get().strip()
        pass_hash = SeguridadService.hashear(self.reg_pass1.get())

        try:
            with conexion_db() as (con, cur):
                cur.execute(
                    "INSERT INTO usuarios (nombre_completo, usuario, correo, telefono, password_hash, rol, estado) "
                    "VALUES (%s, %s, %s, %s, %s, 'Cliente', 'Activo')",
                    (nombre, usuario, correo, telefono, pass_hash))
                con.commit()
            self.registrar_log("Nuevo cliente registrado (aceptó política de datos)", usuario=usuario, rol="Cliente")
            messagebox.showinfo("Registro Exitoso 🎉", f"¡Cuenta creada correctamente!\nInicie sesión con el usuario: {usuario}")
            self.mostrar_login()
        except mysql.connector.IntegrityError:
            messagebox.showerror("Usuario no disponible ❌", "Ese nombre de usuario ya está en uso. Elija otro.")
        except mysql.connector.Error as err:
            messagebox.showerror("Error ❌", f"Error:\n{err}")

    # =========================================================================
    # AUDITORÍA Y USUARIOS
    # =========================================================================
    def mostrar_historial_logs(self):
        if not self.tiene_rol("administrador"):
            return
        self.seleccionar_opcion_menu("logs")
        if not self.body_scroll:
            return
        for w in self.body_scroll.winfo_children():
            w.destroy()

        self._encabezado_body("📜 HISTORIAL DE AUDITORÍA", "Registro detallado de accesos y operaciones realizadas en el taller")
        frame = ctk.CTkFrame(self.body_scroll, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=20, pady=10)

        try:
            with conexion_db(True) as (con, cur):
                cur.execute("SELECT id_log, usuario, rol, accion, fecha_registro FROM logs_sistema ORDER BY fecha_registro DESC LIMIT 100")
                logs = cur.fetchall()
        except mysql.connector.Error as err:
            ctk.CTkLabel(frame, text=f"Error cargando auditoría:\n{err}", text_color=ROJO).pack(pady=20)
            return

        if not logs:
            ctk.CTkLabel(frame, text="No hay registros de auditoría en el sistema aún.", font=("Calibri", 16),
                         text_color=("#6B7280", "#9CA3AF")).pack(pady=30)
            return
        for log in logs:
            card = ctk.CTkFrame(frame, fg_color=CARD_BG, corner_radius=12, border_width=1, border_color=CARD_BORDE)
            card.pack(fill="x", pady=6, ipadx=14, ipady=10)
            top = ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x")
            ctk.CTkLabel(top, text=f"👤 {log['usuario']} ({log['rol']})", font=("Calibri", 16, "bold"), text_color=TXT_T).pack(side="left")
            ctk.CTkLabel(top, text=f"🕒 {log['fecha_registro']}", font=("Calibri", 14, "bold"), text_color=("#6B7280", "#9CA3AF")).pack(side="right")
            ctk.CTkLabel(card, text=f"• {log['accion']}", font=("Calibri", 15), text_color=("#374151", "#E5E7EB"), anchor="w").pack(fill="x", pady=(4, 0))

    def alternar_estado_usuario(self, id_usuario, estado_actual):
        if not self.tiene_rol("administrador"):
            return
        if id_usuario == self.id_usuario_actual:
            messagebox.showwarning("Acción no permitida ⚠️", "No puede desactivar su propia cuenta.")
            return
        nuevo = "Inactivo" if estado_actual == "Activo" else "Activo"
        accion = "desactivar" if nuevo == "Inactivo" else "reactivar"
        if not messagebox.askyesno("Confirmar Cambio ⚠️", f"¿Desea {accion} la cuenta del usuario #{id_usuario}?"):
            return
        try:
            with conexion_db() as (con, cur):
                cur.execute("UPDATE usuarios SET estado = %s WHERE id_usuario = %s", (nuevo, id_usuario))
                con.commit()
            self.registrar_log(f"Cambió el estado del usuario #{id_usuario} a {nuevo}")
            messagebox.showinfo("Éxito 🎉", f"El usuario ahora se encuentra '{nuevo}'.")
            self.mostrar_lista_usuarios()
        except mysql.connector.Error as err:
            messagebox.showerror("Error ❌", str(err))

    def abrir_registro_integrado_por_rol(self, rol_objetivo):
        if not self.tiene_rol("administrador"):
            return
        if rol_objetivo not in ("Administrador", "Mecánico", "Cliente"):
            return
        for w in self.body_scroll.winfo_children():
            w.destroy()

        self._encabezado_body(f"👤 REGISTRAR {rol_objetivo.upper()}", f"Ingrese la información para dar de alta un nuevo usuario con rol de {rol_objetivo}")
        card = ctk.CTkFrame(self.body_scroll, fg_color=CARD_BG, corner_radius=16, border_width=1, border_color=CARD_BORDE)
        card.pack(padx=40, pady=10, fill="x")
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(padx=30, pady=25, fill="x")

        txt_nom = self._campo(inner, "Nombre completo:", alto=44)
        txt_usr = self._campo(inner, "Usuario de acceso:", alto=44)
        txt_cor = self._campo(inner, "Correo electrónico:", alto=44)
        txt_tel = self._campo(inner, "Teléfono de contacto (10 dígitos):", alto=44)
        txt_pas = self._campo(inner, "Contraseña inicial (mín. 8, letras y números):", show="•", alto=44)

        barra = ctk.CTkFrame(inner, fg_color="transparent")
        barra.pack(fill="x", pady=(15, 0))

        def volver():
            if rol_objetivo == "Mecánico":
                self.mostrar_lista_usuarios("Mecánicos", "Mecánico")
            elif rol_objetivo == "Administrador":
                self.mostrar_lista_usuarios("Administrador", "Administrador")
            else:
                self.mostrar_lista_usuarios("Clientes", "Cliente")

        ctk.CTkButton(barra, text="⬅️ Cancelar y Volver", width=180, height=46, fg_color=BTN_GRIS, hover_color=BTN_GRIS_H,
                      text_color=TXT_T, font=("Calibri", 15, "bold"), command=volver).pack(side="left")

        def guardar():
            n, u, c, t, p = txt_nom.get().strip(), txt_usr.get().strip(), txt_cor.get().strip(), txt_tel.get().strip(), txt_pas.get()
            errores = self.validar_datos_usuario(n, u, c, t, p)
            if errores:
                messagebox.showwarning("Errores de Validación ⚠️", "\n".join(errores))
                return
            try:
                with conexion_db() as (con, cur):
                    cur.execute(
                        "INSERT INTO usuarios (nombre_completo, usuario, correo, telefono, password_hash, rol, estado) "
                        "VALUES (%s, %s, %s, %s, %s, %s, 'Activo')",
                        (n, u, c, t, SeguridadService.hashear(p), rol_objetivo))
                    con.commit()
                self.registrar_log(f"Creó la cuenta de {rol_objetivo} '{n}'")
                messagebox.showinfo("Registro Completado 🎉", f"Cuenta de {rol_objetivo} creada exitosamente.")
                volver()
            except mysql.connector.IntegrityError:
                messagebox.showerror("Usuario no disponible ❌", "Ese nombre de usuario ya está en uso.")
            except mysql.connector.Error as err:
                messagebox.showerror("Error ❌", str(err))

        ctk.CTkButton(barra, text=f"💾 Guardar {rol_objetivo}", width=220, height=46, fg_color=ROJO, hover_color=ROJO_H,
                      font=("Calibri", 16, "bold"), command=guardar).pack(side="right")

    def cargar_cards_usuarios(self, contenedor, filtro_rol=None):
        for w in contenedor.winfo_children():
            w.destroy()
        try:
            with conexion_db(True) as (con, cur):
                base = "SELECT id_usuario, nombre_completo, usuario, correo, telefono, rol, estado FROM usuarios"
                if filtro_rol and filtro_rol != "Todos":
                    cur.execute(base + " WHERE LOWER(rol) LIKE %s ORDER BY id_usuario ASC", (f"%{filtro_rol.lower()}%",))
                else:
                    cur.execute(base + " ORDER BY id_usuario ASC")
                usuarios = cur.fetchall()
        except mysql.connector.Error as err:
            ctk.CTkLabel(contenedor, text=f"Error al cargar usuarios:\n{err}", text_color=ROJO).pack(pady=20)
            return

        if not usuarios:
            ctk.CTkLabel(contenedor, text="No hay usuarios registrados en esta sección.", font=("Calibri", 16),
                         text_color=("#6B7280", "#9CA3AF")).pack(pady=30)
            return

        for u in usuarios:
            rol = str(u['rol']).strip().capitalize()
            estado = u['estado']
            card = ctk.CTkFrame(contenedor, fg_color=CARD_BG, corner_radius=12, border_width=1, border_color=CARD_BORDE)
            card.pack(fill="x", pady=6, ipadx=14, ipady=10)
            top = ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x")

            ctk.CTkLabel(top, text=f"#{u['id_usuario']} {u['nombre_completo']}", font=("Calibri", 16, "bold"), text_color=TXT_T).pack(side="left")
            es_admin = rol == "Administrador"
            ctk.CTkLabel(top, text=f"  {rol}  ", font=("Calibri", 13, "bold"), fg_color="#FFF0F0" if es_admin else "#2D2D35",
                         text_color=ROJO if es_admin else "#EEE", corner_radius=6).pack(side="left", padx=10)
            bg, tx = ("#E8F5E9", "#2E7D32") if estado == "Activo" else ("#FFEBEE", "#C62828")
            ctk.CTkLabel(top, text=f"● {estado}", font=("Calibri", 13, "bold"), fg_color=bg, text_color=tx, corner_radius=6).pack(side="right")

            info = f"Usuario: {u['usuario']} | Tel: {u['telefono']} | {u['correo'] if u['correo'] else 'Sin correo'}"
            ctk.CTkLabel(card, text=info, font=("Calibri", 14), text_color=TXT_S, anchor="w").pack(fill="x", pady=(4, 6))

            activo = estado == "Activo"
            ctk.CTkButton(card, text="🚫 Desactivar" if activo else "✅ Reactivar", width=120, height=32,
                          fg_color="#C62828" if activo else "#2E7D32", hover_color="#9A0007" if activo else "#1B5E20",
                          font=("Calibri", 13, "bold"),
                          command=lambda uid=u['id_usuario'], est=estado: self.alternar_estado_usuario(uid, est)).pack(anchor="e")

    def mostrar_lista_usuarios(self, pestaña_inicial="Todos", filtro_inicial="Todos"):
        if not self.tiene_rol("administrador"):
            return
        self.seleccionar_opcion_menu("usuarios")
        if not self.body_scroll:
            return
        for w in self.body_scroll.winfo_children():
            w.destroy()

        self._encabezado_body("👥 GESTIÓN DE USUARIOS", "Administración por roles y filtrado rápido del personal")
        bar_tabs = ctk.CTkFrame(self.body_scroll, fg_color="transparent")
        bar_tabs.pack(fill="x", padx=10, pady=(0, 10))
        tabs_buttons = ctk.CTkFrame(bar_tabs, fg_color="transparent")
        tabs_buttons.pack(side="left")
        container_list = ctk.CTkFrame(self.body_scroll, fg_color="transparent")
        container_list.pack(fill="both", expand=True, padx=10)

        self.btn_tabs_dict = {}
        self.btn_registrar_container = None
        pestañas = [("Todos", "Todos"), ("Administrador", "Administrador"), ("Mecánicos", "Mecánico"), ("Clientes", "Cliente")]

        def seleccionar_tab(nombre_tab, rol_filtro):
            for name, b in self.btn_tabs_dict.items():
                if name == nombre_tab:
                    b.configure(fg_color=ROJO, text_color="#FFFFFF", hover_color=ROJO_H)
                else:
                    b.configure(fg_color=BTN_GRIS, text_color=("#111827", "#E0E0E0"), hover_color=BTN_GRIS_H)
            if self.btn_registrar_container:
                self.btn_registrar_container.destroy()
            self.btn_registrar_container = ctk.CTkFrame(bar_tabs, fg_color="transparent")
            self.btn_registrar_container.pack(side="right")
            if rol_filtro and rol_filtro != "Todos":
                ctk.CTkButton(self.btn_registrar_container, text=f"➕ Registrar {rol_filtro}", height=38, fg_color=ROJO,
                              hover_color=ROJO_H, font=("Calibri", 15, "bold"),
                              command=lambda r=rol_filtro: self.abrir_registro_integrado_por_rol(r)).pack()
            self.cargar_cards_usuarios(container_list, rol_filtro)

        for nombre_tab, rol_filtro in pestañas:
            b = ctk.CTkButton(tabs_buttons, text=nombre_tab, width=120, height=38, corner_radius=20, font=("Calibri", 15, "bold"),
                              command=lambda n=nombre_tab, r=rol_filtro: seleccionar_tab(n, r))
            b.pack(side="left", padx=4)
            self.btn_tabs_dict[nombre_tab] = b

        seleccionar_tab(pestaña_inicial, filtro_inicial)

    # =========================================================================
    # VEHÍCULOS
    # =========================================================================
    def abrir_registro_vehiculo(self):
        if not self.tiene_rol("administrador", "mecanico", "cliente"):
            return
        es_cliente = normalizar_rol(self.rol_actual) == "cliente"
        titulo = "🚘 Registrar Mi Vehículo" if es_cliente else "🚘 Registro de Vehículo"
        win, cuerpo = self.crear_ventana_flotante(titulo, 480, 470 if es_cliente else 545)

        txt_placa = self._campo(cuerpo, "Placa del Vehículo (requerida):", "Ej. ABC123")
        txt_marca = self._campo(cuerpo, "Marca:", "Ej. Chevrolet, Toyota, Mazda")
        txt_color = self._campo(cuerpo, "Color:", "Ej. Rojo, Negro, Blanco")
        txt_modelo = self._campo(cuerpo, "Modelo / Año:", "Ej. 2020")

        combo, dict_clientes = None, {}
        if not es_cliente:
            dict_clientes = self.obtener_lista_clientes()
            opciones = list(dict_clientes.keys())
            ctk.CTkLabel(cuerpo, text="Propietario / Cliente:", font=("Calibri", 15, "bold"), text_color=("#111827", "#FFFFFF")).pack(anchor="w")
            combo = ctk.CTkComboBox(cuerpo, height=38, values=opciones, font=("Calibri", 15), state="readonly")
            combo.set(opciones[0] if opciones else "Sin asignar")
            combo.pack(fill="x", pady=(2, 10))

        def guardar():
            placa = txt_placa.get().strip().upper()
            marca, color, mod = txt_marca.get().strip(), txt_color.get().strip(), txt_modelo.get().strip()

            if not re.fullmatch(r"[A-Z0-9]{5,7}", placa):
                messagebox.showwarning("Placa inválida ⚠️", "La placa debe tener entre 5 y 7 letras o números (Ej. ABC123).", parent=win)
                return
            if not marca:
                messagebox.showwarning("Campos Incompletos ⚠️", "La marca es obligatoria.", parent=win)
                return
            modelo = None
            if mod:
                if not (mod.isdigit() and 1950 <= int(mod) <= datetime.now().year + 1):
                    messagebox.showwarning("Año inválido ⚠️", "Ingrese un año válido (Ej. 2020).", parent=win)
                    return
                modelo = int(mod)

            id_cliente = self.id_usuario_actual if es_cliente else dict_clientes.get(combo.get() if combo else "Sin asignar")
            try:
                with conexion_db() as (con, cur):
                    cur.execute("INSERT INTO vehiculos (id_cliente, placa, marca, color, modelo) VALUES (%s, %s, %s, %s, %s)",
                                (id_cliente, placa, marca, color or None, modelo))
                    con.commit()
                self.registrar_log(f"Registró el vehículo placa {placa} ({marca})")
                messagebox.showinfo("¡Vehículo Registrado! 🚗", f"Placa: {placa}\nMarca: {marca}\nColor: {color or 'N/A'}\nModelo: {modelo or 'N/A'}", parent=win)
                win.destroy()
            except mysql.connector.IntegrityError:
                messagebox.showerror("Placa duplicada ❌", "Esa placa ya está registrada en el sistema.", parent=win)
            except mysql.connector.Error as err:
                messagebox.showerror("Error ❌", f"No se pudo registrar el vehículo:\n\n{err}", parent=win)

        self._barra_botones(cuerpo, "💾 Registrar Vehículo", guardar, win)

    def abrir_formulario_mantenimiento_embebido(self, id_vehiculo, placa):
        if not self.tiene_rol("administrador", "mecanico"):
            return
        win, cuerpo = self.crear_ventana_flotante(f"🛠 Registrar Trabajo ({placa})", 480, 600)

        ctk.CTkLabel(cuerpo, text="📅 Fecha en que se realizó el trabajo:", font=("Calibri", 15, "bold"), text_color=("#111827", "#FFFFFF")).pack(anchor="w")
        f_fecha = ctk.CTkFrame(cuerpo, fg_color="transparent")
        f_fecha.pack(fill="x", pady=(2, 10))

        hoy = datetime.now()
        combo_dia = ctk.CTkComboBox(f_fecha, values=[str(i).zfill(2) for i in range(1, 32)], width=80, height=36, state="readonly")
        combo_dia.set(str(hoy.day).zfill(2))
        combo_mes = ctk.CTkComboBox(f_fecha, values=[str(i).zfill(2) for i in range(1, 13)], width=80, height=36, state="readonly")
        combo_mes.set(str(hoy.month).zfill(2))
        combo_anio = ctk.CTkComboBox(f_fecha, values=[str(i) for i in range(hoy.year - 5, hoy.year + 1)], width=100, height=36, state="readonly")
        combo_anio.set(str(hoy.year))
        combo_dia.pack(side="left", padx=(0, 6))
        ctk.CTkLabel(f_fecha, text="/").pack(side="left", padx=(0, 6))
        combo_mes.pack(side="left", padx=(0, 6))
        ctk.CTkLabel(f_fecha, text="/").pack(side="left", padx=(0, 6))
        combo_anio.pack(side="left")

        ctk.CTkLabel(cuerpo, text="📝 Descripción del trabajo:", font=("Calibri", 15, "bold"), text_color=("#111827", "#FFFFFF")).pack(anchor="w")
        txt_desc = ctk.CTkTextbox(cuerpo, height=90, font=("Calibri", 14))
        txt_desc.pack(fill="x", pady=(2, 10))

        ctk.CTkLabel(cuerpo, text="🔍 Observaciones / Diagnóstico:", font=("Calibri", 15, "bold"), text_color=("#111827", "#FFFFFF")).pack(anchor="w")
        txt_obs = ctk.CTkTextbox(cuerpo, height=70, font=("Calibri", 14))
        txt_obs.pack(fill="x", pady=(2, 10))

        txt_costo = self._campo(cuerpo, "💰 Costo / Mano de obra ($ COP):", "Ej. 150000")

        def guardar():
            desc = txt_desc.get("1.0", "end").strip()
            obs = txt_obs.get("1.0", "end").strip()
            if not desc:
                messagebox.showwarning("Campo Vacío ⚠️", "Escriba la descripción del trabajo.", parent=win)
                return
            try:
                fecha = datetime(int(combo_anio.get()), int(combo_mes.get()), int(combo_dia.get()))
            except ValueError:
                messagebox.showwarning("Fecha inválida ⚠️", "La fecha seleccionada no existe.", parent=win)
                return
            if fecha.date() > datetime.now().date():
                messagebox.showwarning("Fecha inválida ⚠️", "La fecha no puede ser futura.", parent=win)
                return
            try:
                costo = float(txt_costo.get().strip().replace(",", "") or 0)
                if costo < 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("Costo inválido ⚠️", "Ingrese un costo numérico válido.", parent=win)
                return
            try:
                with conexion_db() as (con, cur):
                    cur.execute(
                        "INSERT INTO mantenimientos (id_vehiculo, id_mecanico, descripcion_trabajo, observaciones, costo, fecha_mantenimiento) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        (id_vehiculo, self.id_usuario_actual, desc, obs or None, costo, fecha.strftime("%Y-%m-%d")))
                    con.commit()
                self.registrar_log(f"Registró trabajo de mantenimiento en vehículo placa {placa}")
                messagebox.showinfo("¡Trabajo Registrado! 🛠️", "El mantenimiento fue guardado con éxito.", parent=win)
                win.destroy()
                self.buscar_vehiculo_por_placa(placa_predeterminada=placa)
            except mysql.connector.Error as err:
                messagebox.showerror("Error ❌", f"No se pudo guardar el trabajo:\n\n{err}", parent=win)

        self._barra_botones(cuerpo, "💾 Guardar Trabajo", guardar, win)

    # =========================================================================
    # BÚSQUEDA E HISTORIAL
    # =========================================================================
    def buscar_vehiculo_por_placa(self, placa_predeterminada=None):
        if not self.tiene_rol("administrador", "mecanico", "cliente"):
            return
        self.seleccionar_opcion_menu("buscar")
        if not self.body_scroll:
            return
        for w in self.body_scroll.winfo_children():
            w.destroy()

        rol = normalizar_rol(self.rol_actual)
        self._encabezado_body("🔎 BÚSQUEDA Y HISTORIAL DEL VEHÍCULO", "Consulte los detalles y el historial de trabajos realizados al automóvil")

        card = ctk.CTkFrame(self.body_scroll, fg_color=CARD_BG, corner_radius=16, border_width=1, border_color=CARD_BORDE)
        card.pack(padx=40, pady=10, fill="x")
        f_inner = ctk.CTkFrame(card, fg_color="transparent")
        f_inner.pack(padx=30, pady=25, fill="x")

        ctk.CTkLabel(f_inner, text="Ingrese la Placa a Consultar:", font=("Calibri", 16, "bold"), text_color=("#111827", "#FFF")).pack(anchor="w", pady=(0, 4))
        txt_p = ctk.CTkEntry(f_inner, height=46, placeholder_text="Ej. ABC123", font=("Calibri", 16))
        txt_p.pack(fill="x", pady=(0, 15))
        if placa_predeterminada:
            txt_p.insert(0, placa_predeterminada)

        res_container = ctk.CTkFrame(f_inner, fg_color="transparent")
        res_container.pack(fill="x", pady=(0, 15))
        frame_historial = ctk.CTkFrame(f_inner, fg_color="transparent")
        frame_historial.pack(fill="x")

        def consultar_bd():
            placa = txt_p.get().strip().upper()
            if not placa:
                messagebox.showwarning("Atención ⚠️", "Ingrese una placa válida.")
                return
            for w in res_container.winfo_children():
                w.destroy()
            for w in frame_historial.winfo_children():
                w.destroy()

            try:
                with conexion_db(True) as (con, cur):
                    sql = ("SELECT v.*, u.nombre_completo AS propietario, u.telefono AS tel_propietario "
                           "FROM vehiculos v LEFT JOIN usuarios u ON v.id_cliente = u.id_usuario WHERE v.placa = %s")
                    if rol == "cliente":
                        cur.execute(sql + " AND v.id_cliente = %s", (placa, self.id_usuario_actual))
                    else:
                        cur.execute(sql, (placa,))
                    v = cur.fetchone()

                    mantenimientos = []
                    if v:
                        cur.execute(
                            "SELECT m.*, u.nombre_completo AS mecanico FROM mantenimientos m "
                            "LEFT JOIN usuarios u ON m.id_mecanico = u.id_usuario WHERE m.id_vehiculo = %s "
                            "ORDER BY COALESCE(m.fecha_mantenimiento, m.fecha_registro) DESC", (v['id_vehiculo'],))
                        mantenimientos = cur.fetchall()
            except mysql.connector.Error as err:
                messagebox.showerror("Error ❌", f"Error de consulta:\n{err}")
                return

            self.registrar_log(f"Consultó el vehículo placa {placa}")

            if not v:
                err_box = ctk.CTkFrame(res_container, fg_color=("#FEF2F2", "#2B1718"), corner_radius=10, border_width=1, border_color="#FCA5A5")
                err_box.pack(fill="x", ipadx=10, ipady=10)
                ctk.CTkLabel(err_box, text=f"❌ No se encontró ningún vehículo registrado con la placa '{placa}'.",
                             font=("Calibri", 15, "bold"), text_color=ROJO).pack(anchor="w", padx=15)
                return

            info_box = ctk.CTkFrame(res_container, fg_color=("#F3F4F6", "#141418"), corner_radius=12, border_width=1, border_color=CARD_BORDE)
            info_box.pack(fill="x", ipadx=10, ipady=10)

            def badge(parent, icono, titulo, valor):
                item = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=8, border_width=1, border_color=CARD_BORDE)
                item.pack(side="left", fill="x", expand=True, padx=4)
                ctk.CTkLabel(item, text=f"{icono} {titulo}:", font=("Calibri", 13, "bold"), text_color=("#6B7280", "#9CA3AF")).pack(anchor="w", padx=10, pady=(6, 0))
                ctk.CTkLabel(item, text=str(valor), font=("Calibri", 15, "bold"), text_color=TXT_T).pack(anchor="w", padx=10, pady=(0, 6))

            f1 = ctk.CTkFrame(info_box, fg_color="transparent")
            f1.pack(fill="x", pady=4, padx=10)
            badge(f1, "🚗", "Placa", v['placa'])
            badge(f1, "🚘", "Marca", v['marca'])
            badge(f1, "🎨", "Color", v['color'] or "N/A")
            badge(f1, "📅", "Modelo / Año", v['modelo'] or "N/A")
            f2 = ctk.CTkFrame(info_box, fg_color="transparent")
            f2.pack(fill="x", pady=4, padx=10)
            badge(f2, "👤", "Cliente Propietario", v['propietario'] or "Sin asignación directa")
            badge(f2, "📱", "Teléfono Contacto", v['tel_propietario'] or "N/A")

            titulo_hist = "📜 HISTORIAL DE TRABAJOS REGISTRADOS"
            if rol in ("mecanico", "administrador"):
                barra = ctk.CTkFrame(frame_historial, fg_color="transparent")
                barra.pack(fill="x", pady=(15, 10))
                ctk.CTkLabel(barra, text=titulo_hist, font=("Calibri", 18, "bold"), text_color=TXT_T).pack(side="left")
                ctk.CTkButton(barra, text="➕ Registrar Nuevo Trabajo", height=38, fg_color=ROJO, hover_color=ROJO_H, font=("Calibri", 15, "bold"),
                              command=lambda: self.abrir_formulario_mantenimiento_embebido(v['id_vehiculo'], v['placa'])).pack(side="right")
            else:
                ctk.CTkLabel(frame_historial, text=titulo_hist, font=("Calibri", 18, "bold"), text_color=TXT_T).pack(anchor="w", pady=(15, 10))

            if not mantenimientos:
                ctk.CTkLabel(frame_historial, text="No se han registrado trabajos o mantenimientos previos para este vehículo.",
                             font=("Calibri", 15), text_color=("#6B7280", "#9CA3AF")).pack(anchor="w", pady=10)
                return

            tabla = ctk.CTkFrame(frame_historial, fg_color=("#FFFFFF", "#18181C"), corner_radius=12, border_width=1, border_color=CARD_BORDE)
            tabla.pack(fill="x", pady=5)
            header = ctk.CTkFrame(tabla, fg_color=("#F3F4F6", "#25252A"), corner_radius=8)
            header.pack(fill="x", padx=6, pady=6)
            for col in ["📅 FECHA", "🛠️ MECÁNICO", "📝 DESCRIPCIÓN DEL TRABAJO", "🔍 OBSERVACIONES", "💰 COSTO"]:
                ctk.CTkLabel(header, text=col, font=("Calibri", 13, "bold"), text_color=("#374151", "#E5E7EB"), anchor="w").pack(side="left", fill="x", expand=True, padx=8, pady=8)

            for i, m in enumerate(mantenimientos):
                row = ctk.CTkFrame(tabla, fg_color=("#FFFFFF", "#1E1E22") if i % 2 == 0 else ("#F9FAFB", "#16161A"))
                row.pack(fill="x", padx=6, pady=2)
                fecha = m['fecha_mantenimiento'] if m['fecha_mantenimiento'] else str(m['fecha_registro']).split()[0]
                costo = f"${float(m['costo']):,.0f} COP" if m['costo'] and float(m['costo']) > 0 else "N/A"
                datos = [
                    (str(fecha), ("#111827", "#F9FAFB")),
                    (m['mecanico'] or "Taller General", ("#D32F2F", "#FF5252")),
                    (m['descripcion_trabajo'], ("#111827", "#E5E7EB")),
                    (m['observaciones'] or "Sin observaciones", ("#6B7280", "#9CA3AF")),
                    (costo, ("#2E7D32", "#81C784")),
                ]
                for txt, color in datos:
                    ctk.CTkLabel(row, text=txt, font=("Calibri", 13), text_color=color, anchor="w", justify="left", wraplength=180).pack(side="left", fill="x", expand=True, padx=8, pady=8)

        ctk.CTkButton(f_inner, text="🔍 Buscar Vehículo", height=46, fg_color=ROJO, hover_color=ROJO_H, font=("Calibri", 16, "bold"), command=consultar_bd).pack(fill="x")
        txt_p.bind("<Return>", lambda e: consultar_bd())
        if placa_predeterminada:
            consultar_bd()

    # =========================================================================
    # CIERRE DE CAJA Y CITAS
    # =========================================================================
    def abrir_cierre_caja(self):
        if not self.tiene_rol("mecanico"):
            return
        total, n, aviso = 0.0, 0, ""
        try:
            with conexion_db(True) as (con, cur):
                cur.execute(
                    "SELECT COALESCE(SUM(costo), 0) AS total, COUNT(*) AS n FROM mantenimientos "
                    "WHERE DATE(fecha_mantenimiento) = CURDATE() AND id_mecanico = %s", (self.id_usuario_actual,))
                r = cur.fetchone()
                total, n = float(r['total']), int(r['n'])
        except mysql.connector.Error:
            aviso = "No se pudieron leer los totales del día."

        win, cuerpo = self.crear_ventana_flotante("💵 Cierre de Caja Diario", 480, 460)
        ctk.CTkLabel(cuerpo, text="💰 Total cobrado hoy (sus trabajos):", font=("Calibri", 16, "bold"), text_color=("#111827", "#FFF")).pack(anchor="w")
        ctk.CTkLabel(cuerpo, text=f"$ {total:,.0f} COP", font=("Calibri", 34, "bold"), text_color="#2E7D32").pack(anchor="w", pady=(2, 12))
        ctk.CTkLabel(cuerpo, text=f"🚗 Trabajos registrados hoy: {n}", font=("Calibri", 16, "bold"), text_color=("#374151", "#DDD")).pack(anchor="w", pady=4)
        ctk.CTkLabel(cuerpo, text=f"📅 Fecha: {datetime.now().strftime('%d/%m/%Y')}", font=("Calibri", 15), text_color=TXT_S).pack(anchor="w", pady=4)
        if aviso:
            ctk.CTkLabel(cuerpo, text=aviso, font=("Calibri", 13), text_color=ROJO).pack(anchor="w", pady=4)

        def realizar_cierre():
            self.registrar_log(f"Realizó el Cierre de Caja Diario (${total:,.0f} COP, {n} trabajos)")
            messagebox.showinfo("Cierre Guardado 💵", "El cierre de caja ha sido registrado exitosamente.", parent=win)
            win.destroy()

        self._barra_botones(cuerpo, "🔒 Finalizar Caja", realizar_cierre, win)

    def abrir_agendar_cita(self):
        if not self.tiene_rol("cliente"):
            return
        win, cuerpo = self.crear_ventana_flotante("📅 Agendar Cita en el Taller", 480, 460)
        txt_placa = self._campo(cuerpo, "Placa de su vehículo:", "Ej. ABC123")
        txt_fecha = self._campo(cuerpo, "Fecha deseada:", "DD/MM/AAAA")
        txt_motivo = self._campo(cuerpo, "Motivo de la revisión:", "Ej. Falla de frenos, ruido en motor")

        def confirmar():
            placa = txt_placa.get().strip().upper()
            motivo = txt_motivo.get().strip()
            if not placa or not txt_fecha.get().strip() or not motivo:
                messagebox.showwarning("Campos Incompletos ⚠️", "Ingrese placa, fecha y motivo.", parent=win)
                return
            try:
                fecha = datetime.strptime(txt_fecha.get().strip(), "%d/%m/%Y").date()
            except ValueError:
                messagebox.showwarning("Fecha inválida ⚠️", "Use el formato DD/MM/AAAA.", parent=win)
                return
            if fecha < datetime.now().date():
                messagebox.showwarning("Fecha inválida ⚠️", "La fecha no puede ser anterior a hoy.", parent=win)
                return
            try:
                with conexion_db(True) as (con, cur):
                    cur.execute("SELECT id_vehiculo FROM vehiculos WHERE placa = %s AND id_cliente = %s", (placa, self.id_usuario_actual))
                    if not cur.fetchone():
                        messagebox.showerror("Vehículo no encontrado ❌", "Esa placa no está registrada a su nombre.", parent=win)
                        return
                    cur.execute("INSERT INTO citas (id_cliente, placa, fecha_cita, motivo) VALUES (%s, %s, %s, %s)",
                                (self.id_usuario_actual, placa, fecha.strftime("%Y-%m-%d"), motivo))
                    con.commit()
                self.registrar_log(f"Solicitó cita técnica para vehículo placa {placa} en la fecha {fecha.strftime('%d/%m/%Y')}")
                messagebox.showinfo("Cita Solicitada 📅", f"Su cita para la placa {placa} el día {fecha.strftime('%d/%m/%Y')} quedó registrada.", parent=win)
                win.destroy()
            except mysql.connector.Error as err:
                messagebox.showerror("Error ❌", f"No se pudo registrar la cita:\n\n{err}", parent=win)

        self._barra_botones(cuerpo, "📅 Confirmar Cita", confirmar, win)

    # =========================================================================
    # PANEL PRINCIPAL Y DASHBOARD
    # =========================================================================
    def mostrar_inicio(self):
        for attr in ("frame_login", "frame_registro"):
            f = getattr(self, attr)
            if f:
                f.destroy()
                setattr(self, attr, None)

        self.btn_theme_login.place_forget()
        self.footer.place_forget()
        self.card_main.place_forget()

        self.frame_inicio = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_inicio.pack(fill="both", expand=True)
        self.actualizar_visibilidad_fondo()

        rol_norm = normalizar_rol(self.rol_actual)

        self.sidebar = ctk.CTkFrame(self.frame_inicio, width=260, corner_radius=0, fg_color=("#FFFFFF", "#121215"))
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        img_l = self._logo(130)
        if img_l:
            ctk.CTkLabel(self.sidebar, image=img_l, text="").pack(pady=(20, 15))

        self.btn_menu_activos = {}
        inicio = ("inicio", "🏠  Inicio", lambda: self.mostrar_inicio_dashboard(self.rol_actual))

        if rol_norm == "administrador":
            menu = [inicio,
                    ("vehiculos", "🚗  Registrar Vehículo", self.abrir_registro_vehiculo),
                    ("buscar", "🔎  Buscar Vehículo", self.buscar_vehiculo_por_placa),
                    ("usuarios", "👥  Usuarios", lambda: self.mostrar_lista_usuarios("Todos", "Todos")),
                    ("logs", "📜  Auditoría", self.mostrar_historial_logs)]
        elif rol_norm == "mecanico":
            menu = [inicio,
                    ("vehiculos", "🚗  Recepcion Carro", self.abrir_registro_vehiculo),
                    ("buscar", "🔎  Buscar Vehículo", self.buscar_vehiculo_por_placa),
                    ("caja", "💵  Cierre Caja", self.abrir_cierre_caja)]
        else:
            menu = [inicio,
                    ("vehiculos", "🚗  Registrar Mi Vehículo", self.abrir_registro_vehiculo),
                    ("buscar", "🔎  Mi Vehículo", self.buscar_vehiculo_por_placa),
                    ("citas", "📅  Agendar Cita", self.abrir_agendar_cita)]

        for clave, texto, comando in menu:
            btn = ctk.CTkButton(self.sidebar, text=texto, anchor="w", height=46, corner_radius=8, fg_color="transparent",
                                text_color=("#222222", "#E0E0E0"), font=("Calibri", 15, "bold"), command=comando)
            btn.pack(fill="x", padx=12, pady=3)
            self.btn_menu_activos[clave] = btn

        bottom = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=12, pady=20)
        ctk.CTkButton(bottom, text="☀️ / 🌙", anchor="center", height=40, corner_radius=8, fg_color=("#E5E7EB", "#1E1E22"),
                      text_color=("#111827", "#FFFFFF"), hover_color=("#D1D5DB", "#2B2B30"), font=("Segoe UI Emoji", 15, "bold"),
                      command=self.cambiar_tema).pack(fill="x", pady=(0, 8))
        ctk.CTkButton(bottom, text="🚪  Cerrar Sesión", anchor="w", height=44, corner_radius=8, fg_color="transparent",
                      hover_color=("#F5F5F5", "#2B2B2B"), text_color=("#222222", "#E0E0E0"), font=("Calibri", 15, "bold"),
                      command=self.cerrar_sesion).pack(fill="x")

        main_content = ctk.CTkFrame(self.frame_inicio, fg_color="transparent")
        main_content.pack(side="right", fill="both", expand=True, padx=25, pady=20)

        top_bar = ctk.CTkFrame(main_content, fg_color="transparent")
        top_bar.pack(fill="x", pady=(0, 15))
        user_header = ctk.CTkFrame(top_bar, fg_color="transparent")
        user_header.pack(side="left")
        ctk.CTkLabel(user_header, text="👤", font=("Segoe UI Emoji", 24), text_color=ROJO).pack(side="left", padx=(0, 10))
        info = ctk.CTkFrame(user_header, fg_color="transparent")
        info.pack(side="left")
        ctk.CTkLabel(info, text=f"¡Bienvenido, {self.usuario_actual}!", font=("Calibri", 22, "bold"), text_color=("#111827", "#FFFFFF")).pack(anchor="w")
        ctk.CTkLabel(info, text=f"Panel ejecutivo - Rol: {str(self.rol_actual).strip().capitalize()}", font=("Calibri", 14),
                     text_color=("#6B7280", "#AAAAAA")).pack(anchor="w")

        self.body_scroll = ctk.CTkScrollableFrame(main_content, fg_color="transparent")
        self.body_scroll.pack(fill="both", expand=True)
        self.mostrar_inicio_dashboard(self.rol_actual)

    def mostrar_inicio_dashboard(self, rol_param):
        if not self.body_scroll:
            return
        self.seleccionar_opcion_menu("inicio")
        for w in self.body_scroll.winfo_children():
            w.destroy()

        rol_norm = normalizar_rol(self.rol_actual)
        if rol_norm == "administrador":
            vista = VistaAdministrador(self.body_scroll, self)
        elif rol_norm == "mecanico":
            vista = VistaMecanico(self.body_scroll, self)
        else:
            vista = VistaCliente(self.body_scroll, self)
        vista.pack(fill="both", expand=True)

    # =========================================================================
    # CIERRE DE SESIÓN
    # =========================================================================
    def cerrar_sesion_forzado(self):
        """Limpia la vista y regresa a la pantalla de Inicio de Sesión (Login)."""
        self.cerrar_modal_desbloqueo()
        self.cerrar_ventanas_flotantes()

        if self.frame_inicio:
            self.frame_inicio.destroy()
        self.frame_inicio = None
        self.body_scroll = None
        self.btn_menu_activos = {}

        self.usuario_actual = ""
        self.rol_actual = ""
        self.id_usuario_actual = None
        self.token_sesion_actual = None
        self.bloqueo_pantalla_activo = False

        self.mostrar_login()

    def cerrar_sesion(self):
        if messagebox.askyesno("Cerrar Sesión 🚪", "¿Desea cerrar la sesión actual?"):
            self.registrar_log("Cerró la sesión")
            self.cerrar_sesion_forzado()


if __name__ == "__main__":
    app = AppTallerAutomotriz()
    app.mainloop()