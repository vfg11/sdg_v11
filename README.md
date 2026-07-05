# Signal Diagram Editor — v7

Editor gráfico de diagramas de señales KKS sobre hoja A3 apaisada.  
Multihoja · Cajetín rótulo · Conexiones ortogonales editables · Enlace inter-hoja · Símbolos de campo · Notas de texto.

---

## Instalación

```bash
pip install PyQt6 openpyxl
```

## Arranque

```bash
cd diagram_tool
python main.py
```

---

## Referencia de uso

### Página y área de trabajo

| Zona | Descripción |
|------|-------------|
| Cabecera azul | Título del documento + número de hoja |
| Columna izquierda (ENTRADAS) | 12–24 cajones de señal de entrada |
| Área central | Bloques lógicos y conexiones |
| Columna derecha (SALIDAS) | Cajones de señal de salida |
| Cajetín inferior | Rótulo de rótulo normalizado |
| Pestañas inferiores | Navegación entre hojas |

### Cajones (columnas laterales)

| Acción | Resultado |
|--------|-----------|
| Doble clic en cajón | Editar KKS (18 chars) y referencia |
| Clic derecho → **Limpiar cajón** | Vacía el cajón y rompe enlace si lo tenía |
| Clic derecho → **Enlazar con cajón de entrada de otra hoja** | Inicia enlace inter-hoja |

Cada cajón muestra:
- Número de cajón (`01`–`24`) en la esquina
- KKS en fuente monoespaciada (máx. 18 chars)
- Referencia cruzada con flecha `→ H.02:05` (salida) o `← H.01:03` (entrada)
- Fondo **verde claro** si tiene enlace inter-hoja activo

### Enlace inter-hoja

1. Clic derecho en cajón de **SALIDAS** → *"Enlazar con cajón de entrada de otra hoja…"*
2. La barra de estado muestra un aviso naranja
3. Navega a la hoja destino con las pestañas inferiores
4. Clic izquierdo en el cajón de **ENTRADAS** deseado
5. Se sincronizan automáticamente:
   - KKS (el del cajón origen prevalece)
   - Referencias cruzadas `H.hoja:cajón` en ambos lados
6. Si se limpia cualquiera de los dos cajones, el enlace se rompe en ambos sentidos

### Bloques

| Acción | Resultado |
|--------|-----------|
| Arrastrar desde biblioteca | Deposita bloque; abre diálogo de configuración |
| Doble clic | Editar tipo, KKS, etiqueta y puertos |
| `Ctrl+C` / `Ctrl+V` | Copiar / pegar (offset +10 mm) |
| Clic derecho → **Copiar a hoja…** | Copia el bloque a otra hoja |
| `Supr` / `Backspace` | Eliminar selección (bloques, conexiones, símbolos, notas) |

### Conexiones

| Acción | Resultado |
|--------|-----------|
| Clic en puerto de salida → clic en destino | Crea conexión ortogonal |
| Seleccionar conexión | Muestra **cuadrados naranjas** en los nodos |
| Doble clic en handle naranja | Elimina ese nodo |
| **Ctrl+Click** sobre la línea | Inserta nuevo nodo en ese punto |
| **Click+Drag** sobre segmento H o V | Desplaza el segmento en paralelo |
| El cursor cambia a ↕ / ↔ | Indica si el segmento es horizontal o vertical |
| Clic derecho → **Resetear ruta** | Elimina todos los nodos; vuelve al codo simple |

Cada conexión parte con un **stub horizontal de 5 mm** en origen y destino.

### Símbolos de campo

Tres tipos disponibles en la sección **"Símbolos de campo"** del panel de biblioteca.  
Cada tipo existe en versión **salida** (puerto en borde derecho) y **entrada** (borde izquierdo).

| Símbolo | Icono | Uso típico |
|---------|-------|------------|
| Círculo | ○ | Sensor / actuador genérico |
| Instrumento | ⊙ | Instrumento de medida (burbuja ISA) |
| Actuador | ⬡ | Válvula / actuador final |

Tamaño: `9 mm × 9 mm` (≈ 82% del alto de cajón con 23 ranuras).

| Acción | Resultado |
|--------|-----------|
| Arrastrar desde biblioteca | Deposita símbolo en el canvas |
| Doble clic | Editar KKS / etiqueta |
| Conectar desde/a su puerto | Igual que un bloque |
| `Supr` | Eliminar |

### Notas de texto

| Acción | Resultado |
|--------|-----------|
| Arrastrar "✎ Añadir nota" o clic en el botón | Inserta nota en el canvas |
| **Doble clic** en la nota | Edición de texto in-situ |
| Clic+Drag | Mover la nota |
| `Supr` | Eliminar |
| Clic derecho → **Eliminar nota** | Eliminar |

Fuente pequeña, fondo amarillo semitransparente, borde punteado.

### Propiedades de hoja

**Menú Hojas → Propiedades** (o doble clic en la pestaña):
- **Nombre de pestaña**: texto libre
- **Número de hoja**: valor libre (`01`, `A`, `1-A`…). Si se deja vacío se usa el índice automático.
- **Título de hoja**: aparece en la fila inferior de la columna "Título" del cajetín (distinto del título del documento).

### Cajetín

Estructura (6 columnas):

| Col | Contenido | Filas |
|-----|-----------|-------|
| 0 | Empresa / Logo | 2 |
| 1 | Título documento / **Título de hoja** | 2 |
| 2 | Nº Documento / Rev + Fecha | 2 |
| 3 | Proyecto / Planta | 2 |
| 4 | Elaborado / Revisado / Aprobado | **3** (división propia) |
| 5 | Nº hoja (numeración libre) | 1 |

La línea divisoria horizontal solo atraviesa las columnas 0–3. La columna 4 tiene subdivisión propia en tres franjas.

### Exportación

| Opción | Formato |
|--------|---------|
| PDF — hoja activa | A3 apaisado con margen 5 mm |
| PDF — completo | Portada + todas las hojas |
| SVG | Hoja activa vectorial |
| Excel / CSV | Tabla de señales de todas las hojas |
| Imprimir | Diálogo de impresora del sistema |

La portada PDF incluye: banda de color con título, empresa, metadatos y firmas.

---

## Estructura del proyecto

```
diagram_tool/
├── main.py                    # Ventana principal, pestañas, menús
├── const.py                   # Todas las constantes (página, fuentes, colores)
├── model.py                   # Modelo de datos puro (dataclasses)
├── scene.py                   # QGraphicsScene por hoja
├── editor.py                  # QGraphicsView + FSM (IDLE / DRAWING_CONN / XSHEET_LINK)
├── items/
│   ├── slot_item.py           # Cajón lateral (KKS, referencia, puerto, número)
│   ├── block_item.py          # Bloque lógico central
│   ├── port_item.py           # Puerto E/S del bloque
│   ├── conn_item.py           # Conexión ortogonal (stubs, nodos, arrastre de segmento)
│   ├── symbol_item.py         # Símbolos de campo (círculo, instrumento, actuador)
│   ├── note_item.py           # Nota de texto editable in-situ
│   └── titleblock_item.py     # Cajetín inferior
├── widgets/
│   ├── library_panel.py       # Panel de biblioteca con drag & drop
│   └── dialogs.py             # Diálogos de edición
└── io_utils/
    ├── json_io.py             # Guardar/cargar .sdg (JSON v5)
    ├── pdf_export.py          # PDF con portada y márgenes
    └── excel_export.py        # Excel / CSV de señales
```

## Formato de archivo (.sdg)

JSON v5 — incluye bloques, conexiones (con waypoints), cajones (con enlaces cruzados), símbolos de campo y notas.

```json
{
  "version": 5,
  "title_block": { "title": "...", "doc_number": "...", ... },
  "cover": { "show": true, "subtitle": "...", "description": "..." },
  "sheets": [
    {
      "sheet_name": "Hoja 1",
      "sheet_number": "01",
      "sheet_title": "Alimentación principal",
      "num_slots": 12,
      "slots_left":  [{ "kks": "...", "sub_text": "← H.02:03", "linked_sheet": 1, "linked_slot": 2 }],
      "slots_right": [...],
      "blocks":      [{ "type_id": "PID", "kks": "...", "x": 0, "y": 0, "inputs": [...], "outputs": [...] }],
      "connections": [{ "src": { "kind": "slot_left", ... }, "dst": { ... }, "waypoints": [[x,y]] }],
      "symbols":     [{ "sym_type": "CIRCLE", "port_side": "out", "kks": "...", "x": 0, "y": 0 }],
      "notes":       [{ "text": "Revisar calibración", "x": 500, "y": 300 }]
    }
  ]
}
```
