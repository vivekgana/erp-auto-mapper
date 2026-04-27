"""Lookup tables for ISO-standard reference data used in ERP transformations."""

from __future__ import annotations

import logging


logger = logging.getLogger(__name__)


class LookupManager:
    """Manages ISO and UN/CEFACT reference lookup tables for value standardisation.

    Provides currency (ISO 4217), country (ISO 3166-1 alpha-3), and
    unit-of-measure (UN/CEFACT Rec 20) code mappings used by the
    transformation layer to normalise ERP-native codes into CDM values.
    """

    def __init__(self) -> None:
        self._currency_map: dict[str, str] = self._build_currency_map()
        self._country_map: dict[str, str] = self._build_country_map()
        self._uom_map: dict[str, str] = self._build_uom_map()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_currency_map(self) -> dict[str, str]:
        """Return ISO 4217 currency code -> currency name mapping."""
        return dict(self._currency_map)

    def get_country_map(self) -> dict[str, str]:
        """Return ISO 3166-1 alpha-3 country code -> country name mapping."""
        return dict(self._country_map)

    def get_uom_map(self) -> dict[str, str]:
        """Return UN/CEFACT Rec 20 UOM code -> description mapping."""
        return dict(self._uom_map)

    def validate_code(self, code_type: str, value: str) -> bool:
        """Check whether *value* is a valid code in the given reference table.

        Args:
            code_type: One of ``"currency"``, ``"country"``, or ``"uom"``.
            value: The code to validate (case-insensitive for currency/country).

        Returns:
            ``True`` if the value exists in the lookup, ``False`` otherwise.
        """
        lookup = self._resolve_lookup(code_type)
        if lookup is None:
            logger.warning("Unknown code_type '%s'; validation returns False", code_type)
            return False
        return value.upper() in lookup

    def resolve_code(self, code_type: str, value: str) -> str | None:
        """Return the human-readable name for a code, or ``None`` if not found."""
        lookup = self._resolve_lookup(code_type)
        if lookup is None:
            return None
        return lookup.get(value.upper())

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_lookup(self, code_type: str) -> dict[str, str] | None:
        return {
            "currency": self._currency_map,
            "country": self._country_map,
            "uom": self._uom_map,
        }.get(code_type)

    @staticmethod
    def _build_currency_map() -> dict[str, str]:
        """ISO 4217 — top currencies used in enterprise audit scenarios."""
        return {
            "USD": "US Dollar",
            "EUR": "Euro",
            "GBP": "Pound Sterling",
            "JPY": "Japanese Yen",
            "CHF": "Swiss Franc",
            "CNY": "Chinese Yuan",
            "AUD": "Australian Dollar",
            "CAD": "Canadian Dollar",
            "INR": "Indian Rupee",
            "BRL": "Brazilian Real",
            "MXN": "Mexican Peso",
            "KRW": "South Korean Won",
            "SGD": "Singapore Dollar",
            "HKD": "Hong Kong Dollar",
            "NOK": "Norwegian Krone",
            "SEK": "Swedish Krona",
            "DKK": "Danish Krone",
            "ZAR": "South African Rand",
            "NZD": "New Zealand Dollar",
            "PLN": "Polish Zloty",
        }

    @staticmethod
    def _build_country_map() -> dict[str, str]:
        """ISO 3166-1 alpha-2 + alpha-3 — common countries in global ERP deployments."""
        return {
            "US": "United States",
            "USA": "United States",
            "GB": "United Kingdom",
            "GBR": "United Kingdom",
            "DE": "Germany",
            "DEU": "Germany",
            "FR": "France",
            "FRA": "France",
            "JP": "Japan",
            "JPN": "Japan",
            "CN": "China",
            "CHN": "China",
            "IN": "India",
            "IND": "India",
            "BR": "Brazil",
            "BRA": "Brazil",
            "CA": "Canada",
            "CAN": "Canada",
            "AU": "Australia",
            "AUS": "Australia",
            "CH": "Switzerland",
            "CHE": "Switzerland",
            "SG": "Singapore",
            "SGP": "Singapore",
            "HK": "Hong Kong",
            "HKG": "Hong Kong",
            "MX": "Mexico",
            "MEX": "Mexico",
            "KR": "South Korea",
            "KOR": "South Korea",
            "ZA": "South Africa",
            "ZAF": "South Africa",
            "NL": "Netherlands",
            "NLD": "Netherlands",
            "SE": "Sweden",
            "SWE": "Sweden",
            "NO": "Norway",
            "NOR": "Norway",
            "DK": "Denmark",
            "DNK": "Denmark",
        }

    @staticmethod
    def _build_uom_map() -> dict[str, str]:
        """UN/CEFACT Recommendation 20 — units common in audit/financial data."""
        return {
            "EA": "Each",
            "KG": "Kilogram",
            "LB": "Pound",
            "M": "Metre",
            "KM": "Kilometre",
            "L": "Litre",
            "GAL": "Gallon",
            "HR": "Hour",
            "DAY": "Day",
            "MON": "Month",
            "PC": "Piece",
            "SET": "Set",
            "PR": "Pair",
            "BX": "Box",
            "CT": "Carton",
            "PAL": "Pallet",
            "MT": "Metric Ton",
            "FT": "Foot",
            "IN": "Inch",
            "YD": "Yard",
        }
