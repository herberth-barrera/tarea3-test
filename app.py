import io
import os
import mysql.connector
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, abort, send_file

app = Flask(__name__)

SUCURSALES = ["Escalón", "Santa Elena", "Colonia Médica"]

# --- TAREA 3: configuración de la subida de archivos ---
EXTENSIONES_PERMITIDAS = (".pdf", ".doc", ".docx")
# Tamaño máximo que valida el programa. OJO: el servidor MySQL tiene su propio límite
# (max_allowed_packet, 1 MB por defecto en XAMPP). El programa lo consulta y usa el menor de los dos.
MAX_BYTES = 50 * 1024 * 1024
# Tope duro de Flask: rechaza de entrada cualquier subida mucho mayor (error 413)
app.config["MAX_CONTENT_LENGTH"] = MAX_BYTES + 2 * 1024 * 1024


def conectar():
    # En XAMPP el usuario es root y la contraseña va vacía
    return mysql.connector.connect(host="localhost", user="root", password="",
                                   database="hospital_hdd", charset="utf8mb4")


def formato_tamano(n):
    """Convierte bytes a un texto legible: 921 KB, 50 MB..."""
    if n >= 1024 * 1024:
        valor = n / (1024 * 1024)
        return ("%d MB" % valor) if valor == int(valor) else ("%.1f MB" % valor)
    if n >= 1024:
        return "%d KB" % (n // 1024)
    return "%d B" % n


@app.template_filter("iniciales")
def iniciales(nombre):
    """Iniciales para el avatar: 'Camila Herrera' -> 'CH'."""
    partes = nombre.split()
    if not partes:
        return "?"
    return (partes[0][0] + (partes[-1][0] if len(partes) > 1 else "")).upper()


def limite_efectivo(cursor):
    """El menor entre el máximo del programa y lo que acepta el servidor MySQL (con margen)."""
    cursor.execute("SELECT @@max_allowed_packet AS paquete")
    paquete = int(cursor.fetchone()["paquete"])
    return min(MAX_BYTES, int(paquete * 0.9))


@app.errorhandler(mysql.connector.Error)
def error_mysql(e):
    print("Error de MySQL:", e)
    if "Lost connection" in str(e) or "max_allowed_packet" in str(e):
        mensaje = ("La conexión con MySQL se cortó, normalmente por un archivo más grande que "
                   "max_allowed_packet. Aumenta ese valor en el my.ini de XAMPP y reinicia MySQL.")
    else:
        mensaje = ("Verifica que MySQL esté iniciado en XAMPP y que importaste crear_bd.sql "
                   "en phpMyAdmin.")
    return render_template("error.html", titulo="No se pudo usar la base de datos",
                           mensaje=mensaje, detalle=str(e)), 500


# --- TAREA 3 ---
@app.errorhandler(413)
def archivo_demasiado_grande(e):
    return render_template("error.html", titulo="Archivo demasiado grande",
                           mensaje="El archivo supera el tamaño máximo permitido (%s). "
                                   "Vuelve atrás y elige uno más liviano." % formato_tamano(MAX_BYTES),
                           detalle=""), 413


@app.errorhandler(404)
def no_encontrado(e):
    return render_template("error.html", titulo="Página no encontrada",
                           mensaje="El registro o la página que buscas no existe.", detalle=""), 404


def obtener_empleados():
    """Empleados con su checklist, sus archivos subidos y sus documentos vencidos (JOIN y subconsultas)."""
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    cursor.execute("""
        SELECT e.*,
               CAST(COALESCE(SUM(x.entregado), 0) AS UNSIGNED) AS entregados,
               COUNT(x.documento_id) AS total,
               (SELECT COUNT(DISTINCT a.documento_id) FROM archivos a
                WHERE a.empleado_id = e.id) AS con_archivo,
               (SELECT COUNT(*) FROM archivos a
                WHERE a.empleado_id = e.id AND a.fecha_vencimiento < CURDATE()
                  AND a.version = (SELECT MAX(a2.version) FROM archivos a2
                                   WHERE a2.empleado_id = a.empleado_id
                                     AND a2.documento_id = a.documento_id)) AS vencidos
        FROM empleados e
        LEFT JOIN expediente x ON x.empleado_id = e.id
        GROUP BY e.id
        ORDER BY e.id
    """)
    filas = cursor.fetchall()
    cursor.close()
    conexion.close()
    return filas


@app.route("/")
def inicio():
    return redirect("/empleados")


# ---------- CONSULTAR ----------
@app.route("/empleados")
def listar():
    filas = obtener_empleados()
    empleados = []
    completos = 0
    con_vencidos = 0
    docs_subidos = 0
    docs_requeridos = 0
    for fila in filas:
        docs_subidos = docs_subidos + fila["con_archivo"]
        docs_requeridos = docs_requeridos + fila["total"]
        if fila["total"] > 0 and fila["con_archivo"] == fila["total"] and fila["vencidos"] == 0:
            estado, clase = "Completo", "completo"
            completos = completos + 1
        elif fila["vencidos"] > 0:
            estado, clase = "Con vencidos", "vencidos"
            con_vencidos = con_vencidos + 1
        else:
            estado, clase = "Incompleto", "incompleto"
        empleados.append({"datos": fila, "estado": estado, "clase": clase})
    kpis = {"total": len(filas), "completos": completos, "con_vencidos": con_vencidos,
            "docs_subidos": docs_subidos, "docs_requeridos": docs_requeridos}
    return render_template("empleados.html", empleados=empleados, kpis=kpis)


# ---------- REGISTRAR ----------
@app.route("/empleados/nuevo", methods=["GET", "POST"])
def nuevo():
    error = ""
    datos = {"codigo": "", "nombre": "", "puesto": "", "area": "", "sucursal": "", "fecha_ingreso": ""}
    if request.method == "POST":
        for campo in datos:
            datos[campo] = request.form.get(campo, "").strip()

        conexion = conectar()
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("SELECT id FROM empleados WHERE codigo = %s", (datos["codigo"],))
        repetido = cursor.fetchone()

        fecha_valida = True
        try:
            datetime.strptime(datos["fecha_ingreso"], "%Y-%m-%d")
        except ValueError:
            fecha_valida = False

        if "" in datos.values():
            error = "Todos los campos son obligatorios."
        elif datos["sucursal"] not in SUCURSALES:
            error = "Selecciona una sucursal válida."
        elif not fecha_valida:
            error = "La fecha de ingreso no es válida."
        elif repetido:
            error = "Ya existe un empleado con ese código."
        else:
            cursor.execute(
                "INSERT INTO empleados (codigo, nombre, puesto, area, sucursal, fecha_ingreso) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (datos["codigo"], datos["nombre"], datos["puesto"], datos["area"],
                 datos["sucursal"], datos["fecha_ingreso"]))
            emp_id = cursor.lastrowid
            cursor.execute("SELECT id FROM documentos")
            for doc in cursor.fetchall():
                cursor.execute(
                    "INSERT INTO expediente (empleado_id, documento_id, entregado) VALUES (%s, %s, 0)",
                    (emp_id, doc["id"]))
            conexion.commit()
            cursor.close()
            conexion.close()
            return redirect("/empleados")
        cursor.close()
        conexion.close()
    return render_template("nuevo.html", error=error, datos=datos, sucursales=SUCURSALES)


# ---------- MODIFICAR (estado de los documentos del expediente) ----------
@app.route("/empleados/editar/<int:emp_id>", methods=["GET", "POST"])
def editar(emp_id):
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    cursor.execute("SELECT * FROM empleados WHERE id = %s", (emp_id,))
    empleado = cursor.fetchone()
    if empleado is None:
        cursor.close()
        conexion.close()
        abort(404)
    cursor.execute("""
        SELECT d.id, d.nombre, x.entregado
        FROM expediente x JOIN documentos d ON d.id = x.documento_id
        WHERE x.empleado_id = %s ORDER BY d.id
    """, (emp_id,))
    docs = cursor.fetchall()

    error = ""
    if request.method == "POST":
        validos = {str(d["id"]) for d in docs}
        marcados = request.form.getlist("doc")
        if any(m not in validos for m in marcados):
            error = "Se recibió un documento que no pertenece al expediente."
        else:
            cursor.execute("UPDATE expediente SET entregado = 0 WHERE empleado_id = %s", (emp_id,))
            for m in marcados:
                cursor.execute(
                    "UPDATE expediente SET entregado = 1 WHERE empleado_id = %s AND documento_id = %s",
                    (emp_id, int(m)))
            conexion.commit()
            cursor.close()
            conexion.close()
            return redirect("/empleados")
    cursor.close()
    conexion.close()
    return render_template("expediente.html", empleado=empleado, docs=docs, error=error)


# ---------- ELIMINAR ----------
@app.route("/empleados/eliminar/<int:emp_id>", methods=["POST"])
def eliminar(emp_id):
    conexion = conectar()
    cursor = conexion.cursor()
    # Primero los hijos y luego el padre: no quedan registros huérfanos
    # (la llave foránea con ON DELETE CASCADE también lo garantiza)
    cursor.execute("DELETE FROM archivos WHERE empleado_id = %s", (emp_id,))   # TAREA 3
    cursor.execute("DELETE FROM expediente WHERE empleado_id = %s", (emp_id,))
    cursor.execute("DELETE FROM empleados WHERE id = %s", (emp_id,))
    conexion.commit()
    cursor.close()
    conexion.close()
    return redirect("/empleados")


# ---------- TAREA 3: LISTADO DE ARCHIVOS Y VERSIONES ----------
def texto_dias(n):
    return "1 día" if n == 1 else "%d días" % n


@app.route("/empleados/<int:emp_id>/archivos")
def ver_archivos(emp_id):
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    cursor.execute("SELECT * FROM empleados WHERE id = %s", (emp_id,))
    empleado = cursor.fetchone()
    if empleado is None:
        cursor.close()
        conexion.close()
        abort(404)
    # Solo las columnas que se muestran: NO se trae la columna contenido
    cursor.execute("""
        SELECT a.id, a.documento_id, d.nombre AS documento, a.version, a.nombre_original,
               a.tamano, a.fecha_vencimiento, a.fecha_subida
        FROM archivos a JOIN documentos d ON d.id = a.documento_id
        WHERE a.empleado_id = %s
        ORDER BY d.id, a.version DESC
    """, (emp_id,))
    filas = cursor.fetchall()
    cursor.execute("""
        SELECT d.id, d.nombre FROM documentos d
        WHERE d.id NOT IN (SELECT documento_id FROM archivos WHERE empleado_id = %s)
        ORDER BY d.id
    """, (emp_id,))
    pendientes = cursor.fetchall()
    cursor.close()
    conexion.close()

    hoy = date.today()
    grupos = []      # una tarjeta por documento, con todas sus versiones
    por_documento = {}
    vigentes = 0
    vencidos = 0
    for fila in filas:
        # Como vienen de la versión más reciente a la más antigua, la primera de cada documento es la última
        es_ultima = fila["documento_id"] not in por_documento
        vence = fila["fecha_vencimiento"]
        aviso = ""
        if not es_ultima:
            estado, clase = "Versión anterior", "anterior"
        elif vence is not None and vence < hoy:
            estado, clase = "Vencido", "vencido"
            aviso = "Venció hace " + texto_dias((hoy - vence).days)
            vencidos = vencidos + 1
        else:
            estado, clase = "Vigente", "vigente"
            if vence == hoy:
                aviso = "Vence hoy"
            elif vence is not None:
                aviso = "Vence en " + texto_dias((vence - hoy).days)
            vigentes = vigentes + 1
        es_pdf = os.path.splitext(fila["nombre_original"])[1].lower() == ".pdf"
        item = {"datos": fila, "estado": estado, "clase": clase, "aviso": aviso,
                "tamano": formato_tamano(fila["tamano"]),
                "tipo": "pdf" if es_pdf else "word", "etiqueta": "PDF" if es_pdf else "DOC"}
        if es_ultima:
            grupo = {"documento_id": fila["documento_id"], "nombre": fila["documento"],
                     "ultima": item, "versiones": [item]}
            por_documento[fila["documento_id"]] = grupo
            grupos.append(grupo)
        else:
            por_documento[fila["documento_id"]]["versiones"].append(item)

    resumen_archivos = {"subidos": len(grupos), "total": len(grupos) + len(pendientes),
                        "vigentes": vigentes, "vencidos": vencidos, "pendientes": len(pendientes)}
    return render_template("archivos.html", empleado=empleado, grupos=grupos,
                           pendientes=pendientes, r=resumen_archivos)


# ---------- TAREA 3: SUBIR ARCHIVO (crea una versión nueva) ----------
@app.route("/empleados/<int:emp_id>/archivos/nuevo", methods=["GET", "POST"])
def subir(emp_id):
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    cursor.execute("SELECT * FROM empleados WHERE id = %s", (emp_id,))
    empleado = cursor.fetchone()
    if empleado is None:
        cursor.close()
        conexion.close()
        abort(404)
    cursor.execute("SELECT id, nombre, requiere_vencimiento FROM documentos ORDER BY id")
    documentos = cursor.fetchall()

    error = ""
    limite = limite_efectivo(cursor)
    datos = {"documento_id": request.args.get("documento", ""), "fecha_vencimiento": ""}
    if request.method == "POST":
        datos["documento_id"] = request.form.get("documento_id", "").strip()
        datos["fecha_vencimiento"] = request.form.get("fecha_vencimiento", "").strip()

        archivo = request.files.get("archivo")
        nombre = ""
        contenido = b""
        if archivo is not None and archivo.filename:
            # Solo el nombre, sin carpetas; el nombre nunca se usa como ruta en disco
            nombre = archivo.filename.replace("\\", "/").split("/")[-1].strip()[:255]
            contenido = archivo.read()
        extension = os.path.splitext(nombre)[1].lower()

        documento = None
        for d in documentos:
            if str(d["id"]) == datos["documento_id"]:
                documento = d

        fecha_valida = True
        if datos["fecha_vencimiento"] != "":
            try:
                datetime.strptime(datos["fecha_vencimiento"], "%Y-%m-%d")
            except ValueError:
                fecha_valida = False

        if documento is None:
            error = "Selecciona el tipo de documento."
        elif nombre == "":
            error = "Selecciona un archivo."
        elif extension not in EXTENSIONES_PERMITIDAS:
            error = "Solo se permiten archivos PDF, DOC o DOCX."
        elif len(contenido) == 0:
            error = "El archivo está vacío."
        elif len(contenido) > limite:
            if limite < MAX_BYTES:
                error = ("El archivo supera el máximo que acepta el servidor MySQL (%s). Para subir "
                         "archivos más grandes, aumenta max_allowed_packet en el my.ini de XAMPP "
                         "y reinicia MySQL." % formato_tamano(limite))
            else:
                error = "El archivo supera el tamaño máximo de %s." % formato_tamano(limite)
        elif documento["requiere_vencimiento"] and datos["fecha_vencimiento"] == "":
            error = "Este documento requiere fecha de vencimiento."
        elif not fecha_valida:
            error = "La fecha de vencimiento no es válida."
        else:
            # Versión siguiente: la primera es 1; subir nunca reemplaza a la anterior
            cursor.execute(
                "SELECT MAX(version) AS ultima FROM archivos WHERE empleado_id = %s AND documento_id = %s",
                (emp_id, documento["id"]))
            fila = cursor.fetchone()
            version = (fila["ultima"] or 0) + 1
            cursor.execute(
                "INSERT INTO archivos (empleado_id, documento_id, version, nombre_original, tamano, "
                "contenido, fecha_vencimiento) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (emp_id, documento["id"], version, nombre, len(contenido), contenido,
                 datos["fecha_vencimiento"] or None))
            # Un documento subido cuenta como entregado en el checklist del expediente
            cursor.execute(
                "UPDATE expediente SET entregado = 1 WHERE empleado_id = %s AND documento_id = %s",
                (emp_id, documento["id"]))
            conexion.commit()
            cursor.close()
            conexion.close()
            return redirect("/empleados/%d/archivos" % emp_id)
    cursor.close()
    conexion.close()
    return render_template("subir.html", empleado=empleado, documentos=documentos, datos=datos,
                           error=error, limite_texto=formato_tamano(limite),
                           limitado_por_mysql=limite < MAX_BYTES)


# ---------- TAREA 3: DESCARGAR ----------
@app.route("/archivos/<int:archivo_id>/descargar")
def descargar(archivo_id):
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    cursor.execute("SELECT nombre_original, contenido FROM archivos WHERE id = %s", (archivo_id,))
    fila = cursor.fetchone()
    cursor.close()
    conexion.close()
    if fila is None:
        abort(404)
    return send_file(io.BytesIO(fila["contenido"]), as_attachment=True,
                     download_name=fila["nombre_original"])


# ---------- RESUMEN (repetición + decisión), ahora con los archivos realmente subidos ----------
@app.route("/resumen")
def resumen():
    filas = obtener_empleados()
    completos = 0
    con_vencidos = 0
    en_proceso = 0
    sin_archivos = 0
    docs_subidos = 0
    docs_requeridos = 0
    detalle = []
    for fila in filas:
        docs_subidos = docs_subidos + fila["con_archivo"]
        docs_requeridos = docs_requeridos + fila["total"]
        if fila["total"] > 0 and fila["con_archivo"] == fila["total"] and fila["vencidos"] == 0:
            completos = completos + 1
            clase, estado = "completo", "Completo (todos subidos y vigentes)"
        elif fila["vencidos"] > 0:
            con_vencidos = con_vencidos + 1
            clase, estado = "vencidos", "Con documentos vencidos"
        elif fila["con_archivo"] > 0:
            en_proceso = en_proceso + 1
            clase, estado = "proceso", "Incompleto (en proceso)"
        else:
            sin_archivos = sin_archivos + 1
            clase, estado = "vacio", "Incompleto (sin archivos)"
        detalle.append({"datos": fila, "estado": estado, "clase": clase})
    return render_template("resumen.html", detalle=detalle, total=len(filas),
                           completos=completos, con_vencidos=con_vencidos,
                           en_proceso=en_proceso, sin_archivos=sin_archivos,
                           docs_subidos=docs_subidos, docs_requeridos=docs_requeridos)


if __name__ == "__main__":
    app.run(debug=True)
