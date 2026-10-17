# Sistema de Citas Oftalmológicas

## Instalación y entorno virtual

Desde la carpeta del proyecto:

```bash
# 1. Crear el entorno virtual
python3 -m venv venv

# 2. Activarlo
source venv/bin/activate          # Linux / macOS
venv\Scripts\activate             # Windows

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Ejecutar la aplicación
uvicorn main:app --reload
```

La aplicación queda disponible en http://127.0.0.1:8000

Para salir del entorno virtual: `deactivate`.

## Pruebas

```bash
python pruebas_momento2.py
python pruebas_momento3.py
python pruebas_rf_01_29.py
python pruebas_rf_30_50.py
```
