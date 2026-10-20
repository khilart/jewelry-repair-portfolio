import base64
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

GEM_CUT_SHAPES = [
    ("round", "Round"),
    ("oval", "Oval"),
    ("princess", "Princess"),
    ("cushion", "Cushion"),
    ("emerald", "Emerald"),
    ("radiant", "Radiant"),
    ("pear", "Pear"),
    ("marquise", "Marquise"),
    ("heart", "Heart"),
    ("asscher", "Asscher"),
    ("trapezoid", "Trapezoid"),
]


def _render_preview(mesh):
    """Render an isometric preview using Pillow (painter's algorithm, no GPU needed)."""
    try:
        import io
        import numpy as np
        from PIL import Image, ImageDraw

        # Rotation: 25° around X, 45° around Z
        ax = 25 * np.pi / 180
        az = 45 * np.pi / 180
        Rx = np.array([[1, 0, 0],
                        [0, np.cos(ax), -np.sin(ax)],
                        [0, np.sin(ax),  np.cos(ax)]])
        Rz = np.array([[np.cos(az), -np.sin(az), 0],
                        [np.sin(az),  np.cos(az), 0],
                        [0,           0,           1]])
        verts = mesh.vertices @ (Rz @ Rx).T

        size = 512
        padding = 24
        vmin = verts.min(axis=0)
        vmax = verts.max(axis=0)
        span = max(vmax[0] - vmin[0], vmax[1] - vmin[1], 1e-6)
        scale = (size - 2 * padding) / span

        v2d = (verts[:, :2] - vmin[:2]) * scale + padding

        # Painter's algorithm: back-to-front by mean Z
        depths = verts[mesh.faces, 2].mean(axis=1)
        sorted_faces = mesh.faces[np.argsort(depths)]

        img = Image.new('RGB', (size, size), 'white')
        draw = ImageDraw.Draw(img)

        for face in sorted_faces:
            pts = [(float(v2d[i, 0]), float(size - v2d[i, 1])) for i in face]
            draw.polygon(pts, fill='#d4a843', outline='#a07820')

        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return base64.b64encode(buf.getvalue()).decode('ascii')
    except Exception as e:
        _logger.warning("Preview render failed: %s", e)
        return False


def _parse_stl(stl_bytes):
    """Parse STL binary data using trimesh.
    Returns (mesh, volume_cm3, stone_seats).
    mesh is None if parsing failed.
    stone_seats = [(diameter_mm, count), ...]
    """
    try:
        import io
        import trimesh
        import numpy as np
        from collections import defaultdict

        mesh = trimesh.load(io.BytesIO(stl_bytes), file_type='stl')
        if not isinstance(mesh, trimesh.Trimesh):
            raise ValueError("Not a valid mesh")

        volume_cm3 = abs(mesh.volume) / 1000.0

        stone_seats = []
        try:
            bounds = mesh.bounds
            z_min, z_max = bounds[0][2], bounds[1][2]
            z_sample = z_max - (z_max - z_min) * 0.15

            section = mesh.section(
                plane_origin=[0, 0, z_sample],
                plane_normal=[0, 0, 1],
            )
            if section is not None:
                path2d, _ = section.to_planar()
                circles = []
                for entity in path2d.entities:
                    pts = path2d.vertices[entity.points]
                    if len(pts) < 6:
                        continue
                    centroid = pts.mean(axis=0)
                    radii = np.linalg.norm(pts - centroid, axis=1)
                    r = radii.mean()
                    if r < 0.3:
                        continue
                    if radii.std() / r < 0.15:
                        circles.append(round(r * 2, 2))

                groups = defaultdict(int)
                for d in circles:
                    key = round(d / 0.1) * 0.1
                    groups[key] += 1

                stone_seats = sorted(groups.items(), key=lambda x: x[0])

        except Exception as e:
            _logger.warning("Stone seat detection failed: %s", e)

        return mesh, volume_cm3, stone_seats

    except ImportError:
        _logger.warning("trimesh not available — STL parsing skipped")
        return None, 0.0, []
    except Exception as e:
        _logger.error("STL parsing error: %s", e)
        return None, 0.0, []


class JewelryModel3D(models.Model):
    _name = "jewelry.model.3d"
    _description = "Jewelry 3D Model"
    _order = "name"

    name = fields.Char(string="Model Name", required=True)
    code = fields.Char(string="Article")
    category_id = fields.Many2one("jewelry.repair.item.type", string="Category")
    preview_image = fields.Image(string="Preview")
    notes = fields.Text(string="Notes")

    stl_file = fields.Binary(string="STL File", attachment=True)
    stl_filename = fields.Char(string="STL Filename")
    volume_cm3 = fields.Float(string="Volume (cm³)", digits=(16, 4))

    stone_seat_ids = fields.One2many(
        "jewelry.model.3d.stone.seat", "model_id", string="Stone Seats",
    )
    service_template_ids = fields.One2many(
        "jewelry.model.3d.service.template", "model_id", string="Service Templates",
    )
    material_template_ids = fields.One2many(
        "jewelry.model.3d.material.template", "model_id", string="Material Templates",
    )

    def action_view_3d(self):
        self.ensure_one()
        if not self.stl_file:
            raise UserError(_("Upload an STL file first."))
        return {
            "type": "ir.actions.client",
            "tag": "jewelry_3d_viewer",
            "name": self.name,
            "params": {
                "res_id": self.id,
            },
        }

    def action_parse_stl(self):
        self.ensure_one()
        if not self.stl_file:
            raise UserError(_("Upload an STL file first."))

        stl_bytes = base64.b64decode(self.stl_file)
        mesh, volume_cm3, stone_seats = _parse_stl(stl_bytes)

        if not volume_cm3:
            raise UserError(_("Could not parse the STL file. Check that the file is a valid closed mesh."))

        # 1. Volume
        self.volume_cm3 = volume_cm3

        # 2. Preview (only if not set manually)
        if not self.preview_image and mesh is not None:
            preview = _render_preview(mesh)
            if preview:
                self.preview_image = preview

        # 3. Stone seats
        self.stone_seat_ids.unlink()
        for diameter_mm, count in stone_seats:
            standard_size = self.env["jewelry.gem.standard.size"].search(
                [("diameter_mm", ">=", diameter_mm - 0.1),
                 ("diameter_mm", "<=", diameter_mm + 0.1)],
                limit=1,
            )
            self.env["jewelry.model.3d.stone.seat"].create({
                "model_id": self.id,
                "diameter_mm": diameter_mm,
                "count": count,
                "standard_size_id": standard_size.id if standard_size else False,
            })

        # 4. Material templates — fill with all alloys (only if empty)
        if not self.material_template_ids:
            alloys = self.env["jewelry.metal.alloy"].search([], order="name")
            self.env["jewelry.model.3d.material.template"].create([
                {"model_id": self.id, "alloy_id": alloy.id, "sequence": (i + 1) * 10}
                for i, alloy in enumerate(alloys)
            ])

        # 5. Notification (no next — form reloads naturally)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("STL Parsed"),
                "message": _("Volume: %.4f cm³ · Stone seats: %d") % (volume_cm3, len(stone_seats)),
                "type": "success",
                "sticky": False,
            },
        }


class JewelryModel3DStoneSeat(models.Model):
    _name = "jewelry.model.3d.stone.seat"
    _description = "Stone Seat"
    _order = "diameter_mm"

    model_id = fields.Many2one("jewelry.model.3d", required=True, ondelete="cascade")
    diameter_mm = fields.Float(string="Diameter (mm)", digits=(16, 2), required=True)
    count = fields.Integer(string="Count", default=1, required=True)
    standard_size_id = fields.Many2one("jewelry.gem.standard.size", string="Standard Size")
    gem_type_id = fields.Many2one("jewelry.gem.type", string="Gem Type")
    cut_shape = fields.Selection(GEM_CUT_SHAPES, string="Cut")


class JewelryModel3DServiceTemplate(models.Model):
    _name = "jewelry.model.3d.service.template"
    _description = "Model Service Template"
    _order = "sequence, id"

    model_id = fields.Many2one("jewelry.model.3d", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one(
        "product.product", string="Service", required=True,
        domain=[("type", "=", "service")],
    )
    quantity = fields.Float(default=1.0, required=True)
    price_unit = fields.Float(string="Price")


class JewelryModel3DMaterialTemplate(models.Model):
    _name = "jewelry.model.3d.material.template"
    _description = "Model Material Template"
    _order = "sequence, id"

    model_id = fields.Many2one("jewelry.model.3d", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    alloy_id = fields.Many2one("jewelry.metal.alloy", string="Alloy", required=True)
    weight = fields.Float(string="Weight (g)", digits=(16, 3))
    weight_auto = fields.Float(
        string="Est. Weight (g)",
        compute="_compute_weight_auto",
        digits=(16, 3),
    )
    price_est = fields.Float(
        string="Est. Price",
        compute="_compute_price_est",
        digits=(16, 2),
    )

    @api.depends("model_id.volume_cm3", "alloy_id.density")
    def _compute_weight_auto(self):
        for line in self:
            vol = line.model_id.volume_cm3
            density = line.alloy_id.density
            line.weight_auto = vol * density if vol and density else 0.0

    @api.depends("weight_auto", "alloy_id")
    def _compute_price_est(self):
        now = fields.Datetime.now()
        for line in self:
            if not line.weight_auto or not line.alloy_id:
                line.price_est = 0.0
                continue
            rate = self.env["jewelry.metal.rate"]._get_latest_rate(
                line.alloy_id.metal_id, now, self.env.company,
            )
            if rate:
                line.price_est = rate.price_per_gram * (line.alloy_id.purity or 0.0) * line.weight_auto
            else:
                line.price_est = 0.0
