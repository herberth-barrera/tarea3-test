# Expedientes Digitales – Hospital de Diagnóstico (Tarea 3: archivos y versiones)

## Qué hace el sistema
Administra los expedientes de personal del Hospital de Diagnóstico sobre **MySQL (XAMPP)**. Permite registrar empleados, consultar el estado de su expediente, modificar su checklist y eliminar empleados. **Nuevo en la Tarea 3:** subir los documentos de cada expediente (PDF o Word) a MySQL, conservar el historial de versiones, descargar cada versión y ver si un documento está vigente, vencido o es una versión anterior. El resumen clasifica cada expediente según los archivos realmente subidos.

## Cómo ejecutarlo desde cero
1. Abrir el Panel de Control de XAMPP e **iniciar MySQL** (y Apache, para phpMyAdmin).
2. Abrir http://localhost/phpmyadmin/, pestaña **Importar**, elegir `crear_bd.sql` y presionar **Continuar**.
3. Instalar las dependencias: `pip install -r requirements.txt`
4. Ejecutar: `python app.py`
5. Abrir http://127.0.0.1:5000/empleados

Usuario de MySQL: `root`, sin contraseña (valores por defecto de XAMPP).

## Estructura de archivos
```
|-- app.py              # rutas de Flask y lógica del sistema
|-- crear_bd.sql        # crea la base, las tablas y carga datos de ejemplo
|-- requirements.txt    # flask y mysql-connector-python
|-- README.md
|-- templates/
|   |-- base.html       # menú lateral, logo y estructura común de todas las páginas
|   |-- empleados.html, nuevo.html, expediente.html, resumen.html, error.html
|   |-- archivos.html   # listado de archivos y versiones de un empleado
|   |-- subir.html      # formulario de subida (multipart/form-data)
|-- static/
|   |-- style.css       # única hoja de estilos del sitio
|   |-- logo.png        # logo del Hospital de Diagnóstico
```

## Rutas
| Ruta | Método | Función |
|---|---|---|
| http://127.0.0.1:5000/empleados | GET | Listado de empleados con checklist, archivos subidos y estado |
| http://127.0.0.1:5000/empleados/nuevo | GET, POST | Registrar empleado con validación |
| http://127.0.0.1:5000/empleados/editar/1 | GET, POST | Modificar el checklist del expediente |
| http://127.0.0.1:5000/empleados/eliminar/1 | POST | Eliminar empleado, su expediente y sus archivos |
| http://127.0.0.1:5000/empleados/1/archivos | GET | **Listado de archivos y versiones** del empleado, con estado y descarga |
| http://127.0.0.1:5000/empleados/1/archivos/nuevo | GET, POST | **Subir** un documento (crea una versión nueva) |
| http://127.0.0.1:5000/archivos/1/descargar | GET | **Descargar** un archivo (404 si el id no existe) |
| http://127.0.0.1:5000/resumen | GET | Resumen con contadores por clasificación |

## Base de datos (MySQL, base `hospital_hdd`)
- **empleados**: id (PK), codigo (único), nombre, puesto, area, sucursal, fecha_ingreso
- **documentos**: id (PK), nombre, requiere_vencimiento (1 = la fecha de vencimiento es obligatoria; solo el DUI)
- **expediente**: empleado_id (PK, FK), documento_id (PK, FK), entregado
- **archivos** (nueva): id (PK), empleado_id (FK), documento_id (FK), version, nombre_original, tamano, **contenido (LONGBLOB)**, fecha_vencimiento (opcional), fecha_subida

**Llaves foráneas de `archivos`:**
- `archivos.empleado_id` → `empleados.id` con **`ON DELETE CASCADE`**: al eliminar un empleado se borran también todos sus archivos.
- `archivos.documento_id` → `documentos.id` (el tipo de documento).
- `UNIQUE (empleado_id, documento_id, version)`: no puede repetirse una versión del mismo documento.

## Subida de archivos
- Formulario con `method="POST"` y `enctype="multipart/form-data"` y un campo `<input type="file">`. En Flask el archivo se recibe con `request.files`.
- **Tipos permitidos:** `.pdf`, `.doc` y `.docx` (sin importar mayúsculas o minúsculas).
- **Tamaño máximo: 50 MB** (constante `MAX_BYTES` en `app.py`). Como los archivos se guardan en una columna `LONGBLOB`, el servidor MySQL también impone su propio límite, `max_allowed_packet`, que en XAMPP viene en **1 MB**. El programa consulta ese valor y usa **el menor de los dos**, y muestra el límite vigente en el formulario. Así, un archivo demasiado grande nunca corta la conexión: se rechaza con un mensaje claro.
- **Para subir archivos de hasta 50 MB:** abrir `C:\xampp\mysql\bin\my.ini`, en la sección `[mysqld]` poner `max_allowed_packet=64M`, guardar y reiniciar MySQL desde el Panel de XAMPP.
- Flask rechaza de entrada (error 413) cualquier subida mayor a 52 MB.
- **Validaciones (si algo falla no se guarda nada y se muestra un mensaje claro):** tipo de documento elegido, archivo elegido, extensión permitida, archivo no vacío, tamaño máximo, fecha de vencimiento obligatoria para el DUI y fecha con formato válido.
- Los archivos se guardan en MySQL; nunca en disco. Para las pruebas se usan documentos inventados, nunca un DUI real.

## Versiones y estados
- Subir un documento **nunca reemplaza** al anterior. Se calcula la versión siguiente con `SELECT MAX(version)` (la primera es 1) y se inserta una fila nueva.
- El listado muestra todas las versiones, de la más reciente a la más antigua, y **no trae la columna `contenido`**.
- El estado de cada versión se decide con `if/elif/else`:
  - **Versión anterior** (gris): hay otra versión más reciente del mismo documento.
  - **Vencido** (rojo): es la versión más reciente y su fecha de vencimiento ya pasó.
  - **Vigente** (verde): es la versión más reciente y no está vencida.
- Al subir un documento, el checklist del expediente lo marca como entregado.

## Cómo funciona el resumen
`/resumen` lee todos los empleados con sus archivos realmente subidos (subconsultas sobre `archivos`) y los recorre con un `for`. En cada vuelta decide con `if/elif/else`:
- **Completo** (verde): todos los documentos tienen archivo y ninguno está vencido.
- **Con documentos vencidos** (morado): al menos un documento tiene su versión más reciente vencida.
- **Incompleto en proceso** (naranja): tiene algunos archivos, pero no todos.
- **Incompleto sin archivos** (rojo): no ha subido ninguno.

Cada rama suma a un contador, y un acumulador suma los documentos subidos frente a los requeridos.

## Equipo: parte de código y mejora individual de cada integrante
- Nombre 1 (usuario de GitHub): (completar) subida, versiones y descarga de archivos
- Nombre 2 (usuario de GitHub): (completar) mejora individual: ___ (pull request ___)
- Nombre 3 (usuario de GitHub): (completar) mejora individual: ___ (pull request ___)
- Nombre 4 (usuario de GitHub): (completar) mejora individual: ___ (pull request ___)

## Video de pruebas
(completar) Enlace de YouTube: https://youtu.be/...
