# Jewelry 3D Model Library — Specification

## Purpose

A standalone library of 3D jewelry models for the workshop. Models serve as **order templates** for manufacturing jobs (`new_product_manufacturing = True`). When a manager selects a model on a repair/manufacturing order and clicks "Load from Model", the order is pre-filled with services, materials, and stone lines derived from the model.

## Module

`jewelry_3d_library` — depends on `jewelry_repair_base`, does not modify existing modules (extends via `_inherit` only).

---

## Models

### jewelry.model.3d — Main model record

| Field | Type | Description |
|-------|------|-------------|
| `name` | Char | Model name, required |
| `code` | Char | Article/reference |
| `category_id` | Many2one → jewelry.repair.item.type | Category (ring, bracelet…) |
| `preview_image` | Image | Photo/render |
| `notes` | Text | Internal notes |
| `stl_file` | Binary (attachment) | STL file |
| `stl_filename` | Char | Filename |
| `volume_cm3` | Float | Auto-calculated from STL via trimesh |
| `stone_seat_ids` | One2many | Parsed/manual stone seats |
| `service_template_ids` | One2many | Default services for this model |
| `material_template_ids` | One2many | Default materials (alloy + weight) |

**Button:** `action_parse_stl` — reads STL, computes volume, detects stone seats (circular holes), auto-matches diameter to `jewelry.gem.standard.size`.

---

### jewelry.model.3d.stone.seat — Stone seats

Parsed from STL or filled manually. Represents one group of identically-sized settings.

| Field | Type | Description |
|-------|------|-------------|
| `model_id` | Many2one | Parent model |
| `diameter_mm` | Float | Seat diameter in mm |
| `count` | Integer | Number of seats of this size |
| `standard_size_id` | Many2one → jewelry.gem.standard.size | Auto-matched by diameter |
| `gem_type_id` | Many2one → jewelry.gem.type | Filled by manager |
| `cut_shape` | Selection | Gem cut (round, oval, princess…) |

When loading into an order: only seats with `gem_type_id` set create `gem_line_ids`.

---

### jewelry.model.3d.service.template — Service templates

| Field | Type | Description |
|-------|------|-------------|
| `model_id` | Many2one | Parent model |
| `sequence` | Integer | Order |
| `product_id` | Many2one → product.product | Service product |
| `quantity` | Float | Default quantity |
| `price_unit` | Float | Default price (can be 0, manager adjusts) |

---

### jewelry.model.3d.material.template — Material templates

| Field | Type | Description |
|-------|------|-------------|
| `model_id` | Many2one | Parent model |
| `sequence` | Integer | Order |
| `alloy_id` | Many2one → jewelry.metal.alloy | Alloy |
| `weight` | Float | Weight in grams (manual or from volume × density) |
| `weight_auto` | Float (computed) | volume_cm3 × alloy.density |

---

## Extensions (via _inherit)

### jewelry.metal.alloy
- `density` (Float, g/cm³) — alloy density for weight estimation. Examples: Au585 ≈ 13.5, Au750 ≈ 15.5, Ag925 ≈ 10.3.

### jewelry.repair.order
- `model_3d_id` (Many2one → jewelry.model.3d) — selected model
- Button `action_load_from_model` — copies templates into order lines:
  - `service_template_ids` → `service_line_ids`
  - `material_template_ids` → `material_line_ids`
  - `stone_seat_ids` (with gem_type_id set) → `gem_line_ids`

---

## STL Parsing

Library: `trimesh` (installed in dev Docker image).

**Volume:**
```
volume_cm3 = abs(mesh.volume) / 1000
```

**Stone seat detection:**
1. Take a horizontal cross-section near the top of the mesh
2. Find closed edge loops in the section
3. For each loop: compute centroid + average radius; accept if std/mean < 0.15 and radius > 0.3 mm
4. Group by diameter (0.1 mm tolerance) → (diameter, count) table
5. Auto-match diameter to `jewelry.gem.standard.size`

If trimesh unavailable: volume = 0, stone seats = [] (manager fills manually).

---

## Business Rules

- Model library is workshop-owned (no per-client separation)
- Loading from model **appends** lines to the order (does not clear existing)
- `weight_auto` on material template is informational; `weight` is what gets copied
- Stone seats without `gem_type_id` are skipped when loading into order
- Density on alloy is optional; if missing, `weight_auto` = 0

## Out of Scope (MVP)

- Portal visibility of 3D models
- 3D viewer in browser
- Automatic stone seat detection without trimesh
- Version history of models
- Client-specific model libraries
