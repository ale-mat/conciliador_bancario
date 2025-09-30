# 🏦 Conciliador Bancario

Aplicación modular para conciliación bancaria, separada en **UI**, **Lógica** e **Infraestructura**, pensada para ser escalable y mantenible.

## ✨ Funcionalidades
- 🔍 Detección automática de **Importe único** vs **Débito/Crédito**.  
- ✅ Conciliación **exacta** por **Fecha + Importe** (+ al menos un número coincidente en la descripción si existen).  
- 💡 **Sugerencias** por:
  - Diferencias de fecha (dentro de la tolerancia).  
  - Diferencias de importe (dentro de la tolerancia).  
  - Coincidencias parciales de texto.  
- 📅 Fechas configurables en la **vista** (`config.yaml`) sin alterar el **Excel** exportado (mantiene tipos reales de fecha).  
- 📊 Vista en **Streamlit** con filtros por estado, texto y resumen de resultados.  

---

## ⚙️ Requisitos

Crear un entorno virtual e instalar dependencias:

```bash
python -m venv .venv
# Linux / MacOS
source .venv/bin/activate
# Windows (PowerShell)
.venv\Scripts\activate

pip install -r requirements.txt

