# Requirements Document

## Introduction

DiabetCare S.A. es una aplicación web clínica para la gestión y análisis de pacientes diabéticos. El sistema permite a los profesionales de salud visualizar, filtrar y analizar datos clínicos almacenados en una base de datos PostgreSQL local (`diabetcare`). La aplicación incluye scripts de inicialización de base de datos, carga masiva de datos desde CSV, y una interfaz web construida con Flask que presenta información institucional, registros clínicos filtrables y la capacidad de recargar el dataset desde la fuente original.

---

## Glossary

- **DiabetCare**: El sistema de gestión clínica de pacientes diabéticos descrito en este documento.
- **Flask_App**: El servidor web Flask que sirve la interfaz de usuario y expone los endpoints HTTP.
- **DB_Initializer**: El script Python responsable de crear todas las tablas en la base de datos PostgreSQL.
- **CSV_Loader**: El script Python responsable de cargar el archivo `diabetes_dataset.csv` en la tabla `diabetes_clinical`.
- **Dataset_Reloader**: El componente de la Flask_App que descarga y recarga el dataset desde la web.
- **diabetes_clinical**: La tabla principal de PostgreSQL que almacena los registros clínicos de pacientes.
- **diabetes_dataset.csv**: El archivo CSV con 100,000 registros clínicos de pacientes, ubicado en `dataset/diabetes_dataset.csv`.
- **Registro_Clínico**: Una fila en la tabla `diabetes_clinical` que representa los datos clínicos de un paciente.
- **Usuario**: El profesional de salud o administrador que interactúa con la interfaz web de DiabetCare.
- **psycopg2**: La librería Python utilizada para conectarse y operar sobre PostgreSQL.
- **pandas**: La librería Python utilizada para leer y procesar el archivo CSV.

---

## Requirements

### Requirement 1: Creación de Tablas en la Base de Datos

**User Story:** Como administrador del sistema, quiero ejecutar un script que cree todas las tablas necesarias en PostgreSQL, para que la base de datos esté lista para recibir datos clínicos y operacionales.

#### Acceptance Criteria

1. THE DB_Initializer SHALL conectarse a la base de datos PostgreSQL local `diabetcare` usando credenciales configurables (host, puerto, usuario, contraseña).
2. THE DB_Initializer SHALL crear la tabla `diabetes_clinical` con las 17 columnas especificadas: `id_paciente` (SERIAL PRIMARY KEY), `year`, `gender`, `age`, `location`, `race_african_american`, `race_asian`, `race_caucasian`, `race_hispanic`, `race_other`, `hypertension`, `heart_disease`, `smoking_history`, `bmi`, `hba1c_level`, `blood_glucose_level`, `diabetes`.
3. THE DB_Initializer SHALL crear las 10 tablas adicionales (`clinicas`, `medicos`, `empleados`, `pacientes_registrados`, `consultas`, `medicamentos`, `recetas`, `equipos_medicos`, `alertas`, `seguimientos`), cada una con exactamente una columna SERIAL PRIMARY KEY.
4. WHEN el DB_Initializer detecta que una tabla ya existe, THE DB_Initializer SHALL omitir su creación sin generar un error, de modo que el script sea idempotente.
5. WHEN el DB_Initializer completa la ejecución, THE DB_Initializer SHALL imprimir por consola el número de tablas nuevamente creadas en esa ejecución; IF ninguna tabla fue creada (todas ya existían), THE DB_Initializer SHALL imprimir cero.
6. IF la conexión a la base de datos falla, THEN THE DB_Initializer SHALL imprimir un mensaje de error que incluya el destino de conexión y el motivo del fallo, y terminar con código de salida distinto de cero.
7. IF ocurre un error de SQL durante la creación de alguna tabla, THEN THE DB_Initializer SHALL imprimir el nombre de la tabla afectada y el error, y terminar con código de salida distinto de cero sin dejar la base de datos en estado parcialmente creado.

---

### Requirement 2: Carga del Dataset CSV a PostgreSQL

**User Story:** Como administrador del sistema, quiero ejecutar un script que cargue el archivo `diabetes_dataset.csv` en la tabla `diabetes_clinical`, para que los 100,000 registros clínicos estén disponibles para análisis.

#### Acceptance Criteria

1. THE CSV_Loader SHALL leer el archivo `dataset/diabetes_dataset.csv` usando pandas y cargar sus registros en la tabla `diabetes_clinical` de PostgreSQL.
2. THE CSV_Loader SHALL mapear las columnas del CSV a las columnas de la tabla: `race:AfricanAmerican` → `race_african_american`, `race:Asian` → `race_asian`, `race:Caucasian` → `race_caucasian`, `race:Hispanic` → `race_hispanic`, `race:Other` → `race_other`, `hbA1c_level` → `hba1c_level`; las columnas `year`, `gender`, `age`, `location`, `hypertension`, `heart_disease`, `smoking_history`, `bmi`, `blood_glucose_level` y `diabetes` se mapearán con el mismo nombre de columna en la tabla.
3. WHEN el CSV_Loader inicia la carga, THE CSV_Loader SHALL truncar la tabla `diabetes_clinical` antes de insertar los nuevos registros, para evitar duplicados.
4. THE CSV_Loader SHALL insertar los registros en lotes de 1,000 filas.
5. WHEN el CSV_Loader completa la carga exitosamente, THE CSV_Loader SHALL imprimir por consola el número total de registros insertados.
6. IF el archivo `dataset/diabetes_dataset.csv` no se encuentra en la ruta esperada, THEN THE CSV_Loader SHALL imprimir un mensaje de error indicando la ruta buscada y terminar la ejecución con código de salida distinto de cero.
7. IF ocurre un error durante la inserción de un lote, THEN THE CSV_Loader SHALL realizar un rollback de todos los registros insertados en la ejecución actual, imprimir el error y terminar la ejecución con código de salida distinto de cero.
8. THE CSV_Loader SHALL cargar los valores de las columnas numéricas (`bmi`, `hba1c_level`, `blood_glucose_level`) tal como aparecen en el CSV, sin aplicar redondeo ni transformación aritmética.

---

### Requirement 3: Página de Inicio Institucional

**User Story:** Como usuario, quiero ver una página de inicio con la información institucional de DiabetCare y el total de registros clínicos, para conocer la misión, visión y escala del sistema.

#### Acceptance Criteria

1. WHEN el Usuario accede a la ruta `/` de la Flask_App, THE Flask_App SHALL renderizar la página de inicio con el nombre "DiabetCare S.A.".
2. THE Flask_App SHALL mostrar en la página de inicio la misión de DiabetCare: "Proveer herramientas tecnológicas de análisis clínico para mejorar el diagnóstico y seguimiento de pacientes diabéticos".
3. THE Flask_App SHALL mostrar en la página de inicio la visión de DiabetCare: "Ser la plataforma líder en gestión clínica de diabetes en Latinoamérica".
4. WHEN la página de inicio se carga, THE Flask_App SHALL consultar la tabla `diabetes_clinical` y mostrar el total de registros almacenados como un número entero sin separador de miles.
5. IF la consulta del total de registros falla, THEN THE Flask_App SHALL mostrar el valor "N/D" en lugar del total.
6. IF la consulta del total de registros falla, THEN THE Flask_App SHALL registrar el error en el log del servidor; THE Flask_App SHALL registrar errores únicamente cuando la consulta falle, no cuando se complete exitosamente.
7. THE Flask_App SHALL incluir en la página de inicio un enlace de navegación hacia la ruta `/registros`.

---

### Requirement 4: Página de Registros Clínicos con Filtros

**User Story:** Como usuario, quiero ver y filtrar los registros de la tabla `diabetes_clinical`, para analizar subconjuntos específicos de pacientes según criterios clínicos relevantes.

#### Acceptance Criteria

1. WHEN el Usuario accede a la ruta `/registros` de la Flask_App, THE Flask_App SHALL renderizar una tabla HTML con los registros de `diabetes_clinical`.
2. THE Flask_App SHALL mostrar en la tabla las columnas: `id_paciente`, `year`, `gender`, `age`, `location`, `hypertension`, `heart_disease`, `smoking_history`, `bmi`, `hba1c_level`, `blood_glucose_level`, `diabetes`.
3. THE Flask_App SHALL proveer controles de filtro tipo dropdown para los campos `gender`, `diabetes`, `hypertension` y `smoking_history`; las opciones de cada dropdown se poblarán con los valores distintos presentes en `diabetes_clinical`, más una opción vacía "sin filtro" como selección por defecto.
4. WHEN el Usuario selecciona un valor no vacío en uno o más dropdowns y envía el formulario, THE Flask_App SHALL ejecutar una consulta SQL parametrizada que retorne únicamente los registros que coincidan con todos los filtros activos, y restablecer la paginación a la página 1.
5. WHEN el Usuario no selecciona ningún filtro (todos los dropdowns en "sin filtro"), THE Flask_App SHALL mostrar todos los registros de `diabetes_clinical`.
6. THE Flask_App SHALL paginar los resultados mostrando un máximo de 100 registros por página, con controles de navegación que permitan ir a la página siguiente, anterior, primera y última.
7. THE Flask_App SHALL mostrar el número total de registros que coinciden con los filtros activos.
8. IF la consulta de registros falla, THEN THE Flask_App SHALL registrar el detalle del error en el log del servidor y mostrar al usuario un mensaje que indique que los registros no pudieron recuperarse.
9. THE Flask_App SHALL construir todas las consultas SQL usando parámetros vinculados (parameterized queries) para prevenir inyección SQL.

---

### Requirement 5: Recarga del Dataset desde la Web

**User Story:** Como administrador, quiero recargar el dataset clínico desde la fuente original en la web, para mantener los datos actualizados sin intervención manual en el servidor.

#### Acceptance Criteria

1. THE Flask_App SHALL mostrar un botón "Recargar Dataset" accesible desde la página de registros clínicos.
2. WHEN el Usuario hace clic en el botón "Recargar Dataset", THE Dataset_Reloader SHALL establecer el estado de la operación como IN_PROGRESS y proceder a descargar el archivo CSV desde la URL de origen configurada en la aplicación.
3. WHEN la descarga del CSV se completa exitosamente, THE Dataset_Reloader SHALL invocar el proceso de carga equivalente al CSV_Loader para reemplazar los datos en `diabetes_clinical`; IF el paso de carga falla, THE Dataset_Reloader SHALL preservar los datos existentes en `diabetes_clinical`.
4. WHEN la recarga completa exitosamente, THE Flask_App SHALL mostrar al Usuario un mensaje de confirmación con el número de registros cargados.
5. IF la descarga del CSV falla por error de red o si transcurren 30 segundos sin respuesta del servidor remoto, THEN THE Dataset_Reloader SHALL cancelar la operación, mostrar al Usuario un mensaje de error y no modificar los datos existentes en `diabetes_clinical`.
6. IF el archivo descargado no contiene exactamente las columnas esperadas según el esquema de origen configurado, o si el archivo está vacío, THEN THE Dataset_Reloader SHALL rechazar la carga, mostrar un mensaje de error al Usuario y preservar los datos existentes en `diabetes_clinical`.
7. WHILE la recarga del dataset está en progreso, THE Flask_App SHALL mostrar al Usuario un indicador visual de carga para comunicar que la operación está en curso.
8. WHEN una recarga está en estado IN_PROGRESS, THE Flask_App SHALL deshabilitar el botón "Recargar Dataset" para prevenir recargas concurrentes.
9. THE Dataset_Reloader SHALL aplicar un timeout de 30 segundos a la solicitud de descarga del CSV remoto.

---

### Requirement 6: Interfaz de Usuario y Estilos

**User Story:** Como usuario, quiero una interfaz web visualmente coherente y navegable, para usar DiabetCare de forma intuitiva en un entorno clínico.

#### Acceptance Criteria

1. THE Flask_App SHALL aplicar estilos CSS desde una única hoja de estilos compartida referenciada en todas las páginas.
2. THE Flask_App SHALL incluir una barra de navegación presente en todas las páginas con enlaces a: Inicio (`/`) y Registros Clínicos (`/registros`).
3. THE Flask_App SHALL utilizar una paleta de colores con tonos azules y blancos que cumpla un ratio de contraste mínimo de 4.5:1 (WCAG AA) entre texto y fondo.
4. THE Flask_App SHALL renderizar sin errores de layout en Chrome, Firefox y Edge en una resolución de ventana de 1280×720 píxeles o superior.
5. THE Flask_App SHALL usar plantillas HTML con un template base heredado por todas las páginas, de modo que la barra de navegación y el pie de página aparezcan sin duplicación de código HTML.
6. WHERE la tabla de registros clínicos tiene resultados que superan 100 filas, THE Flask_App SHALL mostrar controles de paginación con al menos los botones "Anterior" y "Siguiente" visibles en la misma página que la tabla.
