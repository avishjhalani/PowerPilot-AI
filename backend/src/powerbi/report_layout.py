import json
import uuid
import re
from typing import Dict, Any, List, Optional


class ReportLayoutBuilder:
    """
    Constructs a production-grade executive visual grid layout for Power BI report.json.
    Canvas: 1280x720, CY24SU02 base theme.

    Grid Structure:
      - Tier 1: Top KPI Cards (Y = 30, H = 100)
      - Tier 2: Middle Row - Primary Visuals (Y = 150, H = 320)
      - Tier 3: Bottom Row - Secondary Charts (Y = 490, H = 200)

    Strict compliance with Power BI Desktop's ExplorationSerializer:
      - Every visual container uses singleVisual in its config
      - vcObjects strictly contains standard title properties
      - All dimension & measure references dynamically resolved and case-synchronized
    """

    def __init__(
        self,
        canvas_width: int = 1280,
        canvas_height: int = 720,
        accent_color: str = "#1F3864",
    ):
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        self.margin = 30
        self.gap = 20
        self.accent_color = accent_color

    def _generate_guid(self) -> str:
        return uuid.uuid4().hex[:8]

    # ------------------------------------------------------------------
    # Dimension / measure resolution (100% case-synchronized)
    # ------------------------------------------------------------------
    def _resolve_dimension(self, requested_dim: Optional[str], available_columns: List[str] = None) -> str:
        if not available_columns:
            return str(requested_dim) if requested_dim else "Category"

        if not requested_dim or not isinstance(requested_dim, str) or not requested_dim.strip():
            preferred = ["category", "type", "region", "sku", "product", "customer", "segment", "status", "channel"]
            for p in preferred:
                for col in available_columns:
                    if p in col.lower():
                        return col
            non_id = [c for c in available_columns if "id" not in c.lower()]
            return non_id[0] if non_id else available_columns[0]

        if requested_dim in available_columns:
            return requested_dim

        req_clean = requested_dim.strip().lower()
        for col in available_columns:
            if col.strip().lower() == req_clean:
                return col

        req_norm = req_clean.replace("_", " ").replace("-", " ")
        for col in available_columns:
            col_norm = col.strip().lower().replace("_", " ").replace("-", " ")
            if col_norm == req_norm or col_norm.replace(" ", "") == req_norm.replace(" ", ""):
                return col

        for col in available_columns:
            if req_clean in col.lower() or col.lower() in req_clean:
                return col

        preferred = ["category", "type", "region", "sku", "product", "customer", "segment", "status", "channel"]
        for p in preferred:
            for col in available_columns:
                if p in col.lower():
                    return col

        non_id = [c for c in available_columns if "id" not in c.lower()]
        return non_id[0] if non_id else available_columns[0]

    def _resolve_measure(self, requested_measure: Optional[str], available_measures: List[str] = None) -> str:
        if not available_measures:
            return str(requested_measure) if requested_measure else "Metric"

        if not requested_measure or not isinstance(requested_measure, str) or not requested_measure.strip():
            return available_measures[0]

        if requested_measure in available_measures:
            return requested_measure

        req_clean = requested_measure.strip().lower()
        for m in available_measures:
            if m.strip().lower() == req_clean:
                return m

        for m in available_measures:
            m_clean = m.strip().lower().replace("_", " ")
            if m_clean == req_clean.replace("_", " ") or m_clean.replace(" ", "") == req_clean.replace(" ", ""):
                return m

        for m in available_measures:
            if req_clean in m.lower() or m.lower() in req_clean:
                return m

        return available_measures[0]

    def _build_card_container(
        self,
        card: Dict[str, Any],
        table_name: str,
        x: int,
        y: int,
        w: int,
        h: int,
        z: int,
        available_measures: List[str] = None
    ) -> Dict[str, Any]:
        raw_measure = card.get("measure") or "Metric"
        measure_name = self._resolve_measure(raw_measure, available_measures) if available_measures else str(raw_measure)
        title_text = card.get("title") or measure_name
        visual_name = self._generate_guid()

        config = {
            "name": visual_name,
            "singleVisual": {
                "visualType": "card",
                "projections": {
                    "Values": [
                        {"queryRef": f"{table_name}.{measure_name}"}
                    ]
                },
                "prototypeQuery": {
                    "Version": 2,
                    "From": [{"Name": "t", "Entity": table_name, "Type": 0}],
                    "Select": [
                        {
                            "Measure": {
                                "Expression": {"SourceRef": {"Source": "t"}},
                                "Property": measure_name
                            },
                            "Name": f"{table_name}.{measure_name}"
                        }
                    ]
                },
                "vcObjects": {
                    "title": [
                        {
                            "properties": {
                                "show": {"expr": {"literal": {"value": True}}},
                                "text": {"expr": {"literal": {"value": title_text}}}
                            }
                        }
                    ]
                }
            }
        }

        return {
            "x": x,
            "y": y,
            "z": z,
            "width": w,
            "height": h,
            "config": json.dumps(config)
        }

    def _build_chart_container(
        self,
        chart: Dict[str, Any],
        table_name: str,
        x: int,
        y: int,
        w: int,
        h: int,
        z: int,
        forced_type: str = None,
        available_columns: List[str] = None,
        available_measures: List[str] = None
    ) -> Dict[str, Any]:
        chart_type_raw = str(chart.get("type") or "").lower()
        title_text = str(chart.get("title") or "Analysis")
        title_text = re.sub(r"\s+by\s+(\b\w+\b)(?:\s+by\s+\1)+", r" by \1", title_text, flags=re.IGNORECASE).strip()

        raw_dimension = chart.get("dimension") or "Category"
        dimension = self._resolve_dimension(raw_dimension, available_columns)

        raw_measure = chart.get("measure") or "Value"
        measure = self._resolve_measure(raw_measure, available_measures)

        dim_lower = (dimension or "").lower()
        title_lower = title_text.lower()

        if forced_type:
            visual_type = forced_type
        elif "trend" in title_lower or "date" in dim_lower or "month" in dim_lower or "year" in dim_lower:
            visual_type = "lineChart"
        elif "donut" in chart_type_raw or "pie" in chart_type_raw or "share" in title_lower:
            visual_type = "donutChart"
        elif "bar" in chart_type_raw:
            visual_type = "barChart"
        else:
            visual_type = "clusteredColumnChart"

        visual_name = self._generate_guid()

        config = {
            "name": visual_name,
            "singleVisual": {
                "visualType": visual_type,
                "projections": {
                    "Category": [
                        {"queryRef": f"{table_name}.{dimension}"}
                    ],
                    "Y": [
                        {"queryRef": f"{table_name}.{measure}"}
                    ]
                },
                "prototypeQuery": {
                    "Version": 2,
                    "From": [{"Name": "t", "Entity": table_name, "Type": 0}],
                    "Select": [
                        {
                            "Column": {
                                "Expression": {"SourceRef": {"Source": "t"}},
                                "Property": dimension
                            },
                            "Name": f"{table_name}.{dimension}"
                        },
                        {
                            "Measure": {
                                "Expression": {"SourceRef": {"Source": "t"}},
                                "Property": measure
                            },
                            "Name": f"{table_name}.{measure}"
                        }
                    ]
                },
                "vcObjects": {
                    "title": [
                        {
                            "properties": {
                                "show": {"expr": {"literal": {"value": True}}},
                                "text": {"expr": {"literal": {"value": title_text}}}
                            }
                        }
                    ]
                }
            }
        }

        return {
            "x": x,
            "y": y,
            "z": z,
            "width": w,
            "height": h,
            "config": json.dumps(config)
        }

    # ------------------------------------------------------------------
    # Layout assembly
    # ------------------------------------------------------------------
    def generate_layout(
        self,
        domain_title: str,
        table_name: str,
        visuals: List[Dict[str, Any]],
        available_columns: List[str] = None,
        available_measures: List[str] = None,
        subtitle: Optional[str] = None,
    ) -> Dict[str, Any]:
        containers: List[Dict[str, Any]] = []
        content_width = self.canvas_width - (2 * self.margin)

        cards = [v for v in visuals if any(k in str(v.get("type", "")).lower() for k in ["card", "kpi", "metric", "single"])]
        charts = [v for v in visuals if not any(k in str(v.get("type", "")).lower() for k in ["card", "kpi", "metric", "single"])]
        usable_cards = cards[:4] if cards else []

        # ---------------- Tier 1: Top KPI Cards (Y = 30, H = 100) ----------------
        num_cards = len(usable_cards) if usable_cards else 1
        card_w = int((content_width - (num_cards - 1) * self.gap) / num_cards)

        for i, card in enumerate(usable_cards):
            card_x = self.margin + i * (card_w + self.gap)
            containers.append(
                self._build_card_container(
                    card, table_name, card_x, y=30, w=card_w, h=100, z=1000 + i,
                    available_measures=available_measures
                )
            )

        # ---------------- Tier 2: Middle Row - Primary Visuals (Y = 150, H = 320) ----------------
        if charts:
            primary_chart = charts[0]
            if len(charts) == 1:
                containers.append(
                    self._build_chart_container(
                        primary_chart, table_name,
                        x=self.margin, y=150, w=content_width, h=320, z=2001,
                        available_columns=available_columns,
                        available_measures=available_measures
                    )
                )
            else:
                left_w = int(content_width * 0.59)
                right_w = content_width - left_w - self.gap
                containers.append(
                    self._build_chart_container(
                        primary_chart, table_name,
                        x=self.margin, y=150, w=left_w, h=320, z=2001,
                        available_columns=available_columns,
                        available_measures=available_measures
                    )
                )

                sec_chart = charts[1]
                containers.append(
                    self._build_chart_container(
                        sec_chart, table_name,
                        x=self.margin + left_w + self.gap, y=150, w=right_w, h=320, z=2002,
                        available_columns=available_columns,
                        available_measures=available_measures
                    )
                )

        # ---------------- Tier 3: Bottom Row - Secondary Charts (Y = 490, H = 200) ----------------
        remaining_charts = charts[2:5]
        if remaining_charts:
            num_rem = len(remaining_charts)
            rem_w = int((content_width - (num_rem - 1) * self.gap) / num_rem)
            for i, r_chart in enumerate(remaining_charts):
                rem_x = self.margin + i * (rem_w + self.gap)
                containers.append(
                    self._build_chart_container(
                        r_chart, table_name,
                        x=rem_x, y=490, w=rem_w, h=200, z=3000 + i,
                        available_columns=available_columns,
                        available_measures=available_measures
                    )
                )

        clean_title = (domain_title or "Executive Overview")[:30]

        return {
            "id": 0,
            "themeCollection": {
                "baseTheme": {
                    "name": "CY24SU02",
                    "reportVersionAtImport": "5.55"
                }
            },
            "sections": [
                {
                    "id": 0,
                    "name": "ExecutiveOverview",
                    "displayName": clean_title,
                    "width": self.canvas_width,
                    "height": self.canvas_height,
                    "visualContainers": containers
                }
            ]
        }


if __name__ == "__main__":
    builder = ReportLayoutBuilder()
    layout = builder.generate_layout(
        domain_title="Sales Performance",
        table_name="Sales",
        visuals=[
            {"type": "card", "measure": "TotalRevenue", "title": "Total Revenue"},
            {"type": "card", "measure": "UnitsSold", "title": "Units Sold"},
            {"type": "card", "measure": "GrossMargin", "title": "Gross Margin"},
            {"type": "line", "dimension": "OrderDate", "measure": "TotalRevenue", "title": "Revenue Trend"},
            {"type": "bar", "dimension": "Region", "measure": "TotalRevenue", "title": "Revenue by Region"},
            {"type": "donut", "dimension": "Category", "measure": "TotalRevenue", "title": "Category Share"},
        ],
        available_columns=["OrderDate", "Region", "Category"],
        available_measures=["TotalRevenue", "UnitsSold", "GrossMargin"],
    )
    print(json.dumps(layout, indent=2)[:500])