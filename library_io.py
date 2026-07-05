"""
library_io.py — Exportación e importación de la biblioteca de bloques.

FORMATO DEL ARCHIVO
-------------------
Líneas que empiezan por '#' son comentarios, líneas vacías se ignoran.
Cada bloque ocupa una línea con el formato:

  {Familia;NombreCorto;Descripción;Anchomm;Inscripción;Puertos_entrada;Puertos_salida;Color_hex}

Puertos:  nombre:d|n[,nombre:d|n,...]  donde d=digital, n=numérico/analógico.
          La lista puede terminar en ',...' para indicar que es extensible.
          Vacío = sin puertos en ese lado.

Ejemplo:
  {Lógica;AND;Puerta AND;20;AND;IN1:d,IN2:d;OUT:d;#E8F8E8}
  {Control;PID;Controlador PID;24;PID;PV:n,SP:n,FF:n,...;OUT:n,TRACK:n;#E8F0FE}
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import List, Tuple

from model import BlockType, PortData


# ── Helpers ────────────────────────────────────────────────────────────────

def _parse_ports(raw: str) -> Tuple[List[dict], bool]:
    """
    Parsea una cadena de puertos y devuelve (lista_de_dicts, extensible).
    Cada dict tiene 'name' y 'signal_type' ('digital'|'analog').
    """
    raw = raw.strip()
    if not raw:
        return [], False
    extensible = raw.endswith(',...')
    if extensible:
        raw = raw[:-4]  # quitar ',...'
    ports = []
    for token in raw.split(','):
        token = token.strip()
        if not token:
            continue
        if ':' in token:
            name, typ = token.rsplit(':', 1)
            sig = 'digital' if typ.strip().lower() == 'd' else 'analog'
        else:
            name, sig = token, 'analog'
        ports.append({'name': name.strip(), 'signal_type': sig})
    return ports, extensible


def _ports_to_str(ports: list, extensible: bool) -> str:
    """Serializa lista de ports + flag extensible a cadena del formato."""
    parts = []
    for p in ports:
        typ = 'd' if getattr(p, 'signal_type', 'analog') == 'digital' else 'n'
        name = getattr(p, 'name', '') or (getattr(p, 'get', lambda k, d: d)('name', '') if isinstance(p, dict) else '')
        if isinstance(p, dict):
            name = p.get('name', '')
            typ  = 'd' if p.get('signal_type', 'analog') == 'digital' else 'n'
        parts.append(f'{name}:{typ}')
    result = ','.join(parts)
    if extensible:
        result += ',...'
    return result


# ── Exportación ────────────────────────────────────────────────────────────

def export_library(block_types: list, filepath: str):
    """Exporta una lista de BlockType al archivo de texto indicado."""
    from datetime import datetime
    lines = [
        '# Biblioteca de bloques — Diagram Tool',
        f'# Exportado: {datetime.now().strftime("%Y-%m-%d %H:%M")}',
        '# Formato: {Familia;NombreCorto;Descripción;Anchomm;Inscripción;Entradas;Salidas;Color}',
        '# Tipo puerto: d=digital, n=numérico/analógico. Lista acaba en ,... si extensible.',
        '',
    ]
    current_cat = None
    for bt in block_types:
        if bt.category != current_cat:
            current_cat = bt.category
            lines.append(f'# ── {current_cat} ──')
        in_types  = getattr(bt, 'in_types',  ())
        out_types = getattr(bt, 'out_types', ())
        ins_str  = _ports_to_str(
            [{'name': n, 'signal_type': in_types[i] if i < len(in_types) else bt.port_type}
             for i, n in enumerate(bt.in_names)],
            getattr(bt, 'extensible_in', True)
        )
        outs_str = _ports_to_str(
            [{'name': n, 'signal_type': out_types[i] if i < len(out_types) else bt.port_type}
             for i, n in enumerate(bt.out_names)],
            getattr(bt, 'extensible_out', True)
        )
        width_mm = getattr(bt, 'width_mm', 20)
        insc     = getattr(bt, 'inscription', bt.name)
        lines.append(
            '{' + ';'.join([
                bt.category,
                bt.type_id,
                bt.description,
                str(width_mm),
                insc,
                ins_str,
                outs_str,
                bt.color,
            ]) + '}'
        )
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


# ── Importación ────────────────────────────────────────────────────────────

@dataclass
class ParsedBlock:
    category:      str
    type_id:       str
    description:   str
    width_mm:      float
    inscription:   str
    in_ports:      List[dict] = field(default_factory=list)
    out_ports:     List[dict] = field(default_factory=list)
    extensible_in: bool       = False
    extensible_out:bool       = False
    color:         str        = '#E8F0FE'


def parse_library_file(filepath: str) -> Tuple[List[ParsedBlock], List[str]]:
    """
    Parsea el archivo y devuelve (bloques_parseados, errores).
    Los errores son cadenas descriptivas de líneas con problemas.
    """
    blocks = []
    errors = []
    with open(filepath, 'r', encoding='utf-8') as f:
        raw = f.read()

    for lineno, line in enumerate(raw.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        m = re.match(r'^\{(.+)\}$', line)
        if not m:
            errors.append(f'Línea {lineno}: formato inválido (debe ser {{...}})')
            continue
        fields = m.group(1).split(';')
        if len(fields) != 8:
            errors.append(f'Línea {lineno}: se esperaban 8 campos, hay {len(fields)}')
            continue
        cat, tid, desc, width_s, insc, ins_s, outs_s, color = fields
        try:
            width_mm = float(width_s.strip())
        except ValueError:
            errors.append(f'Línea {lineno}: anchura no numérica "{width_s}"')
            continue
        if not tid.strip():
            errors.append(f'Línea {lineno}: NombreCorto vacío')
            continue
        in_ports,  ext_in  = _parse_ports(ins_s.strip())
        out_ports, ext_out = _parse_ports(outs_s.strip())
        blocks.append(ParsedBlock(
            category      = cat.strip(),
            type_id       = tid.strip(),
            description   = desc.strip(),
            width_mm      = width_mm,
            inscription   = insc.strip(),
            in_ports      = in_ports,
            out_ports     = out_ports,
            extensible_in = ext_in,
            extensible_out= ext_out,
            color         = color.strip() or '#E8F0FE',
        ))
    return blocks, errors


def parsed_to_block_type(pb: ParsedBlock) -> BlockType:
    """Convierte un ParsedBlock al BlockType del modelo."""
    # Detectar tipo dominante de señal
    all_ports = pb.in_ports + pb.out_ports
    n_dig = sum(1 for p in all_ports if p.get('signal_type') == 'digital')
    port_type = 'digital' if n_dig > len(all_ports) / 2 else 'analog'

    bt = BlockType(
        type_id      = pb.type_id,
        name         = pb.type_id,          # nombre corto = type_id
        category     = pb.category,
        has_kks      = True,                # siempre habilitado
        default_ins  = len(pb.in_ports),
        default_outs = len(pb.out_ports),
        color        = pb.color,
        description  = pb.description,
        port_type    = port_type,
        in_names     = tuple(p['name'] for p in pb.in_ports),
        out_names    = tuple(p['name'] for p in pb.out_ports),
    )
    # Campos extra
    bt.width_mm      = pb.width_mm
    bt.inscription   = pb.inscription
    bt.extensible_in = pb.extensible_in
    bt.extensible_out= pb.extensible_out
    # Tipos individuales de puerto por nombre
    bt.in_types  = tuple(p.get('signal_type', 'analog') for p in pb.in_ports)
    bt.out_types = tuple(p.get('signal_type', 'analog') for p in pb.out_ports)
    return bt


def import_library(filepath: str) -> Tuple[list, List[str], List[str]]:
    """
    Carga el archivo, parsea y convierte a BlockType.
    Devuelve (block_types, warnings, errors).
    warnings: líneas con problemas no fatales.
    errors:   líneas que impidieron parsear el bloque.
    """
    parsed, errors = parse_library_file(filepath)
    block_types = []
    seen_ids = set()
    warnings = list(errors)
    for pb in parsed:
        if pb.type_id in seen_ids:
            warnings.append(f'NombreCorto duplicado "{pb.type_id}" — se ignora la segunda aparición')
            continue
        seen_ids.add(pb.type_id)
        block_types.append(parsed_to_block_type(pb))
    return block_types, warnings, errors
