import customtkinter as ctk
from tkinter import messagebox
from PIL import Image
import mysql.connector
import hashlib
import os

ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("red")

class LoginTallerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Configuración de la ventana principal
        self.title("TALLER AUTOMOTRIZ I.G - Software de Gestión (100% Offline)")
        self.geometry("1024x650")
        self.resizable(False, False)

        # RUTAS EXACTAS DE TUS IMÁGENES
        self.ruta_fondo = r"C:\Users\karol\Downloads\Taller Automotriz I.G\fondo.png"
        self.ruta_logo = r"C:\Users\karol\Downloads\Taller Automotriz I.G\Logo.png"

        # --- 1. IMAGEN DE FONDO (Si existe, la coloca ocupando toda la ventana) ---
        if os.path.exists(self.ruta_fondo):
            img_bg = ctk.CTkImage(light_image=Image.open(self.ruta_fondo), size=(1024, 650))
            self.lbl_bg = ctk.CTkLabel(self, image=img_bg, text="")
            self.lbl_bg.place(x=0, y=0, relwidth=1, relheight=1)

        # --- CONTENEDOR PRINCIPAL (SOBRE EL FONDO) ---
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True, padx=40, pady=20)

        # =====================================================================
        # SECCIÓN IZQUIERDA: LOGO E IDENTIDAD VISUAL
        # =====================================================================
        self.left_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.left_frame.pack(side="left", fill="both", expand=True, padx=(20, 10))

        # Tira superior de marcas
        self.lbl_marcas = ctk.CTkLabel(
            self.left_frame, 
            text="CHEVROLET  •  NISSAN  •  MAZDA  •  RENAULT  •  KIA  •  TOYOTA  •  MITSUBISHI",
            font=("Calibri", 11, "bold"),
            text_color="#555555"
        )
        self.lbl_marcas.pack(pady=(10, 20))

        # Carga del Logo del Taller
        if os.path.exists(self.ruta_logo):
            img_logo_obj = Image.open(self.ruta_logo)
            img_logo = ctk.CTkImage(light_image=img_logo_obj, size=(340, 340))
            self.lbl_logo = ctk.CTkLabel(self.left_frame, image=img_logo, text="")
        else:
            self.lbl_logo = ctk.CTkLabel(
                self.left_frame, 
                text="⚙️\nTALLER AUTOMOTRIZ I.G\nSOFTWARE DE GESTIÓN", 
                font=("Impact", 28), 
                text_color="#D32F2F"
            )
        self.lbl_logo.pack(pady=10)

        # =====================================================================
        # SECCIÓN DERECHA: TARJETA DE INICIO DE SESIÓN
        # =====================================================================
        self.right_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.right_frame.pack(side="right", fill="both", expand=True, padx=(10, 20))

        # Card Blanca Flotante
        self.card_login = ctk.CTkFrame(
            self.right_frame, 
            width=380, 
            height=470, 
            corner_radius=15,
            fg_color="#FFFFFF",
            border_width=1,
            border_color="#E0E0E0"
        )
        self.card_login.place(relx=0.5, rely=0.5, anchor="center")
        self.card_login.pack_propagate(False)

        # Ícono Rojo y Títulos
        self.lbl_user_icon = ctk.CTkLabel(self.card_login, text="👤", font=("Segoe UI Emoji", 35), text_color="#D32F2F")
        self.lbl_user_icon.pack(pady=(25, 5))

        self.lbl_titulo = ctk.CTkLabel(
            self.card_login, 
            text="INICIO DE SESIÓN", 
            font=("Calibri", 20, "bold"),
            text_color="#111111"
        )
        self.lbl_titulo.pack(pady=(0, 2))

        self.lbl_subtitulo = ctk.CTkLabel(
            self.card_login, 
            text="Ingrese sus credenciales para acceder\nal sistema", 
            font=("Calibri", 11),
            text_color="#666666"
        )
        self.lbl_subtitulo.pack(pady=(0, 20))

        # Campo Usuario
        self.txt_usuario = ctk.CTkEntry(
            self.card_login, 
            width=300, 
            height=42, 
            corner_radius=8,
            placeholder_text="👤  Usuario",
            font=("Calibri", 13),
            fg_color="#FAFAFA",
            border_color="#CCCCCC"
        )
        self.txt_usuario.pack(pady=(0, 12))

        # Campo Contraseña
        self.txt_password = ctk.CTkEntry(
            self.card_login, 
            width=300, 
            height=42, 
            corner_radius=8,
            placeholder_text="🔒  Contraseña",
            show="•",
            font=("Calibri", 13),
            fg_color="#FAFAFA",
            border_color="#CCCCCC"
        )
        self.txt_password.pack(pady=(0, 20))

        # Botón Iniciar Sesión Rojo
        self.btn_login = ctk.CTkButton(
            self.card_login, 
            text="➔  INICIAR SESIÓN", 
            width=300, 
            height=44, 
            corner_radius=8,
            fg_color="#D32F2F", 
            hover_color="#B71C1C",
            font=("Calibri", 13, "bold"),
            command=self.validar_login
        )
        self.btn_login.pack(pady=(0, 15))

        # Mensaje de Seguridad
        self.lbl_seguridad = ctk.CTkLabel(
            self.card_login, 
            text="🛡️ Acceso seguro y protegido", 
            font=("Calibri", 10),
            text_color="#777777"
        )
        self.lbl_seguridad.pack(side="bottom", pady=15)

        # =====================================================================
        # PIE DE PÁGINA GENERAL
        # =====================================================================
        self.footer = ctk.CTkLabel(
            self, 
            text="⚙️ TALLER AUTOMOTRIZ I.G - SOFTWARE DE GESTIÓN | Sistema 100% Offline", 
            font=("Calibri", 10, "bold"),
            text_color="#444444"
        )
        self.footer.pack(side="bottom", pady=10)

    # Lógica de Validación con MySQL XAMPP
    def validar_login(self):
        usuario_input = self.txt_usuario.get().strip()
        pass_input = self.txt_password.get().strip()

        if not usuario_input or not pass_input:
            messagebox.showwarning("Atención", "Por favor complete todos los campos.")
            return

        pass_hash = hashlib.sha256(pass_input.encode()).hexdigest()

        try:
            conexion = mysql.connector.connect(
                host="localhost",
                user="root",
                password="",
                database="taller_automotriz_db",
                port=3306
            )
            cursor = conexion.cursor(dictionary=True)

            query = "SELECT id_usuario, nombre_completo, rol, password_hash FROM usuarios WHERE usuario = %s AND estado = 'Activo'"
            cursor.execute(query, (usuario_input,))
            user = cursor.fetchone()

            if user and user['password_hash'] == pass_hash:
                messagebox.showinfo("Acceso Concedido", f"Bienvenido/a {user['nombre_completo']}\nRol: {user['rol']}")
                self.destroy()
            else:
                messagebox.showerror("Error", "Usuario o contraseña incorrectos.")

            cursor.close()
            conexion.close()

        except mysql.connector.Error as err:
            messagebox.showerror("Error BD", f"Error de conexión con XAMPP:\n{err}")

if __name__ == "__main__":
    app = LoginTallerApp()
    app.mainloop()