# 🏦 Conciliador Bancario

**About**
Herramienta que permite comparar movimientos entre extractos bancarios y registros internos, aplicar reglas de negocio y generar reportes de conciliación de manera simple e interactiva.

Aplicación modular para **conciliación bancaria**, diseñada con separación de capas (UI, Lógica e Infraestructura) para ser **escalable, mantenible y extensible**.

---

## ✨ Funcionalidades principales

* 🔍 **Detección automática** de importes: Importe único o Débito/Crédito.
* ✅ **Conciliación exacta** por **Fecha + Importe + coincidencia parcial en descripción**.
* 💡 **Sugerencias inteligentes**:
  - Diferencias de fecha (± tolerancia).
  - Diferencias de importe (± tolerancia).
  - Coincidencias parciales de texto.
* 📅 **Fechas configurables** en `config.yaml`, con visualización en **DD/MM/AAAA**.
* 📊 **Interfaz en Streamlit** con filtros por estado, búsqueda en descripciones y **resumen por pilares**:
  - Conciliados
  - Sugeridos
  - No conciliados

---

## ⚙️ Requisitos

* Python **3.10+** (recomendado)
* [Streamlit](https://streamlit.io/)
* Librerías listadas en `requirements.txt`

---

## 🛠️ Instalación

1. Clonar el repositorio:

   ```bash
   git clone https://github.com/ale-mat/conciliador_bancario.git
   cd conciliador_bancario
   ```

2. Crear un entorno virtual:

   ```bash
   python -m venv .venv
   ```

3. Activar el entorno virtual:

   * **Linux / MacOS**

     ```bash
     source .venv/bin/activate
     ```
   * **Windows (PowerShell)**

     ```powershell
     .venv\Scripts\activate
     ```

4. Instalar dependencias:

   ```bash
   pip install -r requirements.txt
   ```

---

## 🚀 Ejecución

Ejecutar la aplicación en modo local:

```bash
streamlit run app_streamlit.py
```

La app estará disponible en:
👉 [http://localhost:8501](http://localhost:8501)

---

## ⚙️ Configuración

* Archivo de configuración: `config.yaml`
* Variables principales:

  * `csv_encodings`: lista de codificaciones a probar (`utf-8`, `latin1`, etc.)
  * `csv_separadores`: lista de separadores a detectar (`;`, `,`, `\t`, espacios múltiples)
* Permite ajustar **fechas de conciliación** y reglas de tolerancia sin modificar la lógica central.

---

## 📂 Estructura del proyecto

```
conciliador_bancario/
├── app_streamlit.py       # Interfaz de usuario
├── logic/                 # Lógica de conciliación
│   └── ...
├── infra/                 # Infraestructura (lectura CSV, helpers)
├── config.yaml            # Configuración principal
├── requirements.txt       # Dependencias
└── README.md
```

---

## 🤝 Contribuciones

* Haz un fork del repo.
* Crea tu rama (`feature/...`).
* Commit y push.
* Abre un Pull Request.

---

## 📜 Licencia

Este proyecto se distribuye bajo la licencia [MIT](https://opensource.org/licenses/MIT).




