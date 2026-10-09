import hashlib
import hmac
import re
import secrets
import time

import bcrypt
import customtkinter as ctk
from tkinter import messagebox

# Parámetros de seguridad (ajustables en un solo lugar)
MAX_INTENTOS_LOGIN = 5
BLOQUEO_MINUTOS = 5
CODIGO_VIGENCIA_SEG = 300      # el código de recuperación vive 5 minutos
CODIGO_MAX_INTENTOS = 3


class CodigoRecuperacion:
    """Código de 6 dígitos con vencimiento y límite de intentos."""

    def __init__(self, id_usuario):
        self.id_usuario = id_usuario
        self.codigo = f"{secrets.randbelow(1_000_000):06d}"   # criptográficamente seguro
        self.creado = time.time()
        self.intentos = 0

    def verificar(self, ingresado: str) -> str:
        """Devuelve: 'ok', 'incorrecto', 'expirado' o 'agotado'."""
        if time.time() - self.creado > CODIGO_VIGENCIA_SEG:
            return "expirado"
        if self.intentos >= CODIGO_MAX_INTENTOS:
            return "agotado"
        self.intentos += 1
        if hmac.compare_digest(ingresado.strip(), self.codigo):
            return "ok"
        return "agotado" if self.intentos >= CODIGO_MAX_INTENTOS else "incorrecto"


class SeguridadService:

    # ------------------------------------------------------------------
    # HASHING (bcrypt + compatibilidad con hashes SHA-256 antiguos)
    # ------------------------------------------------------------------
    @staticmethod
    def hashear(clave: str) -> str:
        return bcrypt.hashpw(clave.encode("utf-8"), bcrypt.gensalt(12)).decode("utf-8")

    @staticmethod
    def es_legacy(almacenado: str) -> bool:
        """True si el hash guardado es SHA-256 (sin sal) y debe migrarse."""
        return not almacenado.startswith("$2")

    @staticmethod
    def verificar(clave: str, almacenado: str) -> bool:
        try:
            if almacenado.startswith("$2"):
                return bcrypt.checkpw(clave.encode("utf-8"), almacenado.encode("utf-8"))
            legacy = hashlib.sha256(clave.encode("utf-8")).hexdigest()
            return hmac.compare_digest(legacy, almacenado)
        except ValueError:
            return False

    # ------------------------------------------------------------------
    # VALIDACIONES DE ENTRADA
    # ------------------------------------------------------------------
    @staticmethod
    def validar_password(clave: str):
        """Devuelve lista de errores (vacía si la clave es válida)."""
        errores = []
        if len(clave) < 8:
            errores.append("• La contraseña debe tener al menos 8 caracteres.")
        if len(clave.encode("utf-8")) > 72:
            errores.append("• La contraseña es demasiado larga (máx. 72 bytes).")
        if not re.search(r"[A-Za-z]", clave):
            errores.append("• La contraseña debe incluir al menos una letra.")
        if not re.search(r"\d", clave):
            errores.append("• La contraseña debe incluir al menos un número.")
        return errores

    @staticmethod
    def validar_correo(correo: str) -> bool:
        return re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", correo) is not None

    @staticmethod
    def validar_telefono(tel: str) -> bool:
        return tel.isdigit() and len(tel) == 10

    @staticmethod
    def validar_usuario(usr: str) -> bool:
        return re.fullmatch(r"[A-Za-z0-9_.-]{4,30}", usr) is not None

    # ------------------------------------------------------------------
    # HONEYPOT
    # ------------------------------------------------------------------
    @staticmethod
    def validar_honeypot(entry_honeypot) -> bool:
        """True si un bot llenó el campo invisible. Rechaza en silencio."""
        return entry_honeypot.get().strip() != ""

    # ------------------------------------------------------------------
    # UTILIDAD DE VENTANAS
    # ------------------------------------------------------------------
    @staticmethod
    def centrar_ventana(win, ancho: int, alto: int):
        x = (win.winfo_screenwidth() - ancho) // 2
        y = (win.winfo_screenheight() - alto) // 2
        win.geometry(f"{ancho}x{alto}+{x}+{y}")

    # ------------------------------------------------------------------
    # POLÍTICA DE DATOS (LEY 1581 DE 2012)
    # ------------------------------------------------------------------
    @staticmethod
    def mostrar_modal_politica_datos(parent, callback_exito):
        win_pol = ctk.CTkToplevel(parent)
        win_pol.title("Tratamiento de Datos Personales")
        win_pol.resizable(False, False)
        SeguridadService.centrar_ventana(win_pol, 540, 520)
        win_pol.transient(parent)
        win_pol.after(150, win_pol.grab_set)   # el retardo evita un bug de CTkToplevel en Windows

        ctk.CTkLabel(
            win_pol,
            text="📋 POLÍTICA DE DATOS PERSONALES",
            font=("Calibri", 20, "bold"),
            text_color="#D32F2F",
        ).pack(pady=(20, 10))

        txt_pol = ctk.CTkTextbox(win_pol, width=480, height=240, font=("Calibri", 13), wrap="word")
        txt_pol.pack(padx=20, pady=(0, 15))

        texto_ley = (
            "En cumplimiento de la Ley Estatutaria 1581 de 2012 de Protección de Datos Personales "
            "(Hábeas Data) en Colombia, TALLER AUTOMOTRIZ I.G le informa que los datos personales "
            "recabados (nombre, teléfono, correo y datos del vehículo) serán tratados de manera "
            "confidencial y con la única finalidad de:\n\n"
            "1. Gestionar el ingreso y registro de órdenes de trabajo de su vehículo.\n"
            "2. Notificarle estados de reparación y agendamiento de citas.\n"
            "3. Llevar un historial técnico de mantenimientos preventivos y correctivos.\n\n"
            "Usted tiene derecho a conocer, actualizar, rectificar y solicitar la supresión de sus "
            "datos de nuestras bases de datos en cualquier momento."
        )
        txt_pol.insert("1.0", texto_ley)
        txt_pol.configure(state="disabled")

        var_chk = ctk.IntVar(value=0)

        def toggle_boton():
            if var_chk.get() == 1:
                btn_acep.configure(state="normal", fg_color="#D32F2F", hover_color="#B71C1C")
            else:
                btn_acep.configure(state="disabled", fg_color="#888888")

        ctk.CTkCheckBox(
            win_pol,
            text="He leído y acepto la Política de Tratamiento de Datos Personales",
            variable=var_chk,
            command=toggle_boton,
            font=("Calibri", 13, "bold"),
            fg_color="#D32F2F",
            checkmark_color="#FFFFFF",
        ).pack(pady=(0, 20), padx=25, anchor="w")

        def confirmar():
            win_pol.destroy()
            callback_exito()

        btn_acep = ctk.CTkButton(
            win_pol,
            text="Aceptar y Continuar ➔",
            height=44,
            width=480,
            fg_color="#888888",
            state="disabled",
            font=("Calibri", 16, "bold"),
            command=confirmar,
        )
        btn_acep.pack()