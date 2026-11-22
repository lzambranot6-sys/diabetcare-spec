# DiabetCare

## Video de presentación

[Ver video.](https://www.youtube.com/watch?v=7VcCo7PR0RU)



## Descripción

DiabetCare es una aplicación web para apoyar la gestión clínica y el análisis de información relacionada con la diabetes. Reúne herramientas para profesionales de salud, instituciones, analistas y pacientes en un mismo sistema.

El proyecto combina la operación clínica con paneles e informes que ayudan a consultar y analizar los registros disponibles.

## Funcionalidades

- **Pacientes y atención clínica:** consulta de pacientes, historias clínicas, recetas, laboratorio, derivaciones y seguimiento de diabetes.
- **Citas:** consulta y gestión de la agenda según el rol y el ámbito de cada usuario.
- **Portal del paciente:** acceso a citas, diagnósticos, recetas, derivaciones y notificaciones. Los pacientes pueden consultar sus citas y contactar a su médico o clínica para solicitar cambios.
- **Clínicas y consultorios:** espacios de trabajo para instituciones y médicos independientes, con afiliaciones sujetas a aprobación.
- **Análisis e informes:** indicadores, filtros, gráficos e informes exportables en PDF.
- **Administración y seguridad:** gestión de usuarios, roles, permisos, sesiones y auditoría.
- **Procesamiento de datos:** extracción, transformación, carga y sincronización de información para análisis.

## Roles

| Rol | Función general |
| --- | --- |
| Administrador global | Gestiona usuarios, roles, instituciones y configuración general. |
| Administrador de clínica | Gestiona los recursos y operaciones autorizadas de su institución. |
| Médico | Atiende a sus pacientes y trabaja con la agenda y los recursos clínicos de su ámbito. |
| Analista | Consulta información e informes de acuerdo con sus permisos. |
| Paciente | Consulta su información y sus citas en el portal. |

Los permisos efectivos dependen de la configuración y de los roles asignados a cada cuenta.

## Tecnologías

- Python, Flask, Flask-Login y Jinja2.
- PostgreSQL para la información operativa.
- ClickHouse para consultas y análisis de datos.
- Apache Airflow para la orquestación de procesos de datos.
- HTML, CSS y JavaScript para la interfaz.
- pytest para pruebas automatizadas y ReportLab para informes PDF.

## Estructura principal

| Ruta | Contenido |
| --- | --- |
| `app.py` | Aplicación Flask y rutas principales. |
| `templates/` y `static/` | Plantillas, estilos y recursos de la interfaz. |
| `P1_dashboard/` a `P4_dimensiones/` | Plantillas de los módulos de análisis y gestión. |
| `P5_pipeline_etl/` y `P6_airflow/` | Procesamiento de datos y flujos de Airflow. |
| `informes.py` | Consultas y generación de informes. |
| `migraciones/` | Migraciones de bases de datos preparadas para revisión y ensayo. |
| `scripts/` | Herramientas de verificación, ejecución y mantenimiento. |
| `tests/` | Pruebas automatizadas. |

## Ejecución en entorno de ensayo

La demostración local utiliza bases de ensayo preparadas previamente. Con el entorno virtual y los servicios de ensayo disponibles, se puede iniciar desde la raíz del proyecto con:

```powershell
.venv\Scripts\python scripts\iniciar_app_ensayo.py --db diabetcare_fase3_ensayo --ch-ensayo
```

Después, abre [http://127.0.0.1:5000](http://127.0.0.1:5000). La disponibilidad de los informes analíticos depende de que el ClickHouse de ensayo esté en funcionamiento.

Para configurar un entorno nuevo, consulta los requisitos en `requirements.txt` y las variables documentadas en `.env.example`. Las credenciales se configuran localmente mediante variables de entorno.

## Datos e informes

La aplicación puede trabajar con datos de referencia y datos generados para pruebas. Los resultados de un entorno de ensayo sirven para demostrar las funcionalidades y no deben interpretarse como prevalencia clínica de una población real.

Los informes permiten revisar, entre otros aspectos, la agenda, el desempeño de las clínicas, los perfiles metabólicos y los indicadores de riesgo. Su disponibilidad y alcance dependen de los permisos del usuario y de los datos y servicios disponibles.

## Estado del proyecto

DiabetCare continúa en desarrollo. Las mejoras de interfaz, permisos y estructura se están verificando en entornos de ensayo. Las migraciones preparadas y su aplicación a bases reales requieren revisión y autorización específica.
