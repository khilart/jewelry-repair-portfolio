import json
import re
from datetime import datetime, time, timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# The ?Symbol= param value itself doesn't matter for us — any value makes Kitco
# also embed the "Currencies" block (USD rates for every currency it supports,
# RUB included even though it isn't in the visible currency switcher).
KITCO_URL = "https://www.kitco.com/price?Symbol=EUR"
KITCO_METAL_KEYS = {
    "gold": "gold",
    "silver": "silver",
    "platinum": "platinum",
    "palladium": "palladium",
    "rhodium": "rhodium",
}
TROY_OUNCE_IN_GRAMS = 31.1034768


class JewelryMetal(models.Model):
    _name = "jewelry.metal"
    _description = "Jewelry Metal"
    _order = "name"

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    active = fields.Boolean(default=True)
    alloy_ids = fields.One2many("jewelry.metal.alloy", "metal_id", string="Alloys")
    default_material_product_id = fields.Many2one(
        "product.product",
        string="Default Material Product",
        domain="[('product_tmpl_id.repair_material_ok', '=', True)]",
        help="Default product used when metal consumption is auto-calculated from a repair order. Used as fallback if not set on the alloy.",
    )
    kitco_exchange_fee_per_oz = fields.Float(
        string="Kitco Exchange Fee (per oz, USD)",
        default=60.0,
        help="Fixed fee in USD added on top of Kitco's quoted price per troy ounce "
        "before converting to a price per gram, via the \"Fetch Gold Price from Kitco\" button.",
    )


class JewelryMetalAlloy(models.Model):
    _name = "jewelry.metal.alloy"
    _description = "Jewelry Metal Alloy"
    _order = "metal_id, name, id"

    name = fields.Char(required=True)
    code = fields.Char(required=True)

    @api.model
    def name_create(self, name):
        if self.search([("name", "=ilike", name.strip())], limit=1):
            raise UserError(
                _("An alloy named \"%s\" already exists. To create a duplicate, use \"Create and edit...\"") % name
            )
        return super().name_create(name)
    metal_id = fields.Many2one("jewelry.metal", string="Metal", required=True)
    purity = fields.Float(
        required=True,
        digits=(16, 6),
        help="Fine metal coefficient, for example 0.585, 0.750, 0.999.",
    )
    active = fields.Boolean(default=True)
    default_material_product_id = fields.Many2one(
        "product.product",
        string="Default Material Product",
        domain="[('product_tmpl_id.repair_material_ok', '=', True)]",
        help="Default product used when metal consumption is auto-calculated from a repair order. Overrides the metal-level setting.",
    )
    effective_material_product_id = fields.Many2one(
        "product.product",
        string="Effective Material Product",
        compute="_compute_effective_material_product",
    )

    @api.depends("default_material_product_id", "metal_id.default_material_product_id")
    def _compute_effective_material_product(self):
        for alloy in self:
            alloy.effective_material_product_id = (
                alloy.default_material_product_id
                or alloy.metal_id.default_material_product_id
            )


class JewelryMetalRate(models.Model):
    _name = "jewelry.metal.rate"
    _description = "Jewelry Metal Rate"
    _order = "effective_at desc, id desc"

    metal_id = fields.Many2one("jewelry.metal", string="Metal", required=True)
    price_per_gram = fields.Monetary(string="Price per Gram", required=True, currency_field="currency_id")
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        required=True,
        default=lambda self: self.env.company.currency_id.id,
    )
    effective_at = fields.Datetime(string="Effective At", required=True, default=fields.Datetime.now)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company.id,
    )
    price_18k = fields.Monetary(
        string="18k (g)",
        compute="_compute_karat_prices",
        currency_field="currency_id",
    )
    price_14k = fields.Monetary(
        string="14k (g)",
        compute="_compute_karat_prices",
        currency_field="currency_id",
    )
    price_9k = fields.Monetary(
        string="9k (g)",
        compute="_compute_karat_prices",
        currency_field="currency_id",
    )
    notes = fields.Text()
    active = fields.Boolean(default=True)

    @api.depends("price_per_gram")
    def _compute_karat_prices(self):
        for rate in self:
            rate.price_18k = rate.price_per_gram * 0.750
            rate.price_14k = rate.price_per_gram * 0.585
            rate.price_9k  = rate.price_per_gram * 0.375

    @api.model
    def _fetch_kitco_data(self):
        try:
            response = requests.get(
                KITCO_URL,
                headers={"User-Agent": "Mozilla/5.0 (compatible; JewelryRepairBot/1.0)"},
                timeout=10,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            raise UserError(_("Could not reach Kitco: %s") % e)

        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            response.text,
            re.S,
        )
        if not match:
            raise UserError(_("Could not find price data on the Kitco page (site layout may have changed)."))

        try:
            data = json.loads(match.group(1))
        except ValueError:
            raise UserError(_("Kitco page returned invalid data."))

        return (
            data.get("props", {})
            .get("pageProps", {})
            .get("dehydratedState", {})
            .get("queries", [])
        )

    @api.model
    def _fetch_kitco_price_per_gram(self, metal):
        key = KITCO_METAL_KEYS.get(metal.name.strip().lower())
        if not key:
            raise UserError(_(
                "Kitco price is only available for Gold, Silver, Platinum, Palladium or Rhodium."
            ))

        queries = self._fetch_kitco_data()

        metal_data = None
        currencies_data = None
        for query in queries:
            query_data = query.get("state", {}).get("data")
            if not isinstance(query_data, dict):
                continue
            if key in query_data:
                metal_data = query_data[key]
            if query.get("queryKey") == ["Currencies", {}]:
                currencies_data = query_data

        results = (metal_data or {}).get("results") or []
        price_usd_per_oz = results[0].get("mid") if results else False
        if not price_usd_per_oz:
            raise UserError(_("Could not find a %s price in the Kitco data.") % metal.name)

        price_usd_per_gram = (price_usd_per_oz + metal.kitco_exchange_fee_per_oz) / TROY_OUNCE_IN_GRAMS

        company_currency = self.env.company.currency_id
        if company_currency.name == "USD":
            return price_usd_per_gram

        currency_data = (currencies_data or {}).get(company_currency.name)
        rate_results = (currency_data or {}).get("results") or []
        usd_to_currency = rate_results[0].get("mid") if rate_results else False
        if not usd_to_currency:
            raise UserError(_(
                "Kitco does not provide a USD/%s exchange rate — cannot convert the gold price into %s."
            ) % (company_currency.name, company_currency.name))

        return price_usd_per_gram * usd_to_currency

    @api.model
    def action_add_kitco_gold_rate(self):
        gold = self.env["jewelry.metal"].search([("name", "=", "Gold")], limit=1)
        if not gold:
            raise UserError(_("No metal named \"Gold\" found — create it first in Metals."))

        price = self._fetch_kitco_price_per_gram(gold)
        self.create({
            "metal_id": gold.id,
            "price_per_gram": price,
        })

    @api.model
    def _get_latest_rate(self, metal, effective_at, company=False):
        if not metal or not effective_at:
            return self.browse()
        company = company or self.env.company
        return self.search(
            [
                ("metal_id", "=", metal.id),
                ("company_id", "=", company.id),
                ("effective_at", "<=", effective_at),
            ],
            order="effective_at desc, id desc",
            limit=1,
        )
