from datetime import datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_round

from .constants import (
    GEM_CUT_SHAPES,
    GEM_ORIGIN,
    STANDARD_ROUND_BRILLIANT_SIZES,
    GEM_LABS,
    GRADE_QUALITY,
    GEM_FLUORESCENCE,
)


class JewelryGemType(models.Model):
    _name = "jewelry.gem.type"
    _description = "Jewelry Gem Type"
    _order = "name"

    name = fields.Char(string="Name", required=True)
    active = fields.Boolean(default=True)
    parse_keywords = fields.Char(
        string="Certificate Keywords",
        help="Comma-separated keywords to match against certificate description during auto-parse (e.g. diamond, бриллиант)",
    )
    product_id = fields.Many2one("product.product", string="Default Invoice Product", domain=[("type", "=", "service")])
    standard_size_ids = fields.One2many(
        "jewelry.gem.standard.size", "gem_type_id", string="Standard Sizes"
    )
    setting_rule_ids = fields.One2many(
        "jewelry.gem.setting.rule", "gem_type_id", string="Setting Rules"
    )

    def action_load_standard_round_brilliant_sizes(self):
        self.ensure_one()
        existing = set(
            self.standard_size_ids.filtered(lambda s: s.cut_shape == "round").mapped("dim_1")
        )
        for dim, weight_ct in STANDARD_ROUND_BRILLIANT_SIZES:
            if dim not in existing:
                self.env["jewelry.gem.standard.size"].create({
                    "gem_type_id": self.id,
                    "cut_shape": "round",
                    "dim_1": dim,
                    "weight_ct": weight_ct,
                })


class JewelryGemStandardSize(models.Model):
    _name = "jewelry.gem.standard.size"
    _description = "Gem Standard Size"
    _rec_name = "label"
    _order = "gem_type_id, cut_shape, dim_1, dim_2"

    gem_type_id = fields.Many2one(
        "jewelry.gem.type", string="Gem Type", required=True, ondelete="cascade"
    )
    cut_shape = fields.Selection(GEM_CUT_SHAPES, string="Cut Shape", required=True)
    dim_1 = fields.Float(string="Dim 1 (mm)", digits=(16, 2), required=True)
    dim_2 = fields.Float(string="Dim 2 (mm)", digits=(16, 2))
    weight_ct = fields.Float(string="Weight (ct)", digits=(16, 4), required=True)
    weight_g = fields.Float(
        string="Weight (g)", compute="_compute_weight_g", store=True, digits=(16, 4)
    )
    label = fields.Char(string="Size", compute="_compute_label", store=True)

    @api.depends("weight_ct")
    def _compute_weight_g(self):
        for rec in self:
            rec.weight_g = rec.weight_ct * 0.2

    @api.depends("cut_shape", "dim_1", "dim_2")
    def _compute_label(self):
        for rec in self:
            if rec.cut_shape == "round":
                rec.label = f"{rec.dim_1:g} mm"
            elif rec.dim_2:
                rec.label = f"{rec.dim_1:g} × {rec.dim_2:g} mm"
            else:
                rec.label = f"{rec.dim_1:g} mm"


class JewelryGemSettingRule(models.Model):
    _name = "jewelry.gem.setting.rule"
    _description = "Gem Setting Service Rule"
    _order = "gem_type_id, weight_ct_from"

    gem_type_id = fields.Many2one(
        "jewelry.gem.type", string="Gem Type", required=True, ondelete="cascade"
    )
    service_product_id = fields.Many2one(
        "product.product",
        string="Service",
        required=True,
        domain="[('product_tmpl_id.repair_service_ok', '=', True)]",
    )
    weight_ct_from = fields.Float(string="Weight from (ct)", digits=(16, 4))
    weight_ct_to = fields.Float(
        string="Weight to (ct)", digits=(16, 4),
        help="0 means no upper limit"
    )


class JewelryGemCertificate(models.Model):
    _name = "jewelry.gem.certificate"
    _description = "Gem Certificate"
    _rec_name = "name"
    _order = "name"

    name = fields.Char(string="Report Number", required=True, copy=False)
    lab = fields.Selection(GEM_LABS, string="Laboratory")
    lab_other = fields.Char(string="Lab Name")
    cert_date = fields.Date(string="Date")
    gem_type_id = fields.Many2one("jewelry.gem.type", string="Gem Type")
    description = fields.Char(string="Description")
    origin = fields.Selection(
        [("natural", "Natural"), ("lab_grown", "Laboratory Grown")],
        string="Origin",
    )
    shape_cut = fields.Char(string="Shape & Cut")
    dim_1 = fields.Float(string="Dim 1 (mm)", digits=(16, 2))
    dim_2 = fields.Float(string="Dim 2 (mm)", digits=(16, 2))
    depth = fields.Float(string="Depth (mm)", digits=(16, 2))
    carat_weight = fields.Float(string="Carat Weight", digits=(16, 4))
    color_grade = fields.Char(string="Color Grade")
    clarity_grade = fields.Char(string="Clarity Grade")
    cut_grade = fields.Selection(GRADE_QUALITY, string="Cut Grade")
    polish = fields.Selection(GRADE_QUALITY, string="Polish")
    symmetry = fields.Selection(GRADE_QUALITY, string="Symmetry")
    fluorescence = fields.Selection(GEM_FLUORESCENCE, string="Fluorescence")
    lab_grown_type = fields.Selection(
        [("cvd", "CVD"), ("hpht", "HPHT")],
        string="Growth Type",
    )
    type_classification = fields.Char(string="Type Classification")
    comments = fields.Text(string="Comments")
    cert_image = fields.Binary(string="Certificate Image", attachment=True)
    cert_image_name = fields.Char(string="Image Filename")
    gem_line_ids = fields.One2many(
        "jewelry.repair.gem.line", "certificate_id", string="Used in Orders"
    )

    def action_view_image(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/image/jewelry.gem.certificate/{self.id}/cert_image",
            "target": "new",
        }

    @api.model
    def _parse_cert_image_vals(self, image_b64, filename):
        """Call Claude API and return dict of certificate field values."""
        try:
            import anthropic
        except ImportError:
            raise UserError(_(
                "The 'anthropic' Python package is not installed. "
                "Please install it on the server."
            ))
        api_key = self.env["ir.config_parameter"].sudo().get_param("anthropic.api_key")
        if not api_key:
            raise UserError(_(
                "Anthropic API key is not configured. "
                "Set 'anthropic.api_key' in Settings → Technical → System Parameters."
            ))
        import json as _json

        fn = (filename or "").lower()
        if fn.endswith(".png"):
            media_type = "image/png"
        elif fn.endswith(".webp"):
            media_type = "image/webp"
        else:
            media_type = "image/jpeg"

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "Extract all information from this gemstone certificate and return ONLY a valid JSON "
                            "object (no markdown, no extra text) with these exact keys "
                            "(use null for missing fields):\n"
                            "report_number, lab (GIA/IGI/HRD/AGS/EGL/CIBJO or lab name), "
                            "cert_date (YYYY-MM-DD), description, "
                            "gem_type (the type of gemstone, e.g. Diamond, Ruby, Sapphire, Emerald, Alexandrite, Pearl, or other gem name), "
                            "origin (Natural or Laboratory Grown), shape_cut, "
                            "dim_1 (float mm), dim_2 (float mm), depth (float mm), "
                            "carat_weight (float), color_grade, clarity_grade, "
                            "cut_grade (Excellent/Very Good/Good/Fair/Poor), "
                            "polish (Excellent/Very Good/Good/Fair/Poor), "
                            "symmetry (Excellent/Very Good/Good/Fair/Poor), "
                            "fluorescence (None/Faint/Medium/Strong/Very Strong), "
                            "lab_grown_type (CVD/HPHT), type_classification, comments."
                        ),
                    },
                ],
            }],
        )
        try:
            text = message.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            data = _json.loads(text)
        except Exception as e:
            raise UserError(_("Failed to parse API response: %s") % str(e))

        def _map_quality(val):
            if not val:
                return False
            return {
                "excellent": "excellent",
                "very good": "very_good",
                "good": "good",
                "fair": "fair",
                "poor": "poor",
            }.get(val.lower(), False)

        def _map_fluorescence(val):
            if not val:
                return False
            return {
                "none": "none",
                "faint": "faint",
                "medium": "medium",
                "strong": "strong",
                "very strong": "very_strong",
            }.get(val.lower(), False)

        def _map_lab(val):
            if not val:
                return False
            known = {"gia", "igi", "hrd", "ags", "egl", "cibjo"}
            v = val.lower()
            return v if v in known else "other"

        def _map_origin(val):
            if not val:
                return False
            v = val.lower()
            return "lab_grown" if ("lab" in v or "grown" in v or "synthetic" in v) else "natural"

        def _map_lab_grown_type(val):
            if not val:
                return False
            v = val.upper()
            if "CVD" in v:
                return "cvd"
            if "HPHT" in v:
                return "hpht"
            return False

        vals = {}
        if data.get("report_number"):
            vals["name"] = data["report_number"]
        if data.get("lab"):
            lab_val = _map_lab(data["lab"])
            if lab_val:
                vals["lab"] = lab_val
                if lab_val == "other":
                    vals["lab_other"] = data["lab"]
        if data.get("cert_date"):
            vals["cert_date"] = data["cert_date"]
        for char_field in ("description", "shape_cut", "color_grade", "clarity_grade",
                           "type_classification", "comments"):
            if data.get(char_field):
                vals[char_field] = data[char_field]
        if data.get("origin"):
            vals["origin"] = _map_origin(data["origin"])
        for float_field in ("dim_1", "dim_2", "depth", "carat_weight"):
            v = data.get(float_field)
            if v is not None:
                try:
                    vals[float_field] = float(v)
                except (TypeError, ValueError):
                    pass
        for q_field in ("cut_grade", "polish", "symmetry"):
            mapped = _map_quality(data.get(q_field))
            if mapped:
                vals[q_field] = mapped
        fluor = _map_fluorescence(data.get("fluorescence"))
        if fluor:
            vals["fluorescence"] = fluor
        lgt = _map_lab_grown_type(data.get("lab_grown_type"))
        if lgt:
            vals["lab_grown_type"] = lgt

        gem_type_raw = (data.get("gem_type") or "").lower()
        matched = False
        if gem_type_raw:
            for gt in self.env["jewelry.gem.type"].search([("parse_keywords", "!=", False)]):
                keywords = [k.strip().lower() for k in gt.parse_keywords.split(",") if k.strip()]
                if any(kw in gem_type_raw for kw in keywords):
                    vals["gem_type_id"] = gt.id
                    matched = True
                    break
        if not matched:
            desc_lower = (vals.get("description") or "").lower()
            if desc_lower:
                for gt in self.env["jewelry.gem.type"].search([("parse_keywords", "!=", False)]):
                    keywords = [k.strip().lower() for k in gt.parse_keywords.split(",") if k.strip()]
                    if any(kw in desc_lower for kw in keywords):
                        vals["gem_type_id"] = gt.id
                        break

        return vals

    def action_parse_from_image(self):
        self.ensure_one()
        if not self.cert_image:
            raise UserError(_("Please upload a certificate image first."))
        image_b64 = self.cert_image.decode() if isinstance(self.cert_image, bytes) else self.cert_image
        vals = self._parse_cert_image_vals(image_b64, self.cert_image_name)
        self.write(vals)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Success"),
                "message": _("Certificate data extracted successfully."),
                "type": "success",
            },
        }


class JewelryRepairGemLine(models.Model):
    _name = "jewelry.repair.gem.line"
    _inherit = "jewelry.repair.order.line.mixin"
    _description = "Repair Order Gem Line"
    _order = "id"

    order_id = fields.Many2one(
        "jewelry.repair.order", string="Order", required=True, ondelete="cascade"
    )
    gem_type_id = fields.Many2one("jewelry.gem.type", string="Gem Type", required=True)
    origin = fields.Selection(
        GEM_ORIGIN,
        string="Origin",
        help="Natural or laboratory grown. Kept on the line because melee carries no "
             "certificate, and the certificate is the only place the origin used to live.",
    )
    cut_shape = fields.Selection(GEM_CUT_SHAPES, string="Cut Shape")
    standard_size_id = fields.Many2one(
        "jewelry.gem.standard.size",
        string="Standard Size",
        domain="[('gem_type_id', '=', gem_type_id), ('cut_shape', '=', cut_shape)]",
    )
    quantity = fields.Integer(string="Qty", default=1, required=True)
    weight_ct = fields.Float(string="Weight/pc (ct)", digits=(16, 4))
    total_weight_ct = fields.Float(
        string="Total (ct)",
        compute="_compute_total_weight_ct",
        inverse="_inverse_total_weight_ct",
        store=True,
        digits=(16, 4),
    )
    total_weight_g = fields.Float(
        string="Total (g)", compute="_compute_total_weight_g", store=True, digits=(16, 4)
    )
    product_id = fields.Many2one("product.product", string="Product", domain=[("type", "=", "service")])
    price_per_ct = fields.Monetary(string="Price/ct", currency_field="currency_id")
    price_unit = fields.Monetary(string="Price/pc", currency_field="currency_id")
    subtotal = fields.Monetary(string="Amount", currency_field="currency_id", compute="_compute_subtotal", store=True)
    currency_id = fields.Many2one(related="order_id.currency_id", store=True)
    include_in_invoice = fields.Boolean(string="Bill to Client", default=False)
    certificate_id = fields.Many2one(
        "jewelry.gem.certificate", string="Certificate", ondelete="set null"
    )

    def _price_per_piece(self):
        """Price of one stone, in whole units.

        A price per carat times a fractional weight lands on kopecks the workshop
        does not quote, so the derived piece price is rounded; a price entered by
        hand is kept as typed.
        """
        self.ensure_one()
        if self.price_per_ct and self.weight_ct:
            return float_round(self.price_per_ct * self.weight_ct, precision_digits=0)
        return self.price_unit

    @api.depends("quantity", "price_per_ct", "weight_ct", "price_unit")
    def _compute_subtotal(self):
        for rec in self:
            rec.subtotal = rec.quantity * rec._price_per_piece()

    @api.onchange("price_per_ct")
    def _onchange_price_per_ct(self):
        self.price_unit = self._price_per_piece() if self.weight_ct else 0.0

    @api.onchange("price_unit")
    def _onchange_price_unit(self):
        if self.weight_ct:
            self.price_per_ct = self.price_unit / self.weight_ct

    @api.onchange("certificate_id")
    def _onchange_certificate_id(self):
        cert = self.certificate_id
        if not cert:
            return
        if cert.gem_type_id:
            self.gem_type_id = cert.gem_type_id
        if cert.origin:
            self.origin = cert.origin
        if cert.carat_weight:
            self.weight_ct = cert.carat_weight
            self.total_weight_ct = cert.carat_weight * (self.quantity or 1)
        if cert.shape_cut:
            shape_lower = cert.shape_cut.lower()
            for key in ("round", "oval", "princess", "cushion", "emerald",
                        "radiant", "pear", "marquise", "heart", "asscher", "trapezoid"):
                if key in shape_lower:
                    self.cut_shape = key
                    break
        if self.price_per_ct and self.weight_ct:
            self.price_unit = self._price_per_piece()

    @api.onchange("gem_type_id")
    def _onchange_gem_type_id(self):
        if self.gem_type_id and self.gem_type_id.product_id and not self.product_id:
            self.product_id = self.gem_type_id.product_id

    @api.onchange("standard_size_id")
    def _onchange_standard_size_id(self):
        if self.standard_size_id:
            self.weight_ct = self.standard_size_id.weight_ct

    @api.onchange("total_weight_ct")
    def _onchange_total_weight_ct(self):
        if self.quantity:
            self.weight_ct = self.total_weight_ct / self.quantity

    @api.depends("quantity", "weight_ct")
    def _compute_total_weight_ct(self):
        for rec in self:
            rec.total_weight_ct = rec.quantity * rec.weight_ct

    def _inverse_total_weight_ct(self):
        for rec in self:
            if rec.quantity:
                rec.weight_ct = rec.total_weight_ct / rec.quantity

    @api.depends("quantity", "weight_ct")
    def _compute_total_weight_g(self):
        for rec in self:
            rec.total_weight_g = rec.quantity * rec.weight_ct * 0.2

    def action_open_cert_parse_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "jewelry.gem.cert.parse.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_gem_line_id": self.id},
        }


class JewelryGemCertParseWizard(models.TransientModel):
    _name = "jewelry.gem.cert.parse.wizard"
    _description = "Parse Certificate from Photo"

    order_id = fields.Many2one("jewelry.repair.order")
    gem_line_id = fields.Many2one("jewelry.repair.gem.line")
    cert_image = fields.Binary(string="Certificate Photo")
    cert_image_name = fields.Char()
    state = fields.Selection(
        [("upload", "Upload"), ("duplicate", "Duplicate Found")],
        default="upload",
    )
    existing_cert_id = fields.Many2one("jewelry.gem.certificate", readonly=True)
    pending_cert_vals = fields.Text()

    def action_parse_and_create(self):
        self.ensure_one()
        if not self.cert_image:
            raise UserError(_("Please upload a certificate image."))

        import json as _json
        image_b64 = self.cert_image.decode() if isinstance(self.cert_image, bytes) else self.cert_image
        cert_model = self.env["jewelry.gem.certificate"]
        cert_vals = cert_model._parse_cert_image_vals(image_b64, self.cert_image_name)
        cert_vals["cert_image"] = self.cert_image
        cert_vals["cert_image_name"] = self.cert_image_name
        if not cert_vals.get("name"):
            raise UserError(_("Could not extract report number from the image. Please check the photo quality."))

        existing = cert_model.search([("name", "=", cert_vals["name"])], limit=1)
        if existing:
            self.write({
                "state": "duplicate",
                "existing_cert_id": existing.id,
                "pending_cert_vals": _json.dumps({
                    k: v for k, v in cert_vals.items()
                    if k not in ("cert_image", "cert_image_name")
                }),
            })
            return {
                "type": "ir.actions.act_window",
                "res_model": "jewelry.gem.cert.parse.wizard",
                "res_id": self.id,
                "view_mode": "form",
                "target": "new",
            }

        cert = cert_model.create(cert_vals)
        self._apply_cert(cert)
        return {"type": "ir.actions.act_window_close"}

    def action_use_existing(self):
        self.ensure_one()
        self._apply_cert(self.existing_cert_id)
        return {"type": "ir.actions.act_window_close"}

    def action_create_new(self):
        self.ensure_one()
        import json as _json
        cert_vals = _json.loads(self.pending_cert_vals or "{}")
        cert_vals["cert_image"] = self.cert_image
        cert_vals["cert_image_name"] = self.cert_image_name
        cert = self.env["jewelry.gem.certificate"].create(cert_vals)
        self._apply_cert(cert)
        return {"type": "ir.actions.act_window_close"}

    def _apply_cert(self, cert):
        line_vals = {"certificate_id": cert.id}
        if cert.gem_type_id:
            line_vals["gem_type_id"] = cert.gem_type_id.id
        if cert.carat_weight:
            line_vals["weight_ct"] = cert.carat_weight
        if cert.shape_cut:
            shape_lower = cert.shape_cut.lower()
            for key in ("round", "oval", "princess", "cushion", "emerald",
                        "radiant", "pear", "marquise", "heart", "asscher", "trapezoid"):
                if key in shape_lower:
                    line_vals["cut_shape"] = key
                    break

        if self.gem_line_id:
            line = self.gem_line_id
            qty = line.quantity or 1
            if cert.carat_weight:
                line_vals["total_weight_ct"] = cert.carat_weight * qty
            if line.price_per_ct and line_vals.get("weight_ct"):
                line_vals["price_unit"] = float_round(
                    line.price_per_ct * line_vals["weight_ct"], precision_digits=0
                )
            line.write(line_vals)
        elif self.order_id:
            line_vals["order_id"] = self.order_id.id
            line_vals.setdefault("quantity", 1)
            if cert.carat_weight:
                line_vals["total_weight_ct"] = cert.carat_weight * line_vals["quantity"]
            if not line_vals.get("gem_type_id"):
                raise UserError(_(
                    "Gem type could not be determined from the certificate. "
                    "Please add the stone manually."
                ))
            self.env["jewelry.repair.gem.line"].create(line_vals)
