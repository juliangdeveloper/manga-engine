import json
import os
import re

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "schema", "manga.schema.json")
TYPE_NAMES = {
    "object": "objeto",
    "array": "lista",
    "string": "texto",
    "number": "número",
    "integer": "entero",
    "boolean": "booleano",
}
MAX_ERRORS = 40


def load_schema():
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def is_type(value, kind):
    if kind == "object":
        return isinstance(value, dict)
    if kind == "array":
        return isinstance(value, list)
    if kind == "string":
        return isinstance(value, str)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return False


def join(path, key):
    if isinstance(key, int):
        return f"{path}[{key}]"
    return f"{path}.{key}" if path else key


class Validator:
    def __init__(self, schema):
        self.root = schema
        self.errors = []

    def ref(self, node):
        while "$ref" in node:
            target = self.root
            for part in node["$ref"].lstrip("#/").split("/"):
                target = target[part]
            merged = dict(target)
            merged.update({k: v for k, v in node.items() if k != "$ref"})
            node = merged
        return node

    def describe(self, node):
        node = self.ref(node)
        if "const" in node:
            return json.dumps(node["const"], ensure_ascii=False)
        kinds = node.get("type")
        kinds = kinds if isinstance(kinds, list) else [kinds]
        return " o ".join(TYPE_NAMES.get(k, str(k)) for k in kinds)

    def fail(self, path, msg):
        self.errors.append(f"{path or '(raíz)'}: {msg}")

    def check(self, value, node, path=""):
        node = self.ref(node)
        if "anyOf" in node:
            for option in node["anyOf"]:
                sub = Validator(self.root)
                sub.check(value, option, path)
                if not sub.errors:
                    return
            opts = " o ".join(self.describe(o) for o in node["anyOf"])
            self.fail(path, f"debe ser {opts} (recibido {json.dumps(value, ensure_ascii=False)[:60]})")
            return
        kinds = node.get("type")
        if kinds is not None:
            kinds = kinds if isinstance(kinds, list) else [kinds]
            if not any(is_type(value, k) for k in kinds):
                self.fail(path, f"debe ser {' o '.join(TYPE_NAMES[k] for k in kinds)} (recibido {json.dumps(value, ensure_ascii=False)[:60]})")
                return
        if "const" in node and value != node["const"]:
            self.fail(path, f"debe ser {json.dumps(node['const'])}")
        if "enum" in node and value not in node["enum"]:
            opts = ", ".join(json.dumps(v, ensure_ascii=False) for v in node["enum"])
            self.fail(path, f"debe ser uno de {opts} (recibido {json.dumps(value, ensure_ascii=False)})")
        if is_type(value, "number"):
            if "minimum" in node and value < node["minimum"]:
                self.fail(path, f"debe ser ≥ {node['minimum']} (recibido {value})")
            if "maximum" in node and value > node["maximum"]:
                self.fail(path, f"debe ser ≤ {node['maximum']} (recibido {value})")
            if "exclusiveMinimum" in node and value <= node["exclusiveMinimum"]:
                self.fail(path, f"debe ser > {node['exclusiveMinimum']} (recibido {value})")
        if isinstance(value, str):
            if "minLength" in node and len(value) < node["minLength"]:
                self.fail(path, "no puede estar vacío")
            if "pattern" in node and not re.search(node["pattern"], value):
                self.fail(path, f"formato no válido (recibido {json.dumps(value, ensure_ascii=False)})")
        if isinstance(value, list):
            if "minItems" in node and len(value) < node["minItems"]:
                self.fail(path, f"necesita al menos {node['minItems']} elementos")
            if "maxItems" in node and len(value) > node["maxItems"]:
                self.fail(path, f"admite como máximo {node['maxItems']} elementos")
            if "items" in node:
                for i, item in enumerate(value):
                    self.check(item, node["items"], join(path, i))
        if isinstance(value, dict):
            props = node.get("properties", {})
            patterns = node.get("patternProperties", {})
            for key in node.get("required", []):
                if key not in value:
                    self.fail(join(path, key), "es obligatorio")
            for key, item in value.items():
                if key in props:
                    self.check(item, props[key], join(path, key))
                    continue
                matched = [p for p in patterns if re.search(p, key)]
                for p in matched:
                    self.check(item, patterns[p], join(path, key))
                if not matched and node.get("additionalProperties") is False:
                    allowed = ", ".join(sorted(props)) or "ninguna"
                    self.fail(join(path, key), f"propiedad desconocida (válidas: {allowed})")


def layout_errors(cfg, base_dir):
    errors = []
    columns = cfg.get("columns", 12)
    rows = len(cfg.get("rows", []))
    for i, p in enumerate(cfg.get("panels", [])):
        path = f"panels[{i}]"
        col, row = p.get("col"), p.get("row")
        if isinstance(col, list) and len(col) == 2 and col[0] + col[1] - 1 > columns:
            errors.append(f"{path}.col: la viñeta termina en la columna {col[0] + col[1] - 1} y la cuadrícula tiene {columns}")
        if isinstance(row, list) and row:
            span = row[1] if len(row) > 1 else 1
            if row[0] + span - 1 > rows:
                errors.append(f"{path}.row: la viñeta termina en la fila {row[0] + span - 1} y rows define {rows}")
    images = [(f"panels[{i}].img", p.get("img")) for i, p in enumerate(cfg.get("panels", []))]
    images.append(("cover.img", (cfg.get("cover") or {}).get("img")))
    for path, src in images:
        if isinstance(src, str) and not re.match(r"^[a-z]+:", src) and not os.path.isfile(os.path.join(base_dir, src)):
            errors.append(f"{path}: no se encuentra la imagen {src}")
    return errors


def validate(cfg, base_dir):
    v = Validator(load_schema())
    v.check(cfg, v.root)
    errors = v.errors
    if not errors:
        errors = layout_errors(cfg, base_dir)
    return errors[:MAX_ERRORS]
