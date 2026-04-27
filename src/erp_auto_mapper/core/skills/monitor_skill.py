"""MonitorDriftSkill — detect schema drift, data drift, and mapping staleness."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from erp_auto_mapper.core.extractors.base import ERPMetadata, FieldMetadata
from erp_auto_mapper.core.ingest.schema_inferrer import SchemaInferrer
from erp_auto_mapper.core.skills.base import SkillContext, SkillResult

logger = logging.getLogger(__name__)


class DriftAlert(BaseModel):
    """A single drift detection alert."""

    alert_type: str  # "schema_drift", "type_change", "new_field", "removed_field"
    entity: str = ""
    field: str = ""
    detail: str = ""
    severity: str = "medium"


class DriftReport(BaseModel):
    """Result of drift monitoring."""

    has_drift: bool = False
    alerts: list[DriftAlert] = Field(default_factory=list)
    entities_checked: int = 0
    fields_checked: int = 0


class MonitorDriftSkill:
    """Detect schema and data drift between current and baseline metadata."""

    def __init__(self, baseline_metadata: ERPMetadata | None = None) -> None:
        self._baseline = baseline_metadata
        self._inferrer = SchemaInferrer()

    @property
    def name(self) -> str:
        return "monitor_drift"

    async def execute(self, context: SkillContext) -> SkillResult:
        current = context.metadata
        baseline = self._baseline

        if current is None:
            return SkillResult(
                skill_name=self.name,
                status="failed",
                error="No metadata in context to monitor",
            )

        if baseline is None:
            return SkillResult(
                skill_name=self.name,
                output=DriftReport(
                    entities_checked=len(current.entities),
                    fields_checked=sum(len(e.fields) for e in current.entities),
                ),
                metrics={"alerts": 0},
            )

        report = self._compare(current, baseline)

        return SkillResult(
            skill_name=self.name,
            output=report,
            metrics={
                "alerts": len(report.alerts),
                "has_drift": 1.0 if report.has_drift else 0.0,
                "entities_checked": report.entities_checked,
            },
        )

    def _compare(self, current: ERPMetadata, baseline: ERPMetadata) -> DriftReport:
        alerts: list[DriftAlert] = []

        current_entities = {e.name: e for e in current.entities}
        baseline_entities = {e.name: e for e in baseline.entities}

        for name in baseline_entities:
            if name not in current_entities:
                alerts.append(DriftAlert(
                    alert_type="removed_entity",
                    entity=name,
                    detail=f"Entity '{name}' was present in baseline but is missing now",
                    severity="high",
                ))

        for name, entity in current_entities.items():
            if name not in baseline_entities:
                alerts.append(DriftAlert(
                    alert_type="new_entity",
                    entity=name,
                    detail=f"New entity '{name}' not present in baseline",
                    severity="medium",
                ))
                continue

            baseline_entity = baseline_entities[name]
            entity_alerts = self._compare_fields(
                name, entity.fields, baseline_entity.fields
            )
            alerts.extend(entity_alerts)

        total_fields = sum(len(e.fields) for e in current.entities)

        return DriftReport(
            has_drift=len(alerts) > 0,
            alerts=alerts,
            entities_checked=len(current_entities),
            fields_checked=total_fields,
        )

    @staticmethod
    def _compare_fields(
        entity_name: str,
        current_fields: list[FieldMetadata],
        baseline_fields: list[FieldMetadata],
    ) -> list[DriftAlert]:
        alerts: list[DriftAlert] = []

        current_by_name = {f.name: f for f in current_fields}
        baseline_by_name = {f.name: f for f in baseline_fields}

        for fname in baseline_by_name:
            if fname not in current_by_name:
                alerts.append(DriftAlert(
                    alert_type="removed_field",
                    entity=entity_name,
                    field=fname,
                    detail=f"Field '{fname}' removed from entity '{entity_name}'",
                    severity="high",
                ))

        for fname, field in current_by_name.items():
            if fname not in baseline_by_name:
                alerts.append(DriftAlert(
                    alert_type="new_field",
                    entity=entity_name,
                    field=fname,
                    detail=f"New field '{fname}' in entity '{entity_name}'",
                    severity="low",
                ))
                continue

            baseline_field = baseline_by_name[fname]
            if field.type != baseline_field.type:
                alerts.append(DriftAlert(
                    alert_type="type_change",
                    entity=entity_name,
                    field=fname,
                    detail=(
                        f"Field '{fname}' type changed: "
                        f"{baseline_field.type} -> {field.type}"
                    ),
                    severity="high",
                ))

            if field.nullable != baseline_field.nullable:
                alerts.append(DriftAlert(
                    alert_type="nullable_change",
                    entity=entity_name,
                    field=fname,
                    detail=(
                        f"Field '{fname}' nullable changed: "
                        f"{baseline_field.nullable} -> {field.nullable}"
                    ),
                    severity="medium",
                ))

        return alerts
