"""
model.py — Modelo de datos puro (v10).

Jerarquía: DocumentData → GroupData → SheetData
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List
import uuid


@dataclass
class TitleBlockData:
    company:     str = ''
    title:       str = ''
    doc_number:  str = ''
    project:     str = ''
    plant:       str = ''
    revision:    str = 'A'
    date:        str = ''
    drawn_by:    str = ''
    checked_by:  str = ''
    approved_by: str = ''
    logo_path:   str = ''


@dataclass
class CoverPageData:
    """Datos para la portada del PDF."""
    show:        bool = True
    subtitle:    str  = ''
    description: str  = ''
    logo_path:   str  = ''


@dataclass
class SlotData:
    """
    Conector de columna lateral.
    Layout: NUM(8%) | DESC(44%) | SIG(14%) | KKS/KKS2(26%) | REF(lower 18%)
    Un conector SALIDA puede enlazarse a múltiples ENTRADAS.
    """
    slot_id:       str       = field(default_factory=lambda: str(uuid.uuid4()))
    description:   str       = ''   # descripción equipo  (2 líneas × 35 chars)
    signal_desc:   str       = ''   # descripción señal   (2 líneas × 15 chars)
    kks:           str       = ''   # código KKS          (línea superior, 15 chars)
    kks2:          str       = ''   # segundo campo KKS   (línea inferior, 15 chars)
    sub_text:      str       = ''   # referencia(s) auto — calculada, no editar
    linked_sheets: list      = field(default_factory=list)
    linked_slots:  list      = field(default_factory=list)
    # Retrocompatibilidad
    linked_sheet:  int       = -1
    linked_slot:   int       = -1

    def __post_init__(self):
        if self.linked_sheet >= 0 and self.linked_sheet not in self.linked_sheets:
            self.linked_sheets.append(self.linked_sheet)
            if self.linked_slot >= 0:
                self.linked_slots.append(self.linked_slot)
        self.linked_sheet = -1
        self.linked_slot  = -1

    def label_main(self) -> str:
        parts = [p for p in [self.description, self.signal_desc, self.kks] if p]
        return ' | '.join(parts) if parts else '—'

    def is_empty(self) -> bool:
        return not any([self.description, self.signal_desc, self.kks, self.kks2])

    def is_linked(self) -> bool:
        return bool(self.linked_sheets)

    def add_link(self, sheet_idx: int, slot_idx: int):
        if (sheet_idx, slot_idx) not in zip(self.linked_sheets, self.linked_slots):
            self.linked_sheets.append(sheet_idx)
            self.linked_slots.append(slot_idx)

    def remove_link(self, sheet_idx: int, slot_idx: int):
        pairs = list(zip(self.linked_sheets, self.linked_slots))
        try:
            i = pairs.index((sheet_idx, slot_idx))
            self.linked_sheets.pop(i)
            self.linked_slots.pop(i)
        except ValueError:
            pass
        if not self.linked_sheets:
            self.sub_text = ''

    def rebuild_sub_text(self, doc, my_side: str, my_sheet_idx: int, my_slot_idx: int):
        """Recalcula sub_text con TODAS las referencias enlazadas."""
        if not self.linked_sheets:
            self.sub_text = ''
            return
        refs = []
        flat = doc.flat_sheets()
        for si, sl in zip(self.linked_sheets, self.linked_slots):
            if 0 <= si < len(flat):
                sheet, group = flat[si]
                num = group.sheet_number_for(si, doc)
                refs.append(f'H.{num}:{sl+1:02d}')
        self.sub_text = ', '.join(refs)


@dataclass
class PortData:
    port_id:     str  = field(default_factory=lambda: str(uuid.uuid4()))
    name:        str  = ''
    number:      int  = 0
    side:        str  = 'in'
    signal_type: str  = 'analog'
    negated:     bool = False

    def label(self) -> str:
        return self.name


@dataclass
class BlockData:
    block_id:        str  = field(default_factory=lambda: str(uuid.uuid4()))
    type_id:         str  = 'CUSTOM'
    kks:             str  = ''
    label:           str  = ''
    inscription:     str  = ''
    show_type_label: bool = False
    x:               float = 0.0
    y:               float = 0.0
    w:               float = 0.0
    h:               float = 0.0
    inputs:          List[PortData] = field(default_factory=list)
    outputs:         List[PortData] = field(default_factory=list)

    def clone(self, dx=0.0, dy=0.0) -> 'BlockData':
        import copy
        c = copy.deepcopy(self)
        c.block_id = str(uuid.uuid4())
        for p in c.inputs:  p.port_id = str(uuid.uuid4())
        for p in c.outputs: p.port_id = str(uuid.uuid4())
        c.x += dx; c.y += dy
        return c


@dataclass
class EndpointRef:
    kind:     str
    item_id:  str
    port_idx: int = 0


@dataclass
class ConnectionData:
    conn_id:   str = field(default_factory=lambda: str(uuid.uuid4()))
    src:       Optional[EndpointRef] = None
    dst:       Optional[EndpointRef] = None
    waypoints: List[tuple] = field(default_factory=list)


@dataclass
class BranchNodeData:
    """Datos persistentes de un nodo de bifurcación."""
    branch_id:      str   = field(default_factory=lambda: str(uuid.uuid4()))
    parent_conn_id: str   = ''     # conn_id de la conexión padre
    x:              float = 0.0
    y:              float = 0.0


@dataclass
class SymbolData:
    sym_id:    str = field(default_factory=lambda: str(uuid.uuid4()))
    sym_type:  str = 'CIRCLE'
    port_side: str = 'out'
    kks:       str = ''
    x:         float = 0.0
    y:         float = 0.0


@dataclass
class NoteData:
    note_id:     str   = field(default_factory=lambda: str(uuid.uuid4()))
    text:        str   = ''
    x:           float = 0.0
    y:           float = 0.0
    font_size_px:int   = 0
    text_width:  float = 0.0   # 0 = usar default


@dataclass
class TextBoxData:
    textbox_id:  str   = field(default_factory=lambda: str(uuid.uuid4()))
    text:        str   = 'Texto'
    x:           float = 0.0
    y:           float = 0.0
    font_size_px:int   = 0
    signal_type: str   = 'analog'


@dataclass
class SheetData:
    sheet_id:    str  = field(default_factory=lambda: str(uuid.uuid4()))
    sheet_name:  str  = ''       # nombre interno (puede estar vacío)
    num_slots:   int  = 23
    sheet_title: str  = ''       # sobrescritura manual del título (normalmente vacío → usa group.description)
    sheet_number:str  = ''       # sobrescritura manual del número (normalmente vacío → calculado del grupo)
    slots_left:  List[SlotData]       = field(default_factory=list)
    slots_right: List[SlotData]       = field(default_factory=list)
    blocks:      List[BlockData]      = field(default_factory=list)
    connections:  List[ConnectionData] = field(default_factory=list)
    symbols:      List[SymbolData]     = field(default_factory=list)
    notes:        List[NoteData]       = field(default_factory=list)
    textboxes:    List[TextBoxData]    = field(default_factory=list)
    branch_nodes: List[BranchNodeData] = field(default_factory=list)

    def init_slots(self):
        self.slots_left  = [SlotData() for _ in range(self.num_slots)]
        self.slots_right = [SlotData() for _ in range(self.num_slots)]

    def block_by_id(self, bid: str) -> Optional[BlockData]:
        return next((b for b in self.blocks if b.block_id == bid), None)


@dataclass
class GroupData:
    """Unidad lógica que agrupa hojas relacionadas."""
    group_id:          str  = field(default_factory=lambda: str(uuid.uuid4()))
    system:            str  = ''     # sistema al que pertenece (texto libre, obligatorio)
    description:       str  = ''     # → título de hoja en cajetín
    kks:               str  = ''     # → kks de bloques y primer campo de conectores salida
    revision:          str  = 'A'
    date:              str  = ''
    sheet_number_base: int  = 1      # número global de la primera hoja del grupo
    sheets:            List[SheetData] = field(default_factory=list)

    def add_sheet(self, num_slots: int = 23) -> SheetData:
        s = SheetData(num_slots=num_slots)
        s.init_slots()
        self.sheets.append(s)
        return s

    def insert_sheet_at(self, local_idx: int, num_slots: int = 23) -> SheetData:
        """Inserta una hoja nueva en local_idx, desplazando las siguientes."""
        s = SheetData(num_slots=num_slots)
        s.init_slots()
        self.sheets.insert(local_idx, s)
        return s

    def sheet_number_for(self, flat_idx: int, doc: 'DocumentData') -> str:
        """Número de hoja a mostrar en el cajetín para la hoja en flat_idx."""
        # Calcular índice local dentro del grupo
        local_idx = 0
        for gi, g in enumerate(doc.groups):
            for li, s in enumerate(g.sheets):
                fi = doc._flat_index(gi, li)
                if fi == flat_idx:
                    local_idx = li
                    break
        return str(self.sheet_number_base + local_idx)

    def title_for_sheet(self, local_idx: int) -> str:
        """Título de hoja calculado: 'Descripción' o 'Descripción (N)'."""
        if len(self.sheets) <= 1:
            return self.description
        return f'{self.description} ({local_idx + 1})'

    def tab_label(self, local_idx: int) -> str:
        """Etiqueta de pestaña: 'Descripción · HNN'"""
        num = self.sheet_number_base + local_idx
        desc = self.description or f'Grupo {self.group_id[:4]}'
        return f'{desc} · H{num:02d}'


@dataclass
class DocumentData:
    title_block:  TitleBlockData = field(default_factory=TitleBlockData)
    cover:        CoverPageData  = field(default_factory=CoverPageData)
    groups:       List[GroupData] = field(default_factory=list)
    library_blob: list            = field(default_factory=list)

    # ── acceso plano (para compatibilidad con scene.py y exports) ─────────

    def flat_sheets(self) -> List[tuple]:
        """Devuelve lista de (SheetData, GroupData) en orden de pestañas."""
        result = []
        for g in self.groups:
            for s in g.sheets:
                result.append((s, g))
        return result

    def _flat_index(self, group_idx: int, local_idx: int) -> int:
        """Índice plano dado grupo e índice local."""
        n = 0
        for i, g in enumerate(self.groups):
            if i == group_idx:
                return n + local_idx
            n += len(g.sheets)
        return -1

    def sheet_at(self, flat_idx: int) -> Optional[SheetData]:
        """SheetData por índice plano."""
        flat = self.flat_sheets()
        if 0 <= flat_idx < len(flat):
            return flat[flat_idx][0]
        return None

    def group_at(self, flat_idx: int) -> Optional[GroupData]:
        """GroupData por índice plano."""
        flat = self.flat_sheets()
        if 0 <= flat_idx < len(flat):
            return flat[flat_idx][1]
        return None

    def flat_index_of(self, sheet: SheetData) -> int:
        for i, (s, g) in enumerate(self.flat_sheets()):
            if s.sheet_id == sheet.sheet_id:
                return i
        return -1

    def group_of(self, flat_idx: int):
        return self.group_at(flat_idx)

    def sheet_count(self) -> int:
        return sum(len(g.sheets) for g in self.groups)

    def next_free_sheet_number(self) -> int:
        """Siguiente número libre (mayor número usado + 1, mínimo 1)."""
        used = set()
        for g in self.groups:
            for li in range(len(g.sheets)):
                used.add(g.sheet_number_base + li)
        n = 1
        while n in used:
            n += 1
        return n

    def next_suggested_base(self) -> int:
        """Sugiere el número base para un nuevo grupo.

        Regla:
        - Si no hay grupos todavía → 10 (deja espacio para portada e índice)
        - Si ya hay grupos → primera decena libre *estrictamente por encima*
          de la última hoja numerada del documento.

        Ejemplos:
          último nº = 12  → siguiente decena = 20
          último nº = 20  → siguiente decena = 30
          último nº = 30  → siguiente decena = 40
        """
        if not self.groups:
            return 10
        # Máximo número de hoja asignado actualmente
        max_num = 0
        for g in self.groups:
            last = g.sheet_number_base + len(g.sheets) - 1
            if last > max_num:
                max_num = last
        # Primera decena estrictamente por encima de max_num
        decade = (max_num // 10 + 1) * 10
        return decade

    def can_shift(self, from_group_idx: int, delta: int) -> tuple:
        """Verifica si se puede aplicar delta (+/-) a todos los grupos
        desde from_group_idx hasta el final sin colisiones con grupos anteriores.

        Retorna (True, '') o (False, mensaje_error).
        """
        if delta == 0:
            return True, ''

        # Números ocupados por grupos NO afectados (anteriores al rango)
        fixed_nums = set()
        for gi, g in enumerate(self.groups):
            if gi < from_group_idx:
                for li in range(len(g.sheets)):
                    fixed_nums.add(g.sheet_number_base + li)

        # Números que tendrían los grupos afectados tras el desplazamiento
        shifted_nums = set()
        for gi, g in enumerate(self.groups):
            if gi >= from_group_idx:
                new_base = g.sheet_number_base + delta
                if new_base < 1:
                    return False, (f'El grupo "{g.description or g.group_id[:8]}" '
                                   f'quedaría con número de hoja {new_base}, '
                                   f'que es menor que 1.')
                for li in range(len(g.sheets)):
                    shifted_nums.add(new_base + li)

        # Comprobar colisiones
        collisions = fixed_nums & shifted_nums
        if collisions:
            nums = sorted(collisions)
            return False, (f'La operación generaría números de hoja duplicados: '
                           f'{", ".join(str(n) for n in nums[:5])}'
                           + (' …' if len(nums) > 5 else '') + '.')

        return True, ''

    def shift_from(self, from_group_idx: int, delta: int):
        """Aplica delta al sheet_number_base de todos los grupos desde
        from_group_idx hasta el final. No valida — usar can_shift() antes.
        """
        for gi, g in enumerate(self.groups):
            if gi >= from_group_idx:
                g.sheet_number_base += delta

    def remap_links_after_insert(self, insert_flat_idx: int):
        """Tras insertar una hoja en insert_flat_idx, incrementa en 1 todos
        los linked_sheets que apunten a índices >= insert_flat_idx, en todos
        los slots de todas las hojas del documento.

        Las hojas no cargadas se cargan desde BD para que el remap les llegue
        (y se persistirán después vía _rebuild_all_sub_texts).
        """
        for sheet, _ in self.flat_sheets():
            if not getattr(sheet, '_loaded', False):
                try:
                    from io_utils.db_io import load_sheet_content
                    load_sheet_content(sheet)
                except Exception:
                    pass
            for sd in sheet.slots_left + sheet.slots_right:
                sd.linked_sheets = [
                    si + 1 if si >= insert_flat_idx else si
                    for si in sd.linked_sheets
                ]

    def cascade_shift_after_insert(self, from_group_idx: int):
        """Tras insertar una hoja en el grupo from_group_idx, propaga desplazamientos
        hacia los grupos siguientes solo si sus rangos numéricos se solapan.

        Recorre los grupos en orden a partir de from_group_idx y, para cada par
        (grupo_i, grupo_siguiente), si el último número de grupo_i >= base del
        siguiente, incrementa el base del siguiente en 1 y continúa.
        Se detiene en cuanto ya no hay solapamiento.
        """
        groups = self.groups
        for gi in range(from_group_idx, len(groups) - 1):
            cur  = groups[gi]
            nxt  = groups[gi + 1]
            last_cur = cur.sheet_number_base + len(cur.sheets) - 1
            if last_cur >= nxt.sheet_number_base:
                nxt.sheet_number_base = last_cur + 1
            else:
                break   # sin solapamiento → resto no afectado
    def remap_links_by_map(self, idx_map: dict):
        """Aplica un mapa {old_flat_idx → new_flat_idx} a todos los linked_sheets
        de todos los slots de todas las hojas del documento.
        Las hojas no cargadas se cargan antes del remap.
        """
        for sheet, _ in self.flat_sheets():
            if not getattr(sheet, '_loaded', False):
                try:
                    from io_utils.db_io import load_sheet_content
                    load_sheet_content(sheet)
                except Exception:
                    pass
            for sd in sheet.slots_left + sheet.slots_right:
                sd.linked_sheets = [
                    idx_map.get(si, si) for si in sd.linked_sheets
                ]

    def flat_idx_map(self) -> dict:
        """Devuelve {sheet_id: flat_idx} para el estado actual."""
        return {s.sheet_id: i for i, (s, _) in enumerate(self.flat_sheets())}

    def move_group(self, group_id: str, new_base: int) -> tuple[bool, str]:
        """Mueve el grupo group_id para que su primera hoja sea new_base.

        Pasos:
          1. Captura mapa sheet_id → flat_idx antes del movimiento.
          2. Extrae el grupo de su posición actual.
          3. Abre hueco: desplaza todos los grupos cuyo rango se solape
             con [new_base, new_base+n-1], en orden de menor a mayor base.
          4. Asigna new_base al grupo y lo reinserta en el orden correcto
             (ordenado por sheet_number_base).
          5. Captura mapa sheet_id → flat_idx después.
          6. Construye old→new y devuelve el mapa para que el llamador
             aplique remap_links_by_map + _rebuild_all_sub_texts.

        Devuelve (True, '') o (False, mensaje_error).
        """
        g = next((g for g in self.groups if g.group_id == group_id), None)
        if g is None:
            return False, f'Grupo {group_id} no encontrado.'

        n = len(g.sheets)
        old_base = g.sheet_number_base

        if old_base == new_base:
            return False, 'El grupo ya está en esa posición.'

        own_range = range(old_base, old_base + n)
        if new_base in own_range:
            return False, 'El destino solapa con el rango actual del propio grupo.'

        # 1. Mapa previo al movimiento
        pre_map = self.flat_idx_map()

        # 2. Extraer el grupo de la lista
        self.groups.remove(g)

        # 3. Abrir hueco en destino: los grupos restantes que solapan con
        #    [new_base, new_base+n-1] se desplazan hacia adelante.
        #    Se procesan en orden descendente de base para no crear solapamientos
        #    entre los propios grupos desplazados.
        dest_last = new_base + n - 1
        changed = True
        while changed:
            changed = False
            # Ordenar por base ascendente para propagar la cascada hacia adelante
            for other in sorted(self.groups, key=lambda x: x.sheet_number_base):
                o_first = other.sheet_number_base
                o_last  = other.sheet_number_base + len(other.sheets) - 1
                # Solapamiento con el hueco que queremos ocupar
                if o_first <= dest_last and o_last >= new_base:
                    # Desplazar este grupo justo al final del hueco + 1
                    other.sheet_number_base = dest_last + 1
                    # El nuevo dest_last puede haber cambiado solo si el grupo
                    # desplazado ahora solapa con otro → siguiente iteración lo resuelve
                    changed = True
                    break
            # Recalcular dest_last por si cascade movió algo que ahora toca el siguiente
            # (no es necesario: dest_last es fijo para el hueco del grupo que movemos)

        # 4. Asignar new_base e insertar en posición ordenada
        g.sheet_number_base = new_base
        insert_pos = 0
        for i, other in enumerate(self.groups):
            if other.sheet_number_base > new_base:
                insert_pos = i
                break
            insert_pos = i + 1
        self.groups.insert(insert_pos, g)

        # 5. Mapa posterior al movimiento
        post_map = self.flat_idx_map()

        # 6. Construir old_flat → new_flat usando sheet_id como pivote
        idx_map = {}
        for sheet_id, old_fi in pre_map.items():
            new_fi = post_map.get(sheet_id)
            if new_fi is not None and new_fi != old_fi:
                idx_map[old_fi] = new_fi
        # Los índices no presentes en idx_map se mantienen (get devuelve si mismo)

        return True, idx_map



    def sheet_ref(self, flat_idx: int) -> str:
        """Número de hoja para sub_text."""
        g = self.group_at(flat_idx)
        if g is None:
            return str(flat_idx + 1)
        flat = self.flat_sheets()
        local_idx = sum(1 for i, (s2, g2) in enumerate(flat)
                        if i < flat_idx and g2.group_id == g.group_id)
        return str(g.sheet_number_base + local_idx)

    def all_systems(self) -> list:
        """Lista de sistemas existentes en el documento (sin duplicados, en orden)."""
        seen = {}
        for g in self.groups:
            s = g.system or ''
            if s not in seen:
                seen[s] = True
        return list(seen.keys())

    def _next_system_name(self) -> str:
        """Auto-nombre de sistema: 'Sistema N' donde N es el siguiente libre."""
        existing = self.all_systems()
        n = 1
        while f'Sistema {n}' in existing:
            n += 1
        return f'Sistema {n}'

    def add_group(self, description='', kks='', revision='A', date='',
                  sheet_number_base: int = None, num_slots: int = 23,
                  system: str = '') -> GroupData:
        if sheet_number_base is None:
            sheet_number_base = self.next_free_sheet_number()
        if not system:
            system = self._next_system_name()
        g = GroupData(system=system, description=description, kks=kks,
                      revision=revision, date=date,
                      sheet_number_base=sheet_number_base)
        g.add_sheet(num_slots)
        self.groups.append(g)
        return g


# ── Biblioteca de bloques ─────────────────────────────────────────────────

@dataclass
class BlockType:
    type_id:      str
    name:         str
    category:     str
    has_kks:      bool
    default_ins:  int
    default_outs: int
    color:        str
    description:  str   = ''
    port_type:    str   = 'analog'
    in_names:     tuple = ()
    out_names:    tuple = ()
    width_mm:     float = 20.0
    inscription:  str   = ''
    extensible_in:  bool  = True
    extensible_out: bool  = True
    in_types:     tuple = ()
    out_types:    tuple = ()


BLOCK_LIBRARY: List[BlockType] = [
    # Lógica
    BlockType('AND',              'AND',              'Lógica',      True, 2, 1, '#E8F8E8', 'Puerta AND',                       'digital', ('1','2'),                                              ('1',),                           12.0, '&',        True,  False, ('digital','digital'),                                                               ('digital',)),
    BlockType('OR',               'OR',               'Lógica',      True, 2, 1, '#E8F8E8', 'Puerta OR',                        'digital', ('1','2'),                                              ('1',),                           18.0, '/0031',    True,  False, ('digital','digital'),                                                               ('digital',)),
    BlockType('NOT',              'NOT',              'Lógica',      True, 1, 1, '#E8F8E8', 'Inversor',                         'digital', ('o',),                                                 ('ô',),                           12.0, 'Ͷ',        False, False, ('digital',),                                                                        ('digital',)),
    BlockType('FLANCO_UP',        'FLANCO ↑',         'Lógica',      True, 1, 1, '#E8F8E8', 'Flanco ascendente',                'digital', ('1',),                                                 ('1',),                           15.0, '/001',     False, False, ('digital',),                                                                        ('digital',)),
    BlockType('FLANCO_DOWN',      'FLANCO ↓',         'Lógica',      True, 1, 1, '#E8F8E8', 'Flanco descendente',               'digital', ('1',),                                                 ('1',),                           15.0, '/002',     False, False, ('digital',),                                                                        ('digital',)),
    BlockType('XOR',              'XOR',              'Lógica',      True, 2, 1, '#E8F8E8', 'Puerta XOR',                       'digital', ('1','2'),                                              ('1',),                           15.0, '=1',       True,  False, ('digital','digital'),                                                               ('digital',)),
    BlockType('SR',               'SR',               'Lógica',      True, 2, 2, '#E8F8E8', 'Biestable SR',                     'digital', ('S','R'),                                              ('o','ô'),                        15.0, 'SR',       False, False, ('digital','digital'),                                                               ('digital','digital')),
    BlockType('TON',              'TON',              'Lógica',      True, 1, 1, '#E8F8E8', 'Retardo a conexión',               'digital', ('1',),                                                 ('1',),                           18.0, '/005',     False, False, ('digital',),                                                                        ('digital',)),
    BlockType('TOFF',             'TOFF',             'Lógica',      True, 1, 1, '#E8F8E8', 'Retardo a desconexión',            'digital', ('1',),                                                 ('1',),                           18.0, '/006',     False, False, ('digital',),                                                                        ('digital',)),
    BlockType('PULSO',            'PULSO',            'Lógica',      True, 1, 1, '#E8F8E8', 'Pulso',                            'digital', ('1',),                                                 ('1',),                           18.0, '/004',     False, False, ('digital',),                                                                        ('digital',)),
    # Control
    BlockType('PID',              'PID',              'Control',     True, 5, 1, '#E8F0FE', 'Controlador PID',                  'analog',  ('PV','SP','FF','TRACK','T_VALUE'),                     ('OUT',),                         28.0, 'PID',      True,  True,  ('analog','analog','analog','digital','analog'),                                      ('analog',)),
    BlockType('INTEG',            'INTEG',            'Control',     True, 2, 1, '#E8F0FE', 'Integrador',                       'analog',  ('IN','RESET'),                                         ('OUT',),                         25.0, '/009',     True,  True,  ('analog','digital'),                                                                ('analog',)),
    BlockType('DERIV',            'DERIV',            'Control',     True, 1, 1, '#E8F0FE', 'Derivada',                         'analog',  ('IN',),                                                ('OUT',),                         30.0, 'd/dt',     True,  True,  ('analog',),                                                                         ('analog',)),
    BlockType('LAG',              'LAG',              'Control',     True, 1, 1, '#E8F0FE', 'Sistema 1er orden',                'analog',  ('IN',),                                                ('OUT',),                         30.0, 'LAG',      True,  True,  ('analog',),                                                                         ('analog',)),
    BlockType('LIM_INFERIOR',     'LIM INFERIOR',     'Control',     True, 2, 1, '#E8F0FE', 'Limitador inferior',               'analog',  ('IN','L_INF'),                                         ('OUT',),                         32.0, '/014',     False, False, ('analog','analog'),                                                                 ('analog',)),
    BlockType('LIM_SUPERIOR',     'LIM SUPERIOR',     'Control',     True, 2, 1, '#E8F0FE', 'Limitador superior',               'analog',  ('IN','L_SUP'),                                         ('OUT',),                         32.0, '/013',     False, False, ('analog','analog'),                                                                 ('analog',)),
    # Equipos
    BlockType('MOTOR',            'MOTOR',            'Equipos',     True, 7, 5, '#FEF0E8', 'Bloque motor',                     'digital', ('RUN_FB','A_RUN','A_STOP','FAULT','P_START','TRIP','LOCK'), ('START','RUNNING','ALARM','READY','HOURS'), 60.0, 'M',   True,  True,  ('digital','digital','digital','digital','digital','digital','digital'),              ('digital','digital','digital','digital','analog')),
    BlockType('VALVE',            'VALVE',            'Equipos',     True, 8, 6, '#FEF0E8', 'Válvula solenoide',                'digital', ('OPEN_FB','CLOSE_FB','A_OPEN','A_CLOSE','P_OPEN','P_CLOSE','F_OPEN','F_CLOSE'), ('ALARM','READY','OPEN','CLOSE','OPENNED','CLOSED'), 60.0, 'SOL', True, True, ('digital','digital','digital','digital','digital','digital','digital','digital'), ('digital','digital','digital','digital','digital','digital')),
    BlockType('ACTUADOR',         'ACTUADOR',         'Equipos',     True, 9, 6, '#FEF0E8', 'Actuador',                         'digital', ('OPEN_FB','CLOSE_FB','A_OPEN','A_CLOSE','FAULT','P_OPEN','P_CLOSE','F_OPEN','F_CLOSE'), ('ALARM','READY','OPEN','CLOSE','OPENNED','CLOSED'), 60.0, 'ACT', True, True, ('digital','digital','digital','digital','digital','digital','digital','digital','digital'), ('digital','digital','digital','digital','digital','digital')),
    # Matemáticas
    BlockType('SUM',              'SUM',              'Matemáticas', True, 2, 1, '#F8EEF8', 'Suma',                             'analog',  ('1','2'),                                              ('1',),                           15.0, '/007',     True,  False, ('analog','analog'),                                                                 ('analog',)),
    BlockType('DIFF',             'DIFF',             'Matemáticas', True, 2, 1, '#F8EEF8', 'Diferencia',                       'analog',  ('1','2'),                                              ('1',),                           18.0, '/008',     False, False, ('analog','analog'),                                                                 ('analog',)),
    BlockType('MUL',              'MUL',              'Matemáticas', True, 2, 1, '#F8EEF8', 'Multiplicación',                   'analog',  ('1','2'),                                              ('1',),                           15.0, '*',        True,  False, ('analog','analog'),                                                                 ('analog',)),
    BlockType('DIV',              'DIV',              'Matemáticas', True, 2, 1, '#F8EEF8', 'División',                         'analog',  ('1','2'),                                              ('1',),                           15.0, '/016',     False, False, ('analog','analog'),                                                                 ('analog',)),
    BlockType('ROOT',             'ROOT',             'Matemáticas', True, 1, 1, '#F8EEF8', 'Raíz',                             'analog',  ('1',),                                                 ('1',),                           15.0, '/010',     False, False, ('analog',),                                                                         ('analog',)),
    BlockType('GAIN',             'GAIN',             'Matemáticas', True, 1, 1, '#F8EEF8', 'Ganancia',                         'analog',  ('1',),                                                 ('1',),                           12.0, 'K',        False, False, ('analog',),                                                                         ('analog',)),
    BlockType('REVERSE_GAIN',     'REVERSE GAIN',     'Matemáticas', True, 1, 1, '#F8EEF8', 'Ganancia inversa',                 'analog',  ('1',),                                                 ('1',),                           15.0, '-K',       False, False, ('analog',),                                                                         ('analog',)),
    BlockType('COMP',             'COMP',             'Matemáticas', True, 2, 3, '#F8EEF8', 'Comparador',                       'analog',  ('1','R'),                                              ('>','=','<'),                    15.0, '/015',     False, False, ('analog','analog'),                                                                 ('digital','digital','digital')),
    BlockType('MAX',              'MAX',              'Matemáticas', True, 2, 1, '#F8EEF8', 'Máximo',                           'analog',  ('1','2'),                                              ('1',),                           15.0, '/011',     True,  False, ('analog','analog'),                                                                 ('analog',)),
    BlockType('MIN',              'MIN',              'Matemáticas', True, 2, 1, '#F8EEF8', 'Mínimo',                           'analog',  ('1','2'),                                              ('1',),                           15.0, '/012',     True,  False, ('analog','analog'),                                                                 ('analog',)),
    BlockType('FUNCTION',         'FUNCTION',         'Matemáticas', True, 2, 1, '#F8EEF8', 'f(x)',                             'analog',  ('x','y'),                                              ('1',),                           12.0, 'f',        True,  False, ('analog','analog'),                                                                 ('analog',)),
    # Señal
    BlockType('SEL_D',            'SEL_D',            'Señal',       True, 3, 1, '#FFFBE8', 'Selector digital',                 'digital', ('1','2','S_2'),                                        ('1',),                           30.0, 'S_DIG',    False, False, ('digital','digital','digital'),                                                     ('digital',)),
    BlockType('D_2OO3',           '2oo3d',            'Señal',       True, 3, 1, '#E8F8E8', 'Dos de tres digital',              'digital', ('1','2','3'),                                          ('1',),                           18.0, '≥2',       False, False, ('digital','digital','digital'),                                                     ('digital',)),
    BlockType('SEL_N',            'SEL_N',            'Señal',       True, 3, 1, '#FFFBE8', 'Selector numérico',                'analog',  ('1','2','S_2'),                                        ('1',),                           30.0, 'S_NUM',    False, False, ('analog','analog','digital'),                                                       ('analog',)),
    BlockType('SCALING',          'SCALING',          'Señal',       True, 1, 1, '#FFFBE8', 'Convertidor señal',                'analog',  ('1',),                                                 ('1',),                           35.0, 'SCALING',  False, False, ('analog',),                                                                         ('analog',)),
    BlockType('QUALITY',          'QUALITY',          'Señal',       True, 1, 1, '#FFFBE8', 'Calidad señal',                    'analog',  ('1',),                                                 ('BQ',),                          20.0, 'Q',        False, False, ('analog',),                                                                         ('digital',)),
    BlockType('A_1OO2',           '1oo2',             'Señal',       True, 2, 2, '#FFFBE8', 'Uno de dos analógico',             'analog',  ('1','2'),                                              ('1','BQ'),                       30.0, '1oo2',     False, True,  ('analog','analog'),                                                                 ('analog','digital')),
    BlockType('A_2OO3',           '2oo3',             'Señal',       True, 3, 3, '#FFFBE8', 'Dos de tres analógico',            'analog',  ('1','2','3'),                                          ('1','DIS','BQ'),                 30.0, '2oo3',     False, True,  ('analog','analog','analog'),                                                        ('analog','digital','digital')),
    BlockType('MONITOR_HIGH',     'MONITOR HIGH',     'Señal',       True, 1, 1, '#FFFBE8', 'Monitor señal alta',               'analog',  ('1',),                                                 ('1',),                           16.0, 'H/',       False, False, ('analog',),                                                                         ('analog',)),
    BlockType('MONITOR_HIGH_HYST','MONITOR HIGH HYST','Señal',       True, 1, 1, '#FFFBE8', 'Monitor señal alta con histéresis','analog',  ('1',),                                                 ('1',),                           20.0, 'H////',    False, False, ('analog',),                                                                         ('analog',)),
    BlockType('MONITOR_LOW',      'MONITOR LOW',      'Señal',       True, 1, 1, '#FFFBE8', 'Monitor señal baja',               'analog',  ('1',),                                                 ('1',),                           16.0, '/L',       False, False, ('analog',),                                                                         ('analog',)),
    BlockType('MONITOR_LOW_HYST', 'MONITOR LOW HYST', 'Señal',       True, 1, 1, '#FFFBE8', 'Monitor señal baja con histéresis','analog',  ('1',),                                                 ('1',),                           20.0, '////L',    False, False, ('analog',),                                                                         ('analog',)),
    # Usuario
    BlockType('CUSTOM',           'CUSTOM',           'Usuario',     True, 2, 2, '#F5F5F5', 'Bloque personalizado',             'analog',  ('IN1','IN2'),                                          ('OUT1','OUT2'),                  20.0, '',         True,  True,  ('analog','analog'),                                                                 ('analog','analog')),
]

LIBRARY_BY_ID     = {bt.type_id: bt for bt in BLOCK_LIBRARY}
LIBRARY_CATEGORIES = sorted({bt.category for bt in BLOCK_LIBRARY})
