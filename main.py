import customtkinter as ctk
from tkinter import messagebox, Canvas
from PIL import Image, ImageDraw
import mysql.connector
import hashlib
import os
import random
from datetime import datetime

ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("dark-blue")

class AppTallerAutomotriz(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("TALLER AUTOMOTRIZ I.G - Software de Gestión")
        self.after(0, lambda: self.wm_state('zoomed'))

        self.ruta_fondo_claro = "fondo.png"
        posibles_fondos = [
            "fondo pantalla.png", "fondo pantalla.jpg", 
            "fondo_pantalla.png", "fondo_pantalla.jpg",
            "fondo Oscuro.png", "fondo Oscuro.jpg", 
            "fondo_oscuro.png", "fondo_oscuro.jpg"
        ]
        
        self.ruta_fondo_oscuro = "fondo.png"
        for f in posibles_fondos:
            if os.path.exists(f):
                self.ruta_fondo_oscuro = f
                break

        self.ruta_logo = "Logo.png"

       
        self.usuario_actual = ""
        self.rol_actual = ""
        self.id_usuario_actual = None
        self.codigo_verificacion_generado = None
        self.id_usuario_recuperando = None

        self.frame_login = None
        self.frame_registro = None
        self.frame_inicio = None
        self.body_scroll = None
        self.btn_menu_activos = {}

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
            self, text="☀️ / 🌙 Tema", width=110, height=36,
            fg_color=("#E5E7EB", "#2A2D34"), text_color=("#111827", "#F9FAFB"),
            hover_color=("#D1D5DB", "#374151"), font=("Calibri", 13, "bold"),
            command=self.cambiar_tema
        )
        self.btn_theme_login.place(relx=0.03, rely=0.96, anchor="w")

        self.footer = ctk.CTkFrame(
            self, fg_color=("#FFFFFF", "#1E1E1E"), corner_radius=10, border_width=1, border_color=("#D1D5DB", "#2A2D34")
        )
        self.lbl_footer_text = ctk.CTkLabel(
            self.footer, text="⚙️ TALLER AUTOMOTRIZ I.G - SOFTWARE DE GESTIÓN",
            font=("Calibri", 15, "bold"), text_color="#D32F2F"
        )
        self.lbl_footer_text.pack(padx=24, pady=8)
        self.footer.place(relx=0.5, rely=0.96, anchor="center")

        self.actualizar_visibilidad_fondo()
        self.mostrar_login()

    def cambiar_tema(self):
        modo_actual = ctk.get_appearance_mode()
        nuevo_modo = "Dark" if modo_actual == "Light" else "Light"
        ctk.set_appearance_mode(nuevo_modo)
        
        self.actualizar_visibilidad_fondo()

        if self.btn_menu_activos:
            for clave in self.btn_menu_activos:
                if self.btn_menu_activos[clave].cget("fg_color") not in ["transparent", ("transparent", "transparent")]:
                    self.seleccionar_opcion_menu(clave)
                    break

    def actualizar_visibilidad_fondo(self):
        if not hasattr(self, 'lbl_bg'):
            return

        modo_actual = ctk.get_appearance_mode()
        ruta_usar = self.ruta_fondo_oscuro if modo_actual == "Dark" and os.path.exists(self.ruta_fondo_oscuro) else self.ruta_fondo_claro

        if os.path.exists(ruta_usar):
            ancho_p = self.winfo_screenwidth()
            alto_p = self.winfo_screenheight()
            
            img_bg_obj = Image.open(ruta_usar).resize((ancho_p, alto_p), Image.Resampling.LANCZOS)
            self.img_bg_ctk = ctk.CTkImage(light_image=img_bg_obj, dark_image=img_bg_obj, size=(ancho_p, alto_p))
            self.lbl_bg.configure(image=self.img_bg_ctk)
            self.lbl_bg.place(x=0, y=0, relwidth=1, relheight=1)
            self.lbl_bg.lower()

    def hacer_imagen_circular(self, ruta_img, tamano):
        img_original = Image.open(ruta_img).convert("RGBA").resize(tamano, Image.Resampling.LANCZOS)
        mascara = Image.new("L", tamano, 0)
        draw = ImageDraw.Draw(mascara)
        draw.ellipse((0, 0, tamano[0], tamano[1]), fill=255)
        resultado = Image.new("RGBA", tamano, (255, 255, 255, 0))
        resultado.paste(img_original, (0, 0), mascara)
        return resultado

    def registrar_log(self, accion):
        try:
            conexion = mysql.connector.connect(host="localhost", user="root", password="", database="taller_automotriz_db", port=3306)
            cursor = conexion.cursor()
            sql = "INSERT INTO logs_sistema (usuario, rol, accion) VALUES (%s, %s, %s)"
            cursor.execute(sql, (self.usuario_actual if self.usuario_actual else "Sistema/Anonimo", self.rol_actual if self.rol_actual else "Invitado", accion))
            conexion.commit()
            cursor.close()
            conexion.close()
        except mysql.connector.Error as err:
            print(f"Error registrando log: {err}")

    def obtener_conteo_real(self, consulta_sql):
        try:
            conexion = mysql.connector.connect(host="localhost", user="root", password="", database="taller_automotriz_db", port=3306)
            cursor = conexion.cursor()
            cursor.execute(consulta_sql)
            res = cursor.fetchone()
            cursor.close()
            conexion.close()
            return int(res[0]) if res and res[0] is not None else 0
        except mysql.connector.Error:
            return 0

    def obtener_lista_clientes(self):
        clientes_dict = {"Sin asignar": None}
        try:
            conexion = mysql.connector.connect(host="localhost", user="root", password="", database="taller_automotriz_db", port=3306)
            cursor = conexion.cursor(dictionary=True)
            cursor.execute("SELECT id_usuario, nombre_completo, usuario FROM usuarios WHERE LOWER(rol) LIKE '%cliente%'")
            rows = cursor.fetchall()
            for r in rows:
                label = f"#{r['id_usuario']} - {r['nombre_completo']} ({r['usuario']})"
                clientes_dict[label] = r['id_usuario']
            cursor.close()
            conexion.close()
        except mysql.connector.Error:
            pass
        return clientes_dict

    def seleccionar_opcion_menu(self, clave_opcion):
        modo = ctk.get_appearance_mode()
        for clave, btn in self.btn_menu_activos.items():
            if clave == clave_opcion:
                if modo == "Light":
                    btn.configure(fg_color="#FFF0F0", text_color="#D32F2F", hover_color="#FFE0E0")
                else:
                    btn.configure(fg_color="#2B1819", text_color="#FF5252", hover_color="#3A2022")
            else:
                btn.configure(fg_color="transparent", text_color=("#222222", "#E0E0E0"), hover_color=("#F5F5F5", "#2B2B2B"))

    # =========================================================================
    # LOGIN & RECUPERACIÓN (RESTAURADA LÍNEA ROJA)
    # =========================================================================
    def mostrar_login(self):
        if self.frame_registro:
            self.frame_registro.destroy()
            self.frame_registro = None
        if self.frame_inicio:
            self.frame_inicio.destroy()
            self.frame_inicio = None
        if self.frame_login:
            self.frame_login.destroy()
            self.frame_login = None

        self.actualizar_visibilidad_fondo()
        self.btn_theme_login.place(relx=0.03, rely=0.96, anchor="w")
        self.footer.place(relx=0.5, rely=0.96, anchor="center")
        
        self.card_main.configure(
            fg_color=("#FFFFFF", "#121214"), 
            border_color=("#D1D5DB", "#2A2D34"), 
            border_width=1
        )
        self.card_main.place(relx=0.5, rely=0.47, anchor="center")

        self.frame_login = ctk.CTkFrame(self.card_main, fg_color="transparent")
        self.frame_login.pack(fill="both", expand=True, padx=25, pady=20)

        left_f = ctk.CTkFrame(self.frame_login, fg_color="transparent")
        left_f.pack(side="left", fill="both", expand=True, padx=(10, 10))

        logo_center = ctk.CTkFrame(left_f, fg_color="transparent")
        logo_center.place(relx=0.5, rely=0.46, anchor="center")

        if os.path.exists(self.ruta_logo):
            img_c = self.hacer_imagen_circular(self.ruta_logo, (330, 330))
            img_l = ctk.CTkImage(light_image=img_c, dark_image=img_c, size=(330, 330))
            ctk.CTkLabel(logo_center, image=img_l, text="").pack(pady=(0, 15))

        slogan_frame = ctk.CTkFrame(logo_center, fg_color="transparent")
        slogan_frame.pack()

        ctk.CTkFrame(slogan_frame, width=30, height=2, fg_color="#D32F2F").pack(side="left", padx=6)
        ctk.CTkLabel(slogan_frame, text="Tu vehículo en las mejores manos", font=("Calibri", 15, "italic", "bold"), text_color=("#444444", "#DDDDDD")).pack(side="left")
        ctk.CTkFrame(slogan_frame, width=30, height=2, fg_color="#D32F2F").pack(side="right", padx=6)

        # LÍNEA DIVISORIA ROJA DEL LOGIN
        divider = ctk.CTkFrame(self.frame_login, width=3, fg_color="#D32F2F", corner_radius=1)
        divider.pack(side="left", fill="y", pady=15)

        right_f = ctk.CTkFrame(self.frame_login, fg_color="transparent")
        right_f.pack(side="right", fill="both", expand=True, padx=(10, 10))

        form_c = ctk.CTkFrame(right_f, fg_color="transparent")
        form_c.place(relx=0.5, rely=0.48, anchor="center")

        ctk.CTkLabel(form_c, text="👤", font=("Segoe UI Emoji", 42), text_color="#D32F2F").pack(pady=(0, 2))
        ctk.CTkLabel(form_c, text="INICIO DE SESIÓN", font=("Calibri", 28, "bold"), text_color=("#000000", "#FFFFFF")).pack(pady=(0, 4))
        ctk.CTkLabel(form_c, text="Ingresa tus datos para acceder al sistema", font=("Calibri", 15), text_color=("#555555", "#AAAAAA")).pack(pady=(0, 18))

        ctk.CTkLabel(form_c, text="👤  Usuario:", font=("Calibri", 15, "bold"), text_color=("#000000", "#FFFFFF")).pack(anchor="w", pady=(0, 4))
        self.txt_user_login = ctk.CTkEntry(
            form_c, width=350, height=46, corner_radius=10, 
            placeholder_text="Ingrese su usuario", font=("Calibri", 15), 
            fg_color=("#FAFAFA", "#1A1A1E"), border_width=1.5, border_color=("#B0B0B0", "#333338")
        )
        self.txt_user_login.pack(pady=(0, 14))

        ctk.CTkLabel(form_c, text="🔒  Contraseña:", font=("Calibri", 15, "bold"), text_color=("#000000", "#FFFFFF")).pack(anchor="w", pady=(0, 4))
        pass_f = ctk.CTkFrame(form_c, fg_color="transparent")
        pass_f.pack(pady=(0, 6))

        self.txt_pass_login = ctk.CTkEntry(
            pass_f, width=294, height=46, corner_radius=10, show="•", 
            placeholder_text="Ingrese su contraseña", font=("Calibri", 15), 
            fg_color=("#FAFAFA", "#1A1A1E"), border_width=1.5, border_color=("#B0B0B0", "#333338")
        )
        self.txt_pass_login.pack(side="left", padx=(0, 6))

        self.mostrando_p_login = False
        def toggle_p_login():
            if self.mostrando_p_login:
                self.txt_pass_login.configure(show="•")
                btn_p.configure(text="👁️")
                self.mostrando_p_login = False
            else:
                self.txt_pass_login.configure(show="")
                btn_p.configure(text="🙈")
                self.mostrando_p_login = True

        btn_p = ctk.CTkButton(
            pass_f, text="👁️", width=50, height=46, corner_radius=10, 
            fg_color=("#E0E0E0", "#25252A"), text_color=("#000", "#FFF"), 
            hover_color=("#CCCCCC", "#333338"), font=("Segoe UI Emoji", 18), 
            command=toggle_p_login
        )
        btn_p.pack(side="right")

        ctk.CTkButton(
            form_c, text=" ¿Olvidó su contraseña?", font=("Calibri", 14, "underline"), 
            text_color=("#444444", "#CCCCCC"), hover_color=("#FFFFFF", "#121214"), 
            fg_color="transparent", width=100, command=self.recuperar_contrasena
        ).pack(anchor="e", pady=(0, 16))

        ctk.CTkButton(
            form_c, text="➔  INICIAR SESIÓN", width=350, height=48, corner_radius=10, 
            fg_color="#D32F2F", hover_color="#B71C1C", font=("Calibri", 17, "bold"), 
            command=self.validar_login
        ).pack(pady=(0, 10))

        ctk.CTkButton(
            form_c, text="¿No tiene cuenta? Regístrese aquí", font=("Calibri", 15, "bold"), 
            text_color="#D32F2F", hover_color=("#FFFFFF", "#121214"), fg_color="transparent", 
            command=self.mostrar_registro
        ).pack()

    def recuperar_contrasena(self):
        win_rec = ctk.CTkToplevel(self)
        win_rec.title("Recuperar Contraseña")
        win_rec.geometry("500x580")
        win_rec.resizable(False, False)
        win_rec.grab_set()

        ctk.CTkLabel(win_rec, text="🔑 RECUPERAR CONTRASEÑA", font=("Calibri", 22, "bold"), text_color="#D32F2F").pack(pady=(20, 5))
        ctk.CTkLabel(win_rec, text="Ingrese su usuario y teléfono para verificar su identidad", font=("Calibri", 15), text_color=("#222222", "#CCCCCC"), wraplength=440).pack(pady=(0, 15))

        form_rec = ctk.CTkFrame(win_rec, fg_color="transparent")
        form_rec.pack(padx=30, fill="x")

        ctk.CTkLabel(form_rec, text="Usuario:", font=("Calibri", 16, "bold"), text_color=("#000", "#FFF")).pack(anchor="w", pady=(2, 2))
        txt_rec_user = ctk.CTkEntry(form_rec, width=440, height=44, placeholder_text="Ingrese su usuario", font=("Calibri", 16))
        txt_rec_user.pack(pady=(0, 10))

        ctk.CTkLabel(form_rec, text="Teléfono registrado:", font=("Calibri", 16, "bold"), text_color=("#000", "#FFF")).pack(anchor="w", pady=(2, 2))
        txt_rec_tel = ctk.CTkEntry(form_rec, width=440, height=44, placeholder_text="Ingrese su teléfono", font=("Calibri", 16))
        txt_rec_tel.pack(pady=(0, 10))

        ctk.CTkLabel(form_rec, text="Código de verificación:", font=("Calibri", 16, "bold"), text_color=("#000", "#FFF")).pack(anchor="w", pady=(2, 2))
        txt_rec_codigo = ctk.CTkEntry(form_rec, width=440, height=44, placeholder_text="Código de 6 dígitos", font=("Calibri", 16), state="disabled")
        txt_rec_codigo.pack(pady=(0, 10))

        ctk.CTkLabel(form_rec, text="Nueva contraseña:", font=("Calibri", 16, "bold"), text_color=("#000", "#FFF")).pack(anchor="w", pady=(2, 2))
        txt_rec_pass = ctk.CTkEntry(form_rec, width=440, height=44, show="•", placeholder_text="Nueva contraseña", font=("Calibri", 16), state="disabled")
        txt_rec_pass.pack(pady=(0, 18))

        def generar_codigo():
            usr = txt_rec_user.get().strip()
            tel = txt_rec_tel.get().strip()
            if not usr or not tel:
                messagebox.showwarning("Atención ⚠️", "Ingrese usuario y teléfono.", parent=win_rec)
                return
            try:
                conexion = mysql.connector.connect(host="localhost", user="root", password="", database="taller_automotriz_db", port=3306)
                cursor = conexion.cursor(dictionary=True)
                cursor.execute("SELECT id_usuario FROM usuarios WHERE usuario = %s AND telefono = %s", (usr, tel))
                u = cursor.fetchone()
                if u:
                    self.id_usuario_recuperando = u['id_usuario']
                    self.codigo_verificacion_generado = str(random.randint(100000, 999999))
                    messagebox.showinfo("Código Generado 📱", f"Código de verificación: {self.codigo_verificacion_generado}", parent=win_rec)
                    txt_rec_codigo.configure(state="normal")
                    txt_rec_pass.configure(state="normal")
                    btn_rest.configure(state="normal")
                else:
                    messagebox.showerror("Error ❌", "Los datos no coinciden.", parent=win_rec)
                cursor.close()
                conexion.close()
            except mysql.connector.Error as err:
                messagebox.showerror("Error BD ❌", str(err), parent=win_rec)

        def actualizar_clave():
            if txt_rec_codigo.get().strip() != self.codigo_verificacion_generado:
                messagebox.showerror("Error ❌", "Código incorrecto.", parent=win_rec)
                return
            np = txt_rec_pass.get().strip()
            if not np:
                messagebox.showwarning("Atención ⚠️", "Ingrese la nueva clave.", parent=win_rec)
                return
            try:
                ph = hashlib.sha256(np.encode()).hexdigest()
                conexion = mysql.connector.connect(host="localhost", user="root", password="", database="taller_automotriz_db", port=3306)
                cursor = conexion.cursor()
                cursor.execute("UPDATE usuarios SET password_hash = %s WHERE id_usuario = %s", (ph, self.id_usuario_recuperando))
                conexion.commit()
                messagebox.showinfo("Éxito 🎉", "Contraseña cambiada correctamente.", parent=win_rec)
                cursor.close()
                conexion.close()
                win_rec.destroy()
            except mysql.connector.Error as err:
                messagebox.showerror("Error BD ❌", str(err), parent=win_rec)

        ctk.CTkButton(form_rec, text="📱 Generar Código", height=44, font=("Calibri", 16, "bold"), fg_color="#D32F2F", hover_color="#B71C1C", command=generar_codigo).pack(fill="x", pady=(0, 10))
        btn_rest = ctk.CTkButton(form_rec, text="Restablecer Contraseña", height=44, font=("Calibri", 16, "bold"), fg_color="#B71C1C", hover_color="#8B0000", state="disabled", command=actualizar_clave)
        btn_rest.pack(fill="x")

    # =========================================================================
    # REGISTRO DE CLIENTES (PÚBLICO)
    # =========================================================================
    def mostrar_registro(self):
        if self.frame_login:
            self.frame_login.destroy()
            self.frame_login = None
        if self.frame_registro:
            self.frame_registro.destroy()
            self.frame_registro = None

        self.actualizar_visibilidad_fondo()
        self.frame_registro = ctk.CTkFrame(self.card_main, fg_color="transparent")
        self.frame_registro.pack(fill="both", expand=True, padx=30, pady=20)

        left_f = ctk.CTkFrame(self.frame_registro, fg_color="transparent")
        left_f.pack(side="left", fill="both", expand=True, padx=(0, 15))

        left_center_f = ctk.CTkFrame(left_f, fg_color="transparent")
        left_center_f.place(relx=0.5, rely=0.5, anchor="center")

        if os.path.exists(self.ruta_logo):
            img_c = self.hacer_imagen_circular(self.ruta_logo, (280, 280))
            img_l = ctk.CTkImage(light_image=img_c, dark_image=img_c, size=(280, 280))
            ctk.CTkLabel(left_center_f, image=img_l, text="").pack(pady=(0, 15))

        ctk.CTkLabel(left_center_f, text="Taller Automotriz I.G", font=("Calibri", 26, "bold"), text_color="#D32F2F").pack(pady=(0, 4))
        ctk.CTkLabel(left_center_f, text="Crea tu cuenta de Cliente para acceder\ny consultar tus servicios automotrices.", font=("Calibri", 16), text_color=("#222222", "#CCCCCC"), justify="center").pack()

        divider = ctk.CTkFrame(self.frame_registro, width=3, fg_color="#D32F2F")
        divider.pack(side="left", fill="y", pady=15)

        right_f = ctk.CTkFrame(self.frame_registro, fg_color="transparent")
        right_f.pack(side="right", fill="both", expand=True, padx=(15, 0))

        ctk.CTkLabel(right_f, text="👤+", font=("Segoe UI Emoji", 40), text_color="#D32F2F").pack(pady=(0, 2))
        ctk.CTkLabel(right_f, text="REGISTRO DE CLIENTES", font=("Calibri", 28, "bold"), text_color=("#000000", "#FFFFFF")).pack(pady=(0, 15))

        grid_f = ctk.CTkFrame(right_f, fg_color="transparent")
        grid_f.pack(fill="x", pady=5)

        ctk.CTkLabel(grid_f, text="Nombre completo:", font=("Calibri", 16, "bold"), text_color=("#000", "#FFF")).grid(row=0, column=0, sticky="w", padx=8)
        ctk.CTkLabel(grid_f, text="Usuario:", font=("Calibri", 16, "bold"), text_color=("#000", "#FFF")).grid(row=0, column=1, sticky="w", padx=8)

        self.reg_nombre = ctk.CTkEntry(grid_f, width=240, height=44, corner_radius=8, placeholder_text="Ingrese su nombre", font=("Calibri", 16))
        self.reg_nombre.grid(row=1, column=0, padx=8, pady=(3, 12))

        self.reg_usuario = ctk.CTkEntry(grid_f, width=240, height=44, corner_radius=8, placeholder_text="Cree un usuario", font=("Calibri", 16))
        self.reg_usuario.grid(row=1, column=1, padx=8, pady=(3, 12))

        ctk.CTkLabel(grid_f, text="Correo electrónico:", font=("Calibri", 16, "bold"), text_color=("#000", "#FFF")).grid(row=2, column=0, sticky="w", padx=8)
        ctk.CTkLabel(grid_f, text="Teléfono:", font=("Calibri", 16, "bold"), text_color=("#000", "#FFF")).grid(row=2, column=1, sticky="w", padx=8)

        self.reg_correo = ctk.CTkEntry(grid_f, width=240, height=44, corner_radius=8, placeholder_text="ejemplo@correo.com", font=("Calibri", 16))
        self.reg_correo.grid(row=3, column=0, padx=8, pady=(3, 12))

        self.reg_telefono = ctk.CTkEntry(grid_f, width=240, height=44, corner_radius=8, placeholder_text="Máx 10 dígitos", font=("Calibri", 16))
        self.reg_telefono.grid(row=3, column=1, padx=8, pady=(3, 12))

        ctk.CTkLabel(grid_f, text="Contraseña:", font=("Calibri", 16, "bold"), text_color=("#000", "#FFF")).grid(row=4, column=0, sticky="w", padx=8)
        ctk.CTkLabel(grid_f, text="Confirmar contraseña:", font=("Calibri", 16, "bold"), text_color=("#000", "#FFF")).grid(row=4, column=1, sticky="w", padx=8)

        f_p1 = ctk.CTkFrame(grid_f, fg_color="transparent")
        f_p1.grid(row=5, column=0, padx=8, pady=(3, 12), sticky="w")
        self.reg_pass1 = ctk.CTkEntry(f_p1, width=210, height=44, show="•", placeholder_text="Contraseña", font=("Calibri", 16))
        self.reg_pass1.pack(side="left", padx=(0, 5))

        f_p2 = ctk.CTkFrame(grid_f, fg_color="transparent")
        f_p2.grid(row=5, column=1, padx=8, pady=(3, 12), sticky="w")
        self.reg_pass2 = ctk.CTkEntry(f_p2, width=210, height=44, show="•", placeholder_text="Confirme contraseña", font=("Calibri", 16))
        self.reg_pass2.pack(side="left", padx=(0, 5))

        btn_f = ctk.CTkFrame(right_f, fg_color="transparent")
        btn_f.pack(fill="x", padx=8, pady=(20, 5))

        ctk.CTkButton(
            btn_f, text="CANCELAR", width=200, height=46, 
            fg_color=("#F2F2F2", "#333333"), hover_color=("#E5E5E5", "#444444"), 
            border_width=1, border_color="#B0B0B0", 
            text_color=("#333333", "#FFFFFF"), font=("Calibri", 15, "bold"), 
            corner_radius=8, command=self.mostrar_login
        ).pack(side="left")

        ctk.CTkButton(
            btn_f, text="👤+ CREAR CUENTA", width=230, height=46, 
            fg_color="#D32F2F", hover_color="#B71C1C", 
            text_color="#FFFFFF", font=("Calibri", 16, "bold"), 
            corner_radius=8, command=self.guardar_registro
        ).pack(side="right")

    # =========================================================================
    # VISTAS DE AUDITORÍA Y LISTADO/CRUD DE USUARIOS
    # =========================================================================
    def mostrar_historial_logs(self):
        self.seleccionar_opcion_menu("logs")

        if not hasattr(self, 'body_scroll') or not self.body_scroll:
            return

        for widget in self.body_scroll.winfo_children():
            widget.destroy()

        ctk.CTkLabel(self.body_scroll, text="📜 HISTORIAL DE AUDITORÍA", font=("Calibri", 26, "bold"), text_color=("#111827", "#F9FAFB")).pack(pady=(15, 2))
        ctk.CTkLabel(self.body_scroll, text="Registro detallado de accesos y operaciones realizadas en el taller", font=("Calibri", 16), text_color=("#4B5563", "#9CA3AF")).pack(pady=(0, 15))

        frame_tabla_logs = ctk.CTkFrame(self.body_scroll, fg_color="transparent")
        frame_tabla_logs.pack(fill="both", expand=True, padx=20, pady=10)

        try:
            conexion = mysql.connector.connect(host="localhost", user="root", password="", database="taller_automotriz_db", port=3306)
            cursor = conexion.cursor(dictionary=True)
            cursor.execute("SELECT id_log, usuario, rol, accion, fecha_registro FROM logs_sistema ORDER BY fecha_registro DESC LIMIT 100")
            logs = cursor.fetchall()

            if not logs:
                ctk.CTkLabel(frame_tabla_logs, text="No hay registros de auditoría en el sistema aún.", font=("Calibri", 16), text_color=("#6B7280", "#9CA3AF")).pack(pady=30)
            else:
                for log in logs:
                    card_l = ctk.CTkFrame(frame_tabla_logs, fg_color=("#FFFFFF", "#1E1E22"), corner_radius=12, border_width=1, border_color=("#E5E7EB", "#2A2D34"))
                    card_l.pack(fill="x", pady=6, ipadx=14, ipady=10)

                    top_l = ctk.CTkFrame(card_l, fg_color="transparent")
                    top_l.pack(fill="x")

                    ctk.CTkLabel(top_l, text=f"👤 {log['usuario']} ({log['rol']})", font=("Calibri", 16, "bold"), text_color=("#111827", "#FFFFFF")).pack(side="left")
                    ctk.CTkLabel(top_l, text=f"🕒 {log['fecha_registro']}", font=("Calibri", 14, "bold"), text_color=("#6B7280", "#9CA3AF")).pack(side="right")

                    ctk.CTkLabel(card_l, text=f"• {log['accion']}", font=("Calibri", 15), text_color=("#374151", "#E5E7EB"), anchor="w").pack(fill="x", pady=(4, 0))

            cursor.close()
            conexion.close()

        except mysql.connector.Error as err:
            ctk.CTkLabel(frame_tabla_logs, text=f"Error cargando auditoría:\n{err}", text_color="#D32F2F").pack(pady=20)

    def alternar_estado_usuario(self, id_usuario, estado_actual):
        nuevo_estado = "Inactivo" if estado_actual == "Activo" else "Activo"
        accion_txt = "desactivar" if nuevo_estado == "Inactivo" else "reactivar"

        if messagebox.askyesno("Confirmar Cambio ⚠️", f"¿Desea {accion_txt} la cuenta del usuario #{id_usuario}?"):
            try:
                conexion = mysql.connector.connect(host="localhost", user="root", password="", database="taller_automotriz_db", port=3306)
                cursor = conexion.cursor()
                cursor.execute("UPDATE usuarios SET estado = %s WHERE id_usuario = %s", (nuevo_estado, id_usuario))
                conexion.commit()

                self.registrar_log(f"Cambió el estado del usuario #{id_usuario} a {nuevo_estado}")
                messagebox.showinfo("Éxito 🎉", f"El usuario ahora se encuentra '{nuevo_estado}'.")
                cursor.close()
                conexion.close()

                self.mostrar_lista_usuarios()
            except mysql.connector.Error as err:
                messagebox.showerror("Error BD ❌", str(err))

    def abrir_registro_integrado_por_rol(self, rol_objetivo):
        for widget in self.body_scroll.winfo_children():
            widget.destroy()

        ctk.CTkLabel(self.body_scroll, text=f"👤 REGISTRAR {rol_objetivo.upper()}", font=("Calibri", 26, "bold"), text_color=("#111827", "#F9FAFB")).pack(pady=(15, 2))
        ctk.CTkLabel(self.body_scroll, text=f"Ingrese la información para dar de alta un nuevo usuario con rol de {rol_objetivo}", font=("Calibri", 16), text_color=("#4B5563", "#9CA3AF")).pack(pady=(0, 20))

        card_form = ctk.CTkFrame(self.body_scroll, fg_color=("#FFFFFF", "#1E1E22"), corner_radius=16, border_width=1, border_color=("#E5E7EB", "#2A2D34"))
        card_form.pack(padx=40, pady=10, fill="x")

        form_inner = ctk.CTkFrame(card_form, fg_color="transparent")
        form_inner.pack(padx=30, pady=25, fill="x")

        ctk.CTkLabel(form_inner, text="Nombre completo:", font=("Calibri", 16, "bold"), text_color=("#111827", "#FFF")).pack(anchor="w")
        txt_nom = ctk.CTkEntry(form_inner, height=44, font=("Calibri", 16))
        txt_nom.pack(fill="x", pady=(2, 12))

        ctk.CTkLabel(form_inner, text="Usuario de acceso:", font=("Calibri", 16, "bold"), text_color=("#111827", "#FFF")).pack(anchor="w")
        txt_usr = ctk.CTkEntry(form_inner, height=44, font=("Calibri", 16))
        txt_usr.pack(fill="x", pady=(2, 12))

        ctk.CTkLabel(form_inner, text="Correo electrónico:", font=("Calibri", 16, "bold"), text_color=("#111827", "#FFF")).pack(anchor="w")
        txt_cor = ctk.CTkEntry(form_inner, height=44, font=("Calibri", 16))
        txt_cor.pack(fill="x", pady=(2, 12))

        ctk.CTkLabel(form_inner, text="Teléfono de contacto:", font=("Calibri", 16, "bold"), text_color=("#111827", "#FFF")).pack(anchor="w")
        txt_tel = ctk.CTkEntry(form_inner, height=44, font=("Calibri", 16))
        txt_tel.pack(fill="x", pady=(2, 12))

        ctk.CTkLabel(form_inner, text="Contraseña inicial:", font=("Calibri", 16, "bold"), text_color=("#111827", "#FFF")).pack(anchor="w")
        txt_pas = ctk.CTkEntry(form_inner, height=44, show="•", font=("Calibri", 16))
        txt_pas.pack(fill="x", pady=(2, 25))

        btn_bar = ctk.CTkFrame(form_inner, fg_color="transparent")
        btn_bar.pack(fill="x")

        def volver_a_pestaña():
            if rol_objetivo == "Mecánico":
                self.mostrar_lista_usuarios("Mecánicos", "Mecánico")
            elif rol_objetivo == "Administrador":
                self.mostrar_lista_usuarios("Administrador", "Administrador")
            else:
                self.mostrar_lista_usuarios("Clientes", "Cliente")

        ctk.CTkButton(
            btn_bar, text="⬅️ Cancelar y Volver", width=180, height=46,
            fg_color=("#E5E7EB", "#2A2D34"), hover_color=("#D1D5DB", "#374151"),
            text_color=("#111827", "#FFF"), font=("Calibri", 15, "bold"),
            command=volver_a_pestaña
        ).pack(side="left")

        def guardar():
            n, u, c, t, p = txt_nom.get().strip(), txt_usr.get().strip(), txt_cor.get().strip(), txt_tel.get().strip(), txt_pas.get().strip()
            if not n or not u or not c or not t or not p:
                messagebox.showwarning("Atención ⚠️", "Por favor complete todos los campos requeridos.")
                return
            try:
                ph = hashlib.sha256(p.encode()).hexdigest()
                conexion = mysql.connector.connect(host="localhost", user="root", password="", database="taller_automotriz_db", port=3306)
                cursor = conexion.cursor()
                cursor.execute("INSERT INTO usuarios (nombre_completo, usuario, correo, telefono, password_hash, rol, estado) VALUES (%s, %s, %s, %s, %s, %s, 'Activo')", (n, u, c, t, ph, rol_objetivo))
                conexion.commit()
                self.registrar_log(f"Creó la cuenta de {rol_objetivo} '{n}'")
                messagebox.showinfo("Registro Completado 🎉", f"Cuenta de {rol_objetivo} creada exitosamente.")
                cursor.close()
                conexion.close()
                volver_a_pestaña()
            except mysql.connector.Error as err:
                messagebox.showerror("Error BD ❌", str(err))

        ctk.CTkButton(
            btn_bar, text=f"💾 Guardar {rol_objetivo}", width=220, height=46,
            fg_color="#D32F2F", hover_color="#B71C1C", font=("Calibri", 16, "bold"),
            command=guardar
        ).pack(side="right")

    def cargar_cards_usuarios(self, contenedor, filtro_rol=None):
        for w in contenedor.winfo_children():
            w.destroy()

        try:
            conexion = mysql.connector.connect(host="localhost", user="root", password="", database="taller_automotriz_db", port=3306)
            cursor = conexion.cursor(dictionary=True)
            
            if filtro_rol and filtro_rol != "Todos":
                cursor.execute("SELECT id_usuario, nombre_completo, usuario, correo, telefono, rol, estado FROM usuarios WHERE LOWER(rol) LIKE %s ORDER BY id_usuario ASC", (f"%{filtro_rol.lower()}%",))
            else:
                cursor.execute("SELECT id_usuario, nombre_completo, usuario, correo, telefono, rol, estado FROM usuarios ORDER BY id_usuario ASC")
            
            usuarios = cursor.fetchall()

            if not usuarios:
                ctk.CTkLabel(contenedor, text="No hay usuarios registrados en esta sección.", font=("Calibri", 16), text_color=("#6B7280", "#9CA3AF")).pack(pady=30)
            else:
                for u in usuarios:
                    rol = str(u['rol']).strip().capitalize()
                    estado = u['estado']

                    card_usr = ctk.CTkFrame(contenedor, fg_color=("#FFFFFF", "#1E1E22"), corner_radius=12, border_width=1, border_color=("#E5E7EB", "#2A2D34"))
                    card_usr.pack(fill="x", pady=6, ipadx=14, ipady=10)

                    top_card = ctk.CTkFrame(card_usr, fg_color="transparent")
                    top_card.pack(fill="x")

                    ctk.CTkLabel(top_card, text=f"#{u['id_usuario']} {u['nombre_completo']}", font=("Calibri", 16, "bold"), text_color=("#111827", "#FFF")).pack(side="left")

                    badge_rol = ctk.CTkLabel(top_card, text=f"  {rol}  ", font=("Calibri", 13, "bold"), fg_color="#FFF0F0" if rol=="Administrador" else "#2D2D35", text_color="#D32F2F" if rol=="Administrador" else "#EEE", corner_radius=6)
                    badge_rol.pack(side="left", padx=10)

                    bg_est = "#E8F5E9" if estado == "Activo" else "#FFEBEE"
                    tx_est = "#2E7D32" if estado == "Activo" else "#C62828"
                    badge_est = ctk.CTkLabel(top_card, text=f"● {estado}", font=("Calibri", 13, "bold"), fg_color=bg_est, text_color=tx_est, corner_radius=6)
                    badge_est.pack(side="right")

                    info_txt = f"Usuario: {u['usuario']} | Tel: {u['telefono']} | {u['correo'] if u['correo'] else 'Sin correo'}"
                    ctk.CTkLabel(card_usr, text=info_txt, font=("Calibri", 14), text_color=("#4B5563", "#9CA3AF"), anchor="w").pack(fill="x", pady=(4, 6))

                    btn_txt = "🚫 Desactivar" if estado == "Activo" else "✅ Reactivar"
                    btn_color = "#C62828" if estado == "Activo" else "#2E7D32"
                    btn_hover = "#9A0007" if estado == "Activo" else "#1B5E20"

                    ctk.CTkButton(
                        card_usr, text=btn_txt, width=120, height=32, 
                        fg_color=btn_color, hover_color=btn_hover, 
                        font=("Calibri", 13, "bold"),
                        command=lambda uid=u['id_usuario'], est=estado: self.alternar_estado_usuario(uid, est)
                    ).pack(anchor="e")

            cursor.close()
            conexion.close()

        except mysql.connector.Error as err:
            ctk.CTkLabel(contenedor, text=f"Error al cargar usuarios:\n{err}", text_color="#D32F2F").pack(pady=20)

    def mostrar_lista_usuarios(self, pestaña_inicial="Todos", filtro_inicial="Todos"):
        self.seleccionar_opcion_menu("usuarios")

        if not hasattr(self, 'body_scroll') or not self.body_scroll:
            return

        for widget in self.body_scroll.winfo_children():
            widget.destroy()

        ctk.CTkLabel(self.body_scroll, text="👥 GESTIÓN DE USUARIOS", font=("Calibri", 26, "bold"), text_color=("#111827", "#F9FAFB")).pack(pady=(15, 2))
        ctk.CTkLabel(self.body_scroll, text="Administración por roles y filtrado rápido del personal", font=("Calibri", 16), text_color=("#4B5563", "#9CA3AF")).pack(pady=(0, 15))

        bar_tabs = ctk.CTkFrame(self.body_scroll, fg_color="transparent")
        bar_tabs.pack(fill="x", padx=10, pady=(0, 10))

        tabs_buttons = ctk.CTkFrame(bar_tabs, fg_color="transparent")
        tabs_buttons.pack(side="left")

        container_list = ctk.CTkFrame(self.body_scroll, fg_color="transparent")
        container_list.pack(fill="both", expand=True, padx=10)

        self.btn_tabs_dict = {}

        pestañas = [("Todos", "Todos"), ("Administrador", "Administrador"), ("Mecánicos", "Mecánico"), ("Clientes", "Cliente")]

        def seleccionar_tab(nombre_tab, rol_filtro):
            for name, b in self.btn_tabs_dict.items():
                if name == nombre_tab:
                    b.configure(fg_color="#D32F2F", text_color="#FFFFFF", hover_color="#B71C1C")
                else:
                    b.configure(
                        fg_color=("#E5E7EB", "#2A2D34"),
                        text_color=("#111827", "#E0E0E0"),
                        hover_color=("#D1D5DB", "#374151")
                    )

            if hasattr(self, 'btn_registrar_container') and self.btn_registrar_container:
                self.btn_registrar_container.destroy()

            self.btn_registrar_container = ctk.CTkFrame(bar_tabs, fg_color="transparent")
            self.btn_registrar_container.pack(side="right")

            if rol_filtro and rol_filtro != "Todos":
                btn_add = ctk.CTkButton(
                    self.btn_registrar_container, text=f"➕ Registrar {rol_filtro}", height=38,
                    fg_color="#D32F2F", hover_color="#B71C1C", font=("Calibri", 15, "bold"),
                    command=lambda r=rol_filtro: self.abrir_registro_integrado_por_rol(r)
                )
                btn_add.pack()

            self.cargar_cards_usuarios(container_list, rol_filtro)

        for nombre_tab, rol_filtro in pestañas:
            btn_t = ctk.CTkButton(
                tabs_buttons, text=nombre_tab, width=120, height=38, corner_radius=20,
                font=("Calibri", 15, "bold"),
                command=lambda n=nombre_tab, r=rol_filtro: seleccionar_tab(n, r)
            )
            btn_t.pack(side="left", padx=4)
            self.btn_tabs_dict[nombre_tab] = btn_t

        seleccionar_tab(pestaña_inicial, filtro_inicial)

    # =========================================================================
    # FORMULARIO UNIVERSAL DE VEHÍCULO
    # =========================================================================
    def abrir_registro_vehiculo(self):
        self.seleccionar_opcion_menu("vehiculos")

        if not hasattr(self, 'body_scroll') or not self.body_scroll:
            return

        for widget in self.body_scroll.winfo_children():
            widget.destroy()

        rol_normalizado = str(self.rol_actual).strip().capitalize()
        titulo_pantalla = "🚘 REGISTRAR MI VEHÍCULO" if rol_normalizado == "Cliente" else "🚘 REGISTRO DE VEHÍCULO"

        ctk.CTkLabel(self.body_scroll, text=titulo_pantalla, font=("Calibri", 26, "bold"), text_color=("#111827", "#F9FAFB")).pack(pady=(15, 2))
        ctk.CTkLabel(self.body_scroll, text="Ingrese los datos oficiales del automóvil para guardarlo en la base de datos", font=("Calibri", 16), text_color=("#4B5563", "#9CA3AF")).pack(pady=(0, 20))

        card_form = ctk.CTkFrame(self.body_scroll, fg_color=("#FFFFFF", "#1E1E22"), corner_radius=16, border_width=1, border_color=("#E5E7EB", "#2A2D34"))
        card_form.pack(padx=40, pady=10, fill="x")

        form_inner = ctk.CTkFrame(card_form, fg_color="transparent")
        form_inner.pack(padx=30, pady=25, fill="x")

        # PLACA
        ctk.CTkLabel(form_inner, text="Placa del Vehículo (Requerido):", font=("Calibri", 16, "bold"), text_color=("#111827", "#FFF")).pack(anchor="w")
        txt_v_placa = ctk.CTkEntry(form_inner, height=44, placeholder_text="Ej. ABC123", font=("Calibri", 16))
        txt_v_placa.pack(fill="x", pady=(2, 12))

        # MARCA
        ctk.CTkLabel(form_inner, text="Marca:", font=("Calibri", 16, "bold"), text_color=("#111827", "#FFF")).pack(anchor="w")
        txt_v_marca = ctk.CTkEntry(form_inner, height=44, placeholder_text="Ej. Chevrolet, Toyota, Mazda", font=("Calibri", 16))
        txt_v_marca.pack(fill="x", pady=(2, 12))

        # COLOR
        ctk.CTkLabel(form_inner, text="Color:", font=("Calibri", 16, "bold"), text_color=("#111827", "#FFF")).pack(anchor="w")
        txt_v_color = ctk.CTkEntry(form_inner, height=44, placeholder_text="Ej. Rojo, Negro, Blanco", font=("Calibri", 16))
        txt_v_color.pack(fill="x", pady=(2, 12))

        # MODELO
        ctk.CTkLabel(form_inner, text="Modelo / Año (modelo INT):", font=("Calibri", 16, "bold"), text_color=("#111827", "#FFF")).pack(anchor="w")
        txt_v_modelo = ctk.CTkEntry(form_inner, height=44, placeholder_text="Ej. 2020", font=("Calibri", 16))
        txt_v_modelo.pack(fill="x", pady=(2, 12))

        # DESPLEGABLE SOLO PARA ADMIN Y MECÁNICO
        combo_cliente = None
        dict_clientes = {}
        if rol_normalizado != "Cliente":
            dict_clientes = self.obtener_lista_clientes()
            opciones_combo = list(dict_clientes.keys())
            ctk.CTkLabel(form_inner, text="Propietario / Cliente del Vehículo:", font=("Calibri", 16, "bold"), text_color=("#111827", "#FFF")).pack(anchor="w")
            combo_cliente = ctk.CTkComboBox(form_inner, height=44, values=opciones_combo, font=("Calibri", 16), state="readonly")
            combo_cliente.set(opciones_combo[0] if opciones_combo else "Sin asignar")
            combo_cliente.pack(fill="x", pady=(2, 12))

        btn_bar = ctk.CTkFrame(form_inner, fg_color="transparent")
        btn_bar.pack(fill="x", pady=(15, 0))

        ctk.CTkButton(
            btn_bar, text="⬅️ Cancelar y Volver", width=180, height=46,
            fg_color=("#E5E7EB", "#2A2D34"), hover_color=("#D1D5DB", "#374151"),
            text_color=("#111827", "#FFF"), font=("Calibri", 15, "bold"),
            command=lambda: self.mostrar_inicio_dashboard(rol_normalizado)
        ).pack(side="left")

        def guardar_vehiculo_bd():
            p = txt_v_placa.get().strip().upper()
            marca = txt_v_marca.get().strip()
            c = txt_v_color.get().strip()
            mod_str = txt_v_modelo.get().strip()

            if not p or not marca:
                messagebox.showwarning("Campos Incompletos ⚠️", "La Placa y la Marca son obligatorias.")
                return

            modelo_val = int(mod_str) if mod_str.isdigit() else None

            if rol_normalizado == "Cliente":
                id_cliente_val = self.id_usuario_actual
            else:
                cliente_sel = combo_cliente.get() if combo_cliente else "Sin asignar"
                id_cliente_val = dict_clientes.get(cliente_sel, None)

            try:
                conexion = mysql.connector.connect(host="localhost", user="root", password="", database="taller_automotriz_db", port=3306)
                cursor = conexion.cursor()

                sql = "INSERT INTO vehiculos (id_cliente, placa, marca, color, modelo) VALUES (%s, %s, %s, %s, %s)"
                cursor.execute(sql, (id_cliente_val, p, marca, c if c else None, modelo_val))
                conexion.commit()

                cursor.close()
                conexion.close()

                self.registrar_log(f"Registró en BD el vehículo placa {p} ({marca})")
                messagebox.showinfo("¡Vehículo Registrado! 🚗", f"El automóvil fue guardado exitosamente en la base de datos.\n\nPlaca: {p}\nMarca: {marca}\nColor: {c if c else 'N/A'}\nModelo: {modelo_val if modelo_val else 'N/A'}")
                self.mostrar_inicio_dashboard(rol_normalizado)

            except mysql.connector.Error as err:
                messagebox.showerror("Error BD ❌", f"No se pudo registrar el vehículo en la base de datos:\n\n{err}")

        ctk.CTkButton(
            btn_bar, text="💾 Registrar Vehículo", width=240, height=46,
            fg_color="#D32F2F", hover_color="#B71C1C", font=("Calibri", 16, "bold"),
            command=guardar_vehiculo_bd
        ).pack(side="right")

    # =========================================================================
    # BÚSQUEDA Y REGISTRO DE TRABAJOS / HISTORIAL DE MANTENIMIENTO EN TABLA
    # =========================================================================
    def abrir_formulario_mantenimiento_embebido(self, id_vehiculo, placa):
        for widget in self.body_scroll.winfo_children():
            widget.destroy()

        ctk.CTkLabel(self.body_scroll, text=f"🛠️ REGISTRAR TRABAJO ({placa})", font=("Calibri", 26, "bold"), text_color=("#111827", "#F9FAFB")).pack(pady=(15, 2))
        ctk.CTkLabel(self.body_scroll, text="Ingrese los detalles del servicio técnico realizado al vehículo", font=("Calibri", 16), text_color=("#4B5563", "#9CA3AF")).pack(pady=(0, 20))

        card_form = ctk.CTkFrame(self.body_scroll, fg_color=("#FFFFFF", "#1E1E22"), corner_radius=16, border_width=1, border_color=("#E5E7EB", "#2A2D34"))
        card_form.pack(padx=40, pady=10, fill="x")

        form_inner = ctk.CTkFrame(card_form, fg_color="transparent")
        form_inner.pack(padx=30, pady=25, fill="x")

        # FECHA REALIZADA
        ctk.CTkLabel(form_inner, text="📅 Fecha en que se realizó el trabajo:", font=("Calibri", 16, "bold"), text_color=("#111827", "#FFF")).pack(anchor="w")
        
        f_fecha = ctk.CTkFrame(form_inner, fg_color="transparent")
        f_fecha.pack(fill="x", pady=(4, 15))

        hoy = datetime.now()
        dias = [str(i).zfill(2) for i in range(1, 32)]
        meses = [str(i).zfill(2) for i in range(1, 13)]
        anios = [str(i) for i in range(hoy.year - 5, hoy.year + 2)]

        combo_dia = ctk.CTkComboBox(f_fecha, values=dias, width=80, height=40, font=("Calibri", 15), state="readonly")
        combo_dia.set(str(hoy.day).zfill(2))
        combo_dia.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(f_fecha, text="/", font=("Calibri", 18, "bold"), text_color=("#111827", "#FFF")).pack(side="left", padx=(0, 8))

        combo_mes = ctk.CTkComboBox(f_fecha, values=meses, width=80, height=40, font=("Calibri", 15), state="readonly")
        combo_mes.set(str(hoy.month).zfill(2))
        combo_mes.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(f_fecha, text="/", font=("Calibri", 18, "bold"), text_color=("#111827", "#FFF")).pack(side="left", padx=(0, 8))

        combo_anio = ctk.CTkComboBox(f_fecha, values=anios, width=100, height=40, font=("Calibri", 15), state="readonly")
        combo_anio.set(str(hoy.year))
        combo_anio.pack(side="left")

        # DESCRIPCIÓN DEL TRABAJO
        ctk.CTkLabel(form_inner, text="📝 Descripción del Trabajo / Mantenimiento:", font=("Calibri", 16, "bold"), text_color=("#111827", "#FFF")).pack(anchor="w")
        txt_desc = ctk.CTkTextbox(form_inner, height=110, font=("Calibri", 15))
        txt_desc.pack(fill="x", pady=(4, 15))

        # OBSERVACIONES
        ctk.CTkLabel(form_inner, text="🔍 Observaciones Adicionales / Diagnóstico:", font=("Calibri", 16, "bold"), text_color=("#111827", "#FFF")).pack(anchor="w")
        txt_obs = ctk.CTkTextbox(form_inner, height=90, font=("Calibri", 15))
        txt_obs.pack(fill="x", pady=(4, 15))

        # COSTO
        ctk.CTkLabel(form_inner, text="💰 Costo / Mano de Obra ($ COP):", font=("Calibri", 16, "bold"), text_color=("#111827", "#FFF")).pack(anchor="w")
        txt_costo = ctk.CTkEntry(form_inner, height=44, placeholder_text="Ej. 150000", font=("Calibri", 16))
        txt_costo.pack(fill="x", pady=(4, 25))

        btn_bar = ctk.CTkFrame(form_inner, fg_color="transparent")
        btn_bar.pack(fill="x")

        def volver():
            self.buscar_vehiculo_por_placa(placa_predeterminada=placa)

        ctk.CTkButton(
            btn_bar, text="⬅️ Cancelar y Volver", width=180, height=46,
            fg_color=("#E5E7EB", "#2A2D34"), hover_color=("#D1D5DB", "#374151"),
            text_color=("#111827", "#FFF"), font=("Calibri", 15, "bold"),
            command=volver
        ).pack(side="left")

        def guardar_trabajo():
            desc = txt_desc.get("1.0", "end").strip()
            obs = txt_obs.get("1.0", "end").strip()
            c_str = txt_costo.get().strip()
            fecha_sel = f"{combo_anio.get()}-{combo_mes.get()}-{combo_dia.get()}"

            if not desc:
                messagebox.showwarning("Campo Vacío ⚠️", "Escriba la descripción del trabajo.")
                return

            costo_val = float(c_str) if c_str.replace('.', '', 1).isdigit() else 0.0

            try:
                conexion = mysql.connector.connect(host="localhost", user="root", password="", database="taller_automotriz_db", port=3306)
                cursor = conexion.cursor()
                
                sql = "INSERT INTO mantenimientos (id_vehiculo, id_mecanico, descripcion_trabajo, observaciones, costo, fecha_mantenimiento) VALUES (%s, %s, %s, %s, %s, %s)"
                cursor.execute(sql, (id_vehiculo, self.id_usuario_actual, desc, obs if obs else None, costo_val, fecha_sel))
                conexion.commit()

                cursor.close()
                conexion.close()

                self.registrar_log(f"Registró trabajo de mantenimiento en vehículo placa {placa}")
                messagebox.showinfo("¡Trabajo Registrado! 🛠️", "El mantenimiento fue guardado con éxito.")
                self.buscar_vehiculo_por_placa(placa_predeterminada=placa)
            except mysql.connector.Error as err:
                messagebox.showerror("Error BD ❌", f"No se pudo guardar el trabajo:\n\n{err}")

        ctk.CTkButton(
            btn_bar, text="💾 Guardar Mantenimiento", width=240, height=46,
            fg_color="#D32F2F", hover_color="#B71C1C", font=("Calibri", 16, "bold"),
            command=guardar_trabajo
        ).pack(side="right")

    def buscar_vehiculo_por_placa(self, placa_predeterminada=None):
        self.seleccionar_opcion_menu("buscar")
        if not hasattr(self, 'body_scroll') or not self.body_scroll:
            return

        for widget in self.body_scroll.winfo_children():
            widget.destroy()

        ctk.CTkLabel(self.body_scroll, text="🔎 BÚSQUEDA Y HISTORIAL DEL VEHÍCULO", font=("Calibri", 26, "bold"), text_color=("#111827", "#F9FAFB")).pack(pady=(15, 2))
        ctk.CTkLabel(self.body_scroll, text="Consulte los detalles y el historial de trabajos realizados al automóvil", font=("Calibri", 16), text_color=("#4B5563", "#9CA3AF")).pack(pady=(0, 20))

        card = ctk.CTkFrame(self.body_scroll, fg_color=("#FFFFFF", "#1E1E22"), corner_radius=16, border_width=1, border_color=("#E5E7EB", "#2A2D34"))
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
                conexion = mysql.connector.connect(host="localhost", user="root", password="", database="taller_automotriz_db", port=3306)
                cursor = conexion.cursor(dictionary=True)
                cursor.execute("""
                    SELECT v.*, u.nombre_completo AS propietario, u.telefono AS tel_propietario 
                    FROM vehiculos v 
                    LEFT JOIN usuarios u ON v.id_cliente = u.id_usuario 
                    WHERE v.placa = %s
                """, (placa,))
                v = cursor.fetchone()

                if v:
                    prop = v['propietario'] if v['propietario'] else "Sin asignación directa"
                    tel_prop = v['tel_propietario'] if v['tel_propietario'] else "N/A"
                    color_txt = v['color'] if v['color'] else "N/A"
                    mod_txt = v['modelo'] if v['modelo'] else "N/A"

                    info_box = ctk.CTkFrame(res_container, fg_color=("#F3F4F6", "#141418"), corner_radius=12, border_width=1, border_color=("#E5E7EB", "#2A2D34"))
                    info_box.pack(fill="x", ipadx=10, ipady=10)

                    f1 = ctk.CTkFrame(info_box, fg_color="transparent")
                    f1.pack(fill="x", pady=4, padx=10)

                    def crear_item_badge(parent, icono, titulo, valor):
                        item = ctk.CTkFrame(parent, fg_color=("#FFFFFF", "#1E1E22"), corner_radius=8, border_width=1, border_color=("#E5E7EB", "#2A2D34"))
                        item.pack(side="left", fill="x", expand=True, padx=4)
                        ctk.CTkLabel(item, text=f"{icono} {titulo}:", font=("Calibri", 13, "bold"), text_color=("#6B7280", "#9CA3AF")).pack(anchor="w", padx=10, pady=(6,0))
                        ctk.CTkLabel(item, text=str(valor), font=("Calibri", 15, "bold"), text_color=("#111827", "#F9FAFB")).pack(anchor="w", padx=10, pady=(0,6))

                    crear_item_badge(f1, "🚗", "Placa", v['placa'])
                    crear_item_badge(f1, "🚘", "Marca", v['marca'])
                    crear_item_badge(f1, "🎨", "Color", color_txt)
                    crear_item_badge(f1, "📅", "Modelo / Año", mod_txt)

                    f2 = ctk.CTkFrame(info_box, fg_color="transparent")
                    f2.pack(fill="x", pady=4, padx=10)

                    crear_item_badge(f2, "👤", "Cliente Propietario", prop)
                    crear_item_badge(f2, "📱", "Teléfono Contacto", tel_prop)

                    # EVALUACIÓN DE ROL EXACTO (INDEPENDIENTEMENTE DE TILDES Y MAYÚSCULAS)
                    rol_norm = str(self.rol_actual).strip().lower()
                    if rol_norm in ["mecanico", "mecánico", "administrador", "admin"]:
                        btn_bar_h = ctk.CTkFrame(frame_historial, fg_color="transparent")
                        btn_bar_h.pack(fill="x", pady=(15, 10))

                        ctk.CTkLabel(btn_bar_h, text="📜 HISTORIAL DE TRABAJOS REGISTRADOS", font=("Calibri", 18, "bold"), text_color=("#111827", "#F9FAFB")).pack(side="left")
                        
                        ctk.CTkButton(
                            btn_bar_h, text="➕ Registrar Nuevo Trabajo", height=38,
                            fg_color="#D32F2F", hover_color="#B71C1C", font=("Calibri", 15, "bold"),
                            command=lambda: self.abrir_formulario_mantenimiento_embebido(v['id_vehiculo'], v['placa'])
                        ).pack(side="right")
                    else:
                        ctk.CTkLabel(frame_historial, text="📜 HISTORIAL DE TRABAJOS REGISTRADOS", font=("Calibri", 18, "bold"), text_color=("#111827", "#F9FAFB")).pack(anchor="w", pady=(15, 10))

                    cursor.execute("""
                        SELECT m.*, u.nombre_completo AS mecanico 
                        FROM mantenimientos m 
                        LEFT JOIN usuarios u ON m.id_mecanico = u.id_usuario 
                        WHERE m.id_vehiculo = %s 
                        ORDER BY COALESCE(m.fecha_mantenimiento, m.fecha_registro) DESC
                    """, (v['id_vehiculo'],))
                    mantenimientos = cursor.fetchall()

                    if not mantenimientos:
                        ctk.CTkLabel(frame_historial, text="No se han registrado trabajos o mantenimientos previos para este vehículo.", font=("Calibri", 15), text_color=("#6B7280", "#9CA3AF")).pack(anchor="w", pady=10)
                    else:
                        tabla_card = ctk.CTkFrame(frame_historial, fg_color=("#FFFFFF", "#18181C"), corner_radius=12, border_width=1, border_color=("#E5E7EB", "#2A2D34"))
                        tabla_card.pack(fill="x", pady=5)

                        header_table = ctk.CTkFrame(tabla_card, fg_color=("#F3F4F6", "#25252A"), corner_radius=8)
                        header_table.pack(fill="x", padx=6, pady=6)

                        cols = [("📅 FECHA", 0.15), ("🛠️ MECÁNICO", 0.20), ("📝 DESCRIPCIÓN DEL TRABAJO", 0.35), ("🔍 OBSERVACIONES", 0.18), ("💰 COSTO", 0.12)]
                        for col_name, weight in cols:
                            lbl_col = ctk.CTkLabel(header_table, text=col_name, font=("Calibri", 13, "bold"), text_color=("#374151", "#E5E7EB"), anchor="w")
                            lbl_col.pack(side="left", fill="x", expand=True, padx=8, pady=8)

                        for i, m in enumerate(mantenimientos):
                            bg_row = ("#FFFFFF", "#1E1E22") if i % 2 == 0 else ("#F9FAFB", "#16161A")
                            row_frame = ctk.CTkFrame(tabla_card, fg_color=bg_row)
                            row_frame.pack(fill="x", padx=6, pady=2)

                            fecha_maint = m['fecha_mantenimiento'] if m['fecha_mantenimiento'] else str(m['fecha_registro']).split()[0]
                            mec_txt = m['mecanico'] if m['mecanico'] else "Taller General"
                            obs_txt = m['observaciones'] if m['observaciones'] else "Sin observaciones"
                            costo_txt = f"${float(m['costo']):,.0f} COP" if m['costo'] and float(m['costo']) > 0 else "N/A"

                            datos_fila = [
                                (str(fecha_maint), ("#111827", "#F9FAFB")),
                                (mec_txt, ("#D32F2F", "#FF5252")),
                                (m['descripcion_trabajo'], ("#111827", "#E5E7EB")),
                                (obs_txt, ("#6B7280", "#9CA3AF")),
                                (costo_txt, ("#2E7D32", "#81C784"))
                            ]

                            for txt_val, color_val in datos_fila:
                                lbl_val = ctk.CTkLabel(row_frame, text=txt_val, font=("Calibri", 13), text_color=color_val, anchor="w", justify="left", wraplength=180)
                                lbl_val.pack(side="left", fill="x", expand=True, padx=8, pady=8)

                else:
                    err_box = ctk.CTkFrame(res_container, fg_color=("#FEF2F2", "#2B1718"), corner_radius=10, border_width=1, border_color="#FCA5A5")
                    err_box.pack(fill="x", ipadx=10, ipady=10)
                    ctk.CTkLabel(err_box, text=f"❌ No se encontró ningún vehículo registrado con la placa '{placa}'.", font=("Calibri", 15, "bold"), text_color="#D32F2F").pack(anchor="w", padx=15)

                cursor.close()
                conexion.close()
                self.registrar_log(f"Consultó en BD el vehículo placa {placa}")

            except mysql.connector.Error as err:
                messagebox.showerror("Error BD ❌", f"Error consultando BD:\n{err}")

        ctk.CTkButton(f_inner, text="🔍 Buscar en Base de Datos", height=46, fg_color="#D32F2F", hover_color="#B71C1C", font=("Calibri", 16, "bold"), command=consultar_bd).pack(fill="x")

        if placa_predeterminada:
            consultar_bd()

    def abrir_cierre_caja(self):
        self.seleccionar_opcion_menu("caja")
        if not hasattr(self, 'body_scroll') or not self.body_scroll:
            return

        for widget in self.body_scroll.winfo_children():
            widget.destroy()

        ctk.CTkLabel(self.body_scroll, text="💵 CIERRE DE CAJA DIARIO", font=("Calibri", 26, "bold"), text_color=("#111827", "#F9FAFB")).pack(pady=(15, 2))
        ctk.CTkLabel(self.body_scroll, text="Resumen y balance final de recaudaciones por mano de obra y servicios", font=("Calibri", 16), text_color=("#4B5563", "#9CA3AF")).pack(pady=(0, 20))

        card = ctk.CTkFrame(self.body_scroll, fg_color=("#FFFFFF", "#1E1E22"), corner_radius=16, border_width=1, border_color=("#E5E7EB", "#2A2D34"))
        card.pack(padx=40, pady=10, fill="x")

        f_inner = ctk.CTkFrame(card, fg_color="transparent")
        f_inner.pack(padx=30, pady=25, fill="x")

        ctk.CTkLabel(f_inner, text="💰 Total Efectivo Cobrado Hoy:", font=("Calibri", 18, "bold"), text_color=("#111827", "#FFF")).pack(anchor="w")
        ctk.CTkLabel(f_inner, text="$ 0 COP", font=("Calibri", 36, "bold"), text_color="#2E7D32").pack(anchor="w", pady=(2, 15))

        ctk.CTkLabel(f_inner, text="🚗 Trabajos Entregados y Cobrados: 0", font=("Calibri", 16, "bold"), text_color=("#374151", "#DDD")).pack(anchor="w", pady=4)
        ctk.CTkLabel(f_inner, text="📋 Reparaciones Pendientes por Cobrar: 0", font=("Calibri", 16, "bold"), text_color=("#374151", "#DDD")).pack(anchor="w", pady=(4, 25))

        def realizar_cierre():
            self.registrar_log("Realizó el Cierre de Caja Diario ($0 COP)")
            messagebox.showinfo("Cierre Guardado 💵", "El cierre de caja ha sido registrado exitosamente.")
            self.mostrar_inicio_dashboard(self.rol_actual)

        ctk.CTkButton(f_inner, text="🔒 Finalizar y Cuadrar Caja", height=48, fg_color="#D32F2F", hover_color="#B71C1C", font=("Calibri", 16, "bold"), command=realizar_cierre).pack(fill="x")

    def abrir_agendar_cita(self):
        self.seleccionar_opcion_menu("citas")
        if not hasattr(self, 'body_scroll') or not self.body_scroll:
            return

        for widget in self.body_scroll.winfo_children():
            widget.destroy()

        ctk.CTkLabel(self.body_scroll, text="📅 AGENDAR CITA EN EL TALLER", font=("Calibri", 26, "bold"), text_color=("#111827", "#F9FAFB")).pack(pady=(15, 2))
        ctk.CTkLabel(self.body_scroll, text="Reserve su espacio técnico para mantenimientos y diagnósticos", font=("Calibri", 16), text_color=("#4B5563", "#9CA3AF")).pack(pady=(0, 20))

        card = ctk.CTkFrame(self.body_scroll, fg_color=("#FFFFFF", "#1E1E22"), corner_radius=16, border_width=1, border_color=("#E5E7EB", "#2A2D34"))
        card.pack(padx=40, pady=10, fill="x")

        f_inner = ctk.CTkFrame(card, fg_color="transparent")
        f_inner.pack(padx=30, pady=25, fill="x")

        ctk.CTkLabel(f_inner, text="Placa de su Vehículo:", font=("Calibri", 16, "bold"), text_color=("#111827", "#FFF")).pack(anchor="w")
        txt_c_placa = ctk.CTkEntry(f_inner, height=44, placeholder_text="Ej. ABC123", font=("Calibri", 16))
        txt_c_placa.pack(fill="x", pady=(2, 12))

        ctk.CTkLabel(f_inner, text="Fecha Deseada:", font=("Calibri", 16, "bold"), text_color=("#111827", "#FFF")).pack(anchor="w")
        txt_c_fecha = ctk.CTkEntry(f_inner, height=44, placeholder_text="DD/MM/AAAA", font=("Calibri", 16))
        txt_c_fecha.pack(fill="x", pady=(2, 12))

        ctk.CTkLabel(f_inner, text="Motivo de la Revisión:", font=("Calibri", 16, "bold"), text_color=("#111827", "#FFF")).pack(anchor="w")
        txt_c_motivo = ctk.CTkEntry(f_inner, height=44, placeholder_text="Ej. Falla de frenos, ruido en motor", font=("Calibri", 16))
        txt_c_motivo.pack(fill="x", pady=(2, 25))

        def confirmar_cita():
            p = txt_c_placa.get().strip().upper()
            f = txt_c_fecha.get().strip()
            if not p or not f:
                messagebox.showwarning("Campos Incompletos ⚠️", "Por favor ingrese la placa y la fecha.")
                return
            self.registrar_log(f"Solicitó cita técnica para vehículo placa {p} en la fecha {f}")
            messagebox.showinfo("Cita Solicitada 📅", f"Su cita para la placa {p} el día {f} ha sido programada con éxito.")
            self.mostrar_inicio_dashboard(self.rol_actual)

        ctk.CTkButton(f_inner, text="📅 Confirmar Solicitud de Cita", height=48, fg_color="#D32F2F", hover_color="#B71C1C", font=("Calibri", 16, "bold"), command=confirmar_cita).pack(fill="x")

    # =========================================================================
    # PANEL PRINCIPAL Y DASHBOARD (SOLUCIÓN DASHBOARD MECÁNICO)
    # =========================================================================
    def mostrar_inicio(self):
        if self.frame_login:
            self.frame_login.destroy()
            self.frame_login = None
        if self.frame_registro:
            self.frame_registro.destroy()
            self.frame_registro = None

        self.btn_theme_login.place_forget()
        self.footer.place_forget()
        self.card_main.place_forget()
        
        self.frame_inicio = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_inicio.pack(fill="both", expand=True)

        self.actualizar_visibilidad_fondo()

        rol_norm = str(self.rol_actual).strip().lower()

        # SIDEBAR DE NAVEGACIÓN
        self.sidebar = ctk.CTkFrame(self.frame_inicio, width=260, corner_radius=0, fg_color=("#FFFFFF", "#121215"))
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        if os.path.exists(self.ruta_logo):
            img_c = self.hacer_imagen_circular(self.ruta_logo, (130, 130))
            img_l = ctk.CTkImage(light_image=img_c, dark_image=img_c, size=(130, 130))
            ctk.CTkLabel(self.sidebar, image=img_l, text="").pack(pady=(20, 15))

        self.btn_menu_activos = {}

        if rol_norm in ["admin", "administrador"]:
            menu_opciones = [
                ("inicio", "🏠  Inicio", lambda: self.mostrar_inicio_dashboard(self.rol_actual)),
                ("vehiculos", "🚗  Registrar Vehículo", self.abrir_registro_vehiculo),
                ("buscar", "🔎  Buscar Vehículo", self.buscar_vehiculo_por_placa),
                ("usuarios", "👥  Usuarios", lambda: self.mostrar_lista_usuarios("Todos", "Todos")),
                ("logs", "📜  Auditoría", self.mostrar_historial_logs),
            ]
        elif rol_norm in ["mecanico", "mecánico"]:
            menu_opciones = [
                ("inicio", "🏠  Inicio", lambda: self.mostrar_inicio_dashboard(self.rol_actual)),
                ("vehiculos", "🚗  Recepción Carro", self.abrir_registro_vehiculo),
                ("buscar", "🔎  Buscar Vehículo", self.buscar_vehiculo_por_placa),
                ("caja", "💵  Cierre Caja", self.abrir_cierre_caja),
            ]
        else:  # Cliente
            menu_opciones = [
                ("inicio", "🏠  Inicio", lambda: self.mostrar_inicio_dashboard(self.rol_actual)),
                ("vehiculos", "🚗  Registrar Mi Vehículo", self.abrir_registro_vehiculo),
                ("buscar", "🔎  Mi Vehículo", self.buscar_vehiculo_por_placa),
                ("citas", "📅  Agendar Cita", self.abrir_agendar_cita),
            ]

        for clave, texto, comando in menu_opciones:
            btn = ctk.CTkButton(
                self.sidebar, text=texto, anchor="w", height=46, 
                corner_radius=8, fg_color="transparent", text_color=("#222222", "#E0E0E0"), 
                font=("Calibri", 15, "bold"), command=comando
            )
            btn.pack(fill="x", padx=12, pady=3)
            self.btn_menu_activos[clave] = btn

        bottom_sidebar = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        bottom_sidebar.pack(side="bottom", fill="x", padx=12, pady=20)

        btn_theme_sidebar = ctk.CTkButton(
            bottom_sidebar, text="☀️ / 🌙 Cambiar Tema", anchor="w", height=40,
            corner_radius=8, fg_color=("#E5E7EB", "#1E1E22"), text_color=("#111827", "#FFFFFF"),
            hover_color=("#D1D5DB", "#2B2B30"), font=("Calibri", 14, "bold"),
            command=self.cambiar_tema
        )
        btn_theme_sidebar.pack(fill="x", pady=(0, 8))

        btn_salir = ctk.CTkButton(
            bottom_sidebar, text="🚪  Cerrar Sesión", anchor="w", height=44, 
            corner_radius=8, fg_color="transparent", hover_color=("#F5F5F5", "#2B2B2B"), 
            text_color=("#222222", "#E0E0E0"), font=("Calibri", 15, "bold"), 
            command=self.cerrar_sesion
        )
        btn_salir.pack(fill="x")

        # ÁREA PRINCIPAL
        main_content = ctk.CTkFrame(self.frame_inicio, fg_color="transparent")
        main_content.pack(side="right", fill="both", expand=True, padx=25, pady=20)

        top_bar = ctk.CTkFrame(main_content, fg_color="transparent")
        top_bar.pack(fill="x", pady=(0, 15))

        user_header = ctk.CTkFrame(top_bar, fg_color="transparent")
        user_header.pack(side="left")
        
        ctk.CTkLabel(user_header, text="👤", font=("Segoe UI Emoji", 24), text_color="#D32F2F").pack(side="left", padx=(0, 10))
        
        info_header = ctk.CTkFrame(user_header, fg_color="transparent")
        info_header.pack(side="left")
        ctk.CTkLabel(info_header, text=f"¡Bienvenido, {self.usuario_actual}!", font=("Calibri", 22, "bold"), text_color=("#111827", "#FFFFFF")).pack(anchor="w")
        ctk.CTkLabel(info_header, text=f"Panel ejecutivo - Rol: {str(self.rol_actual).strip().capitalize()}", font=("Calibri", 14), text_color=("#6B7280", "#AAAAAA")).pack(anchor="w")

        self.body_scroll = ctk.CTkScrollableFrame(main_content, fg_color="transparent")
        self.body_scroll.pack(fill="both", expand=True)

        self.mostrar_inicio_dashboard(self.rol_actual)

    def mostrar_inicio_dashboard(self, rol_param):
        self.seleccionar_opcion_menu("inicio")

        for widget in self.body_scroll.winfo_children():
            widget.destroy()

        rol_norm = str(rol_param).strip().lower()

        # CONTEOS BD EN TIEMPO REAL
        num_usuarios = self.obtener_conteo_real("SELECT COUNT(*) FROM usuarios")
        num_mecanicos = self.obtener_conteo_real("SELECT COUNT(*) FROM usuarios WHERE LOWER(rol) LIKE '%mecanico%' OR LOWER(rol) LIKE '%mecánico%'")
        num_admins = self.obtener_conteo_real("SELECT COUNT(*) FROM usuarios WHERE LOWER(rol) LIKE '%admin%'")
        num_clientes = self.obtener_conteo_real("SELECT COUNT(*) FROM usuarios WHERE LOWER(rol) LIKE '%cliente%'")
        num_logs = self.obtener_conteo_real("SELECT COUNT(*) FROM logs_sistema")
        num_vehiculos = self.obtener_conteo_real("SELECT COUNT(*) FROM vehiculos")

        grid_frame = ctk.CTkFrame(self.body_scroll, fg_color="transparent")
        grid_frame.pack(fill="x", pady=(10, 20))

        def vincular_evento_clic(widget, funcion):
            widget.bind("<Button-1>", lambda e: funcion())
            for hijo in widget.winfo_children():
                vincular_evento_clic(hijo, funcion)

        def crear_tarjeta_unificada(parent, icono, titulo, cifra, descripcion, comando):
            card = ctk.CTkFrame(
                parent, fg_color=("#FFFFFF", "#18181C"), corner_radius=16, 
                border_width=1, border_color=("#E5E7EB", "#2D2D35"), height=200
            )
            card.pack(side="left", fill="both", expand=True, padx=8)
            card.pack_propagate(False)

            top_f = ctk.CTkFrame(card, fg_color="transparent")
            top_f.pack(fill="x", padx=16, pady=(16, 4))

            icon_box = ctk.CTkFrame(top_f, width=46, height=46, corner_radius=23, fg_color=("#FFF0F0", "#341719"))
            icon_box.pack(side="left")
            icon_box.pack_propagate(False)
            ctk.CTkLabel(icon_box, text=icono, font=("Segoe UI Emoji", 20), text_color="#D32F2F").place(relx=0.5, rely=0.5, anchor="center")

            ctk.CTkLabel(top_f, text=str(cifra), font=("Calibri", 26, "bold"), text_color=("#111827", "#FFFFFF")).pack(side="right")

            ctk.CTkLabel(card, text=titulo, font=("Calibri", 18, "bold"), text_color=("#111827", "#FFFFFF")).pack(pady=(4, 2))
            ctk.CTkLabel(card, text=descripcion, font=("Calibri", 13), text_color=("#6B7280", "#999999"), wraplength=180, justify="center").pack(pady=(0, 10))

            btn_arrow = ctk.CTkFrame(card, width=34, height=34, corner_radius=17, fg_color="#D32F2F")
            btn_arrow.place(relx=0.88, rely=0.84, anchor="center")
            btn_arrow.pack_propagate(False)
            ctk.CTkLabel(btn_arrow, text="➔", font=("Calibri", 15, "bold"), text_color="#FFFFFF").place(relx=0.5, rely=0.5, anchor="center")

            vincular_evento_clic(card, comando)

        if rol_norm in ["admin", "administrador"]:
            crear_tarjeta_unificada(grid_frame, "🚗", "Registrar Vehículo", num_vehiculos, "Gestión e ingreso de autos al taller.", self.abrir_registro_vehiculo)
            crear_tarjeta_unificada(grid_frame, "🔎", "Buscar Vehículo", num_vehiculos, "Consulte el historial de un auto por placa.", self.buscar_vehiculo_por_placa)
            crear_tarjeta_unificada(grid_frame, "👥", "Usuarios", num_usuarios, "Control de cuentas y asignación de roles.", lambda: self.mostrar_lista_usuarios("Todos", "Todos"))
            crear_tarjeta_unificada(grid_frame, "📜", "Auditoría", num_logs, "Historial de logs y acciones del sistema.", self.mostrar_historial_logs)

        elif rol_norm in ["mecanico", "mecánico"]:
            crear_tarjeta_unificada(grid_frame, "🚗", "Recepción Carro", num_vehiculos, "Ingresar auto y registrar datos técnicos.", self.abrir_registro_vehiculo)
            crear_tarjeta_unificada(grid_frame, "🔎", "Buscar Vehículo", num_vehiculos, "Consultar detalles de vehículos por placa.", self.buscar_vehiculo_por_placa)
            crear_tarjeta_unificada(grid_frame, "💵", "Cierre de Caja", "$ 0 COP", "Registrar balance diario y cobros.", self.abrir_cierre_caja)

        else:  # Cliente
            crear_tarjeta_unificada(grid_frame, "🚗", "Registrar Mi Vehículo", num_vehiculos, "Inscribe tu automóvil en nuestra plataforma.", self.abrir_registro_vehiculo)
            crear_tarjeta_unificada(grid_frame, "🔎", "Mi Vehículo", num_vehiculos, "Consultar el estado técnico de su auto.", self.buscar_vehiculo_por_placa)
            crear_tarjeta_unificada(grid_frame, "📅", "Agendar Cita", "0", "Solicitar cita de revisión técnica.", self.abrir_agendar_cita)

        if rol_norm in ["admin", "administrador"]:
            chart_card = ctk.CTkFrame(self.body_scroll, fg_color=("#FFFFFF", "#18181C"), corner_radius=16, border_width=1, border_color=("#E5E7EB", "#2D2D35"), height=300)
            chart_card.pack(fill="x", pady=10, padx=8)
            chart_card.pack_propagate(False)

            ctk.CTkLabel(chart_card, text="📊 Resumen Estadístico de Cuentas del Sistema", font=("Calibri", 18, "bold"), text_color=("#111827", "#FFF")).pack(anchor="w", padx=20, pady=(15, 5))

            bg_canvas = "#FFFFFF" if ctk.get_appearance_mode() == "Light" else "#18181C"
            canvas = Canvas(chart_card, bg=bg_canvas, highlightthickness=0, height=220)
            canvas.pack(fill="both", expand=True, padx=20, pady=(0, 10))

            def dibujar_grafico_grande():
                canvas.update()
                w_width = canvas.winfo_width()
                if w_width < 100:
                    w_width = 800

                roles = [("Administradores", num_admins, "#D32F2F"), ("Mecánicos", num_mecanicos, "#FF5252"), ("Clientes", num_clientes, "#E57373")]
                max_val = max([v for _, v, _ in roles] + [1])
                
                ancho_bar = 100
                gap = 120
                max_h = 130
                
                total_w = (len(roles) * ancho_bar) + ((len(roles) - 1) * gap)
                start_x = (w_width - total_w) / 2

                canvas.create_line(start_x - 30, 170, start_x + total_w + 30, 170, fill="#E5E7EB" if ctk.get_appearance_mode()=="Light" else "#555555", width=2)

                for i, (nombre, val, color) in enumerate(roles):
                    h = int((val / max_val) * max_h) if max_val > 0 else 8
                    if h < 8: h = 8
                    
                    x0 = start_x + i * (ancho_bar + gap)
                    y0 = 170 - h
                    x1 = x0 + ancho_bar
                    y1 = 170

                    canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline="")
                    txt_color = "#111827" if ctk.get_appearance_mode() == "Light" else "#FFFFFF"
                    canvas.create_text(x0 + ancho_bar/2, y0 - 14, text=str(val), fill=txt_color, font=("Calibri", 15, "bold"))
                    canvas.create_text(x0 + ancho_bar/2, 190, text=nombre, fill=txt_color, font=("Calibri", 13, "bold"))

            self.after(150, dibujar_grafico_grande)

    # =========================================================================
    # VALIDACIÓN DE LOGIN Y CIERRE DE SESIÓN
    # =========================================================================
    def validar_login(self):
        usr = self.txt_user_login.get().strip()
        pas = self.txt_pass_login.get().strip()

        if not usr or not pas:
            messagebox.showwarning("Datos Incompletos ⚠️", "Ingrese usuario y contraseña.")
            return

        pass_hash = hashlib.sha256(pas.encode()).hexdigest()

        try:
            conexion = mysql.connector.connect(host="localhost", user="root", password="", database="taller_automotriz_db", port=3306)
            cursor = conexion.cursor(dictionary=True)
            cursor.execute("SELECT id_usuario, nombre_completo, rol, password_hash, estado FROM usuarios WHERE usuario = %s", (usr,))
            user = cursor.fetchone()

            if not user:
                messagebox.showerror("Usuario No Registrado ❌", f"El usuario '{usr}' no existe.")
            elif user['estado'] != 'Activo':
                messagebox.showwarning("Cuenta Inactiva ⚠️", "Esta cuenta ha sido desactivada por la administración.")
            elif user['password_hash'] != pass_hash:
                messagebox.showerror("Contraseña Incorrecta ❌", "La contraseña es incorrecta.")
            else:
                self.usuario_actual = user['nombre_completo']
                self.rol_actual = user['rol']
                self.id_usuario_actual = user['id_usuario']
                cursor.close()
                conexion.close()

                # INICIA SIEMPRE EN MODO CLARO ("Light")
                ctk.set_appearance_mode("Light")

                self.registrar_log("Inicio de sesión exitoso")
                self.mostrar_inicio()
                return

            cursor.close()
            conexion.close()
        except mysql.connector.Error as err:
            messagebox.showerror("Error BD ❌", f"No se pudo conectar a MySQL:\n{err}")

    def guardar_registro(self):
        nombre = self.reg_nombre.get().strip()
        usuario = self.reg_usuario.get().strip()
        correo = self.reg_correo.get().strip()
        telefono = self.reg_telefono.get().strip()
        pass1 = self.reg_pass1.get().strip()
        pass2 = self.reg_pass2.get().strip()

        errores = []
        if not nombre or not usuario or not correo or not telefono or not pass1 or not pass2:
            errores.append("• Todos los campos son obligatorios.")
        if pass1 and pass2 and pass1 != pass2:
            errores.append("• Las contraseñas no coinciden.")

        if errores:
            messagebox.showerror("Errores de Validación ❌", "\n".join(errores))
            return

        pass_hash = hashlib.sha256(pass1.encode()).hexdigest()

        try:
            conexion = mysql.connector.connect(host="localhost", user="root", password="", database="taller_automotriz_db", port=3306)
            cursor = conexion.cursor()
            sql = "INSERT INTO usuarios (nombre_completo, usuario, correo, telefono, password_hash, rol, estado) VALUES (%s, %s, %s, %s, %s, 'Cliente', 'Activo')"
            cursor.execute(sql, (nombre, usuario, correo, telefono, pass_hash))
            conexion.commit()

            cursor.close()
            conexion.close()

            self.usuario_actual = nombre
            self.rol_actual = "Cliente"
            self.registrar_log("Nuevo cliente registrado desde la plataforma pública")

            messagebox.showinfo("Registro Exitoso 🎉", f"¡Cuenta creada correctamente!\nInicie sesión con el usuario: {usuario}")
            self.mostrar_login()

        except mysql.connector.Error as err:
            messagebox.showerror("Error BD ❌", f"Error:\n{err}")

    def cerrar_sesion(self):
        if messagebox.askyesno("Cerrar Sesión 🚪", "¿Desea cerrar la sesión actual?"):
            self.registrar_log("Cerró la sesión")
            if hasattr(self, 'sidebar'): self.sidebar.destroy()
            self.frame_inicio.destroy()
            self.frame_inicio = None
            self.usuario_actual = ""
            self.rol_actual = ""
            self.id_usuario_actual = None
            self.mostrar_login()

if __name__ == "__main__":
    app = AppTallerAutomotriz()
    app.mainloop()