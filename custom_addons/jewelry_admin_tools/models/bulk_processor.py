import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval


class JewelryBulkProcessor(models.TransientModel):
    _name = "jewelry.bulk.processor"
    _description = "Bulk Data Processor"

    model_id = fields.Many2one("ir.model", string="Model", required=True, domain=[("transient", "=", False)])
    model_name = fields.Char(related="model_id.model", string="Model Technical Name")
    domain = fields.Char(string="Filter", default="[]")
    operation_line_ids = fields.One2many("jewelry.bulk.operation.line", "processor_id", string="Operations")
    preview_line_ids = fields.One2many("jewelry.bulk.preview.line", "processor_id", string="Preview")
    state = fields.Selection(
        [("draft", "Draft"), ("previewed", "Previewed"), ("ai_done", "AI Done"), ("applied", "Applied")],
        default="draft",
        required=True,
    )

    def action_preview(self):
        self.ensure_one()
        if not self.operation_line_ids:
            raise UserError(_("Add at least one operation."))

        model = self.env[self.model_id.model]
        domain = safe_eval(self.domain or "[]")
        records = model.search(domain)
        if not records:
            raise UserError(_("No records match the filter."))

        self.preview_line_ids.unlink()

        lines = []
        for op in self.operation_line_ids:
            field_name = op.field_id.name
            if op.operation_type == "ai_translate":
                langs = op.ai_target_lang_ids or self.env["res.lang"].search([("active", "=", True)])
                for record in records:
                    for lang in langs:
                        current = record.with_context(lang=lang.code).read([field_name])[0][field_name] or ""
                        lines.append({
                            "processor_id": self.id,
                            "operation_line_id": op.id,
                            "res_id": record.id,
                            "res_name": record.display_name,
                            "field_id": op.field_id.id,
                            "operation_type": "ai_translate",
                            "lang_id": lang.id,
                            "current_value": current,
                            "new_value": "",
                            "selected": True,
                        })
            elif op.operation_type == "ai_transform":
                for record in records:
                    current = record.read([field_name])[0][field_name] or ""
                    lines.append({
                        "processor_id": self.id,
                        "operation_line_id": op.id,
                        "res_id": record.id,
                        "res_name": record.display_name,
                        "field_id": op.field_id.id,
                        "operation_type": "ai_transform",
                        "current_value": current,
                        "new_value": "",
                        "selected": True,
                    })
            elif op.operation_type == "set_value":
                for record in records:
                    current = record.read([field_name])[0][field_name] or ""
                    lines.append({
                        "processor_id": self.id,
                        "operation_line_id": op.id,
                        "res_id": record.id,
                        "res_name": record.display_name,
                        "field_id": op.field_id.id,
                        "operation_type": "set_value",
                        "current_value": current,
                        "new_value": op.set_value or "",
                        "selected": True,
                    })
            elif op.operation_type == "clear":
                for record in records:
                    current = record.read([field_name])[0][field_name] or ""
                    lines.append({
                        "processor_id": self.id,
                        "operation_line_id": op.id,
                        "res_id": record.id,
                        "res_name": record.display_name,
                        "field_id": op.field_id.id,
                        "operation_type": "clear",
                        "current_value": current,
                        "new_value": "",
                        "selected": True,
                    })

        self.env["jewelry.bulk.preview.line"].create(lines)
        self.state = "previewed"

    def action_run_ai(self):
        self.ensure_one()
        ai_lines = self.preview_line_ids.filtered(
            lambda l: l.operation_type in ("ai_translate", "ai_transform") and l.selected
        )
        if not ai_lines:
            raise UserError(_("No AI translation lines selected."))

        api_key = self.env["ir.config_parameter"].sudo().get_param("anthropic.api_key")
        if not api_key:
            raise UserError(
                _("Anthropic API key not set. Configure 'anthropic.api_key' in Settings → Technical → System Parameters.")
            )
        try:
            import anthropic as anthropic_lib
        except ImportError:
            raise UserError(_("The 'anthropic' Python package is not installed."))

        client = anthropic_lib.Anthropic(api_key=api_key)
        model = self.env[self.model_id.model]

        # Group lines by operation to batch per-operation call
        by_op = {}
        for line in ai_lines:
            by_op.setdefault(line.operation_line_id.id, []).append(line)

        for op_id, lines in by_op.items():
            op = lines[0].operation_line_id
            field_name = op.field_id.name

            res_ids = list({l.res_id for l in lines})
            source_values = {}
            for res_id in res_ids:
                ctx = {"lang": op.ai_source_lang_id.code} if op.ai_source_lang_id else {}
                val = model.browse(res_id).with_context(**ctx).read([field_name])[0][field_name] or ""
                source_values[str(res_id)] = val

            context_part = f"\nContext: {op.ai_context}" if op.ai_context else ""

            if op.operation_type == "ai_translate":
                lang_map = {l.lang_id.code: l.lang_id.name for l in lines}
                prompt = (
                    f"Translate these names from {op.ai_source_lang_id.name} to the specified languages.{context_part}\n\n"
                    f"Records (id → name):\n{json.dumps(source_values, ensure_ascii=False, indent=2)}\n\n"
                    f"Target languages: {json.dumps(lang_map, ensure_ascii=False)}\n\n"
                    'Return ONLY valid JSON: {"<id>": {"<lang_code>": "<translation>", ...}, ...}'
                )
            else:  # ai_transform
                prompt = (
                    f"Apply this transformation rule to each value.{context_part}\n"
                    f"Rule: {op.ai_rule}\n\n"
                    f"Records (id → value):\n{json.dumps(source_values, ensure_ascii=False, indent=2)}\n\n"
                    'Return ONLY valid JSON: {"<id>": "<transformed_value>", ...}'
                )

            message = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                system="You are a data transformation API. Respond with raw JSON only. No markdown, no code blocks, no explanation.",
                messages=[{"role": "user", "content": prompt}],
            )

            raw = message.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1]
                raw = raw.rsplit("```", 1)[0]
            try:
                result = json.loads(raw)
            except (json.JSONDecodeError, IndexError, KeyError):
                raise UserError(_("AI returned an invalid response. Try again."))

            if op.operation_type == "ai_translate":
                for line in lines:
                    translations = result.get(str(line.res_id), {})
                    if line.lang_id.code in translations:
                        line.new_value = translations[line.lang_id.code]
            else:  # ai_transform
                for line in lines:
                    line.new_value = result.get(str(line.res_id), "")

        self.state = "ai_done"

    def action_select_all(self):
        self.preview_line_ids.write({"selected": True})

    def action_deselect_all(self):
        self.preview_line_ids.write({"selected": False})

    def action_apply(self):
        self.ensure_one()
        model = self.env[self.model_id.model]
        for line in self.preview_line_ids.filtered(lambda l: l.selected):
            record = model.browse(line.res_id)
            field_name = line.field_id.name
            value = line.new_value if line.operation_type != "clear" else False
            if line.lang_id:
                record.with_context(lang=line.lang_id.code).write({field_name: value})
            else:
                record.write({field_name: value})
        self.state = "applied"


class JewelryBulkOperationLine(models.TransientModel):
    _name = "jewelry.bulk.operation.line"
    _description = "Bulk Operation Line"

    processor_id = fields.Many2one("jewelry.bulk.processor", required=True, ondelete="cascade")
    field_id = fields.Many2one(
        "ir.model.fields",
        string="Field",
        required=True,
        domain="[('model_id', '=', parent.model_id), ('ttype', 'in', ['char', 'text', 'html'])]",
    )
    operation_type = fields.Selection(
        [("ai_translate", "AI Translate"), ("ai_transform", "AI Transform"), ("set_value", "Set Value"), ("clear", "Clear")],
        string="Operation",
        required=True,
        default="ai_translate",
    )
    set_value = fields.Char(string="Value")
    ai_context = fields.Text(string="AI Context")
    ai_rule = fields.Text(string="Rule")
    ai_source_lang_id = fields.Many2one(
        "res.lang",
        string="Source Language",
        domain=[("active", "=", True)],
    )
    ai_target_lang_ids = fields.Many2many(
        "res.lang",
        "jewelry_bulk_op_line_lang_rel",
        "line_id",
        "lang_id",
        string="Target Languages",
        domain=[("active", "=", True)],
        help="Leave empty to use all active languages.",
    )


class JewelryBulkPreviewLine(models.TransientModel):
    _name = "jewelry.bulk.preview.line"
    _description = "Bulk Preview Line"
    _order = "res_name, lang_id"

    processor_id = fields.Many2one("jewelry.bulk.processor", required=True, ondelete="cascade")
    operation_line_id = fields.Many2one("jewelry.bulk.operation.line", ondelete="cascade")
    res_id = fields.Integer(string="Record ID")
    res_name = fields.Char(string="Record")
    field_id = fields.Many2one("ir.model.fields", string="Field")
    operation_type = fields.Char(string="Operation")
    lang_id = fields.Many2one("res.lang", string="Language")
    current_value = fields.Char(string="Current")
    new_value = fields.Char(string="New Value")
    selected = fields.Boolean(string="Apply", default=True)
