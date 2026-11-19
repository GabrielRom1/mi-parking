# PUNG



flask:

https://www.tutorialspoint.com/flask


python3 -m venv .venv

source .venv/bin/activate

python3 app.py



para tailwind

npm init -y
npm i tailwindcss
npm install -D @tailwindcss/cli
https://www.codewithharry.com/blogpost/using-tailwind-with-flask


seguí esto para la db
https://oneuptime.com/blog/post/2026-02-02-sqlite-flask/view


para "compilar" css: npm run build:css

## Gestión de lotes

Las cuentas con rol `admin` pueden consultar y editar lotes padre desde `/admin/lots`. La edición acepta `PUT` o `PATCH` con JSON en `/admin/lots/<id>`, el `GET` de esa ruta devuelve los datos editables. También se pueden crear lotes padre con sus pisos desde el formulario de administración. Al editar, se pueden agregar o eliminar pisos y ajustar capacidades, el servidor impide eliminar pisos o reducir capacidades cuando ello afectaría espacios con reservaciones.

Las acciones `POST /admin/lots/<id>/delete`, `POST /admin/lots/<id>/schedule-deletion`, `POST /admin/lots/<id>/deactivate` y `POST /admin/lots/<id>/activate` permiten eliminar físicamente el lote y sus registros dependientes cuando no tiene reservaciones, programar su eliminación si sus pisos tienen reservaciones, o desactivarlo/activarlo conservando sus datos. Como está se asume que el scheduler (que no está hecho) se encarga de la limpieza en  la fecha correspondiente.

OJO: `date_to_be_deleted` está definido actualmente como `Date`, por lo que se guarda una fecha (dos días después de la solicitud),
no una hora exacta a 48 horas. Probablemente haya que cambiar este campo a `DateTime` pronto para poder cumplir con con precisión el requisito de 48 horas.