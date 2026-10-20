"""E-commerce Analytics Dashboard (Dash / Plotly).

A professional business-intelligence view over the loaded analytics database.
Run it with:

    python dashboard/app.py

then open the printed URL (default http://127.0.0.1:8050).
"""
from __future__ import annotations

import sys
from pathlib import Path

import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Input, Output, State, dcc, html

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dashboard import data as data_layer             # noqa: E402
from src.utils.logging import setup_logging          # noqa: E402

ACCENT = "#1f4e79"
GREY = "#6c757d"
BG = "#f5f7fa"


# ---------------------------------------------------------------------------
# Reusable formatting helpers
# ---------------------------------------------------------------------------
def _fmt_usd(v: float) -> str:
    return f"${v:,.0f}"


def _fmt_int(v) -> str:
    return f"{int(v):,}"


def _card(title: str, value: str, sub: str = "", value_id: str | None = None) -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.Div(title, className="kpi-label"),
                html.Div(value, className="kpi-value", id=value_id),
                html.Div(sub, className="kpi-sub"),
            ]
        ),
        className="kpi-card",
    )


# ---------------------------------------------------------------------------
# App scaffold
# ---------------------------------------------------------------------------
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
app.title = "E-commerce Sales Analytics"

# Seed the dashboards with the full (unfiltered) analytics datasets.
_kpis = data_layer.kpis().iloc[0]
_monthly = data_layer.revenue_by_month()
_products = data_layer.top_products(limit=10)
_categories = data_layer.revenue_by_category()
_regions = data_layer.revenue_by_region()
_segments = data_layer.segments()
_txn = data_layer.transaction_table()

_region_options = ["All"]
_region_options += sorted(_regions["region"].dropna().unique().tolist())
_category_options = ["All"]
_category_options += sorted(_categories["category"].unique().tolist())

app.layout = dbc.Container(
    fluid=True,
    className="dash-container",
    children=[
        # ---- header ------------------------------------------------------
        dbc.Row(
            dbc.Col(
                html.Div(
                    [
                        html.H1("E-commerce Sales Analytics", className="title"),
                        html.P(
                            "Executive business dashboard — automated by the ETL "
                            "pipeline (PostgreSQL / SQLite)", className="subtitle"
                        ),
                    ],
                    className="header",
                )
            )
        ),
        # ---- KPI cards ---------------------------------------------------
        dbc.Row(
            [
                dbc.Col(
                    _card(
                        "Total Revenue",
                        _fmt_usd(_kpis["total_revenue"]),
                        "completed + shipped orders",
                        value_id="kpi-revenue",
                    ),
                    md=3, sm=6,
                ),
                dbc.Col(
                    _card("Total Orders", _fmt_int(_kpis["total_orders"]),
                          f"{_fmt_int(_kpis['units_sold'])} units sold",
                          value_id="kpi-orders"),
                    md=3, sm=6,
                ),
                dbc.Col(
                    _card("Avg Order Value", _fmt_usd(_kpis["average_order_value"]),
                          value_id="kpi-aov"),
                    md=3, sm=6,
                ),
                dbc.Col(
                    _card("Units Sold", _fmt_int(_kpis["units_sold"]),
                          value_id="kpi-units"),
                    md=3, sm=6,
                ),
            ],
            className="mb-3",
        ),
        # ---- filters -----------------------------------------------------
        dbc.Row(
            dbc.Col(
                dbc.Card(
                    dbc.CardBody(
                        dbc.Row(
                            [
                                dbc.Col(
                                    [
                                        html.Label("Region", className="filter-label"),
                                        dcc.Dropdown(
                                            id="region-filter",
                                            options=[{"label": r, "value": r} for r in _region_options],
                                            value="All",
                                            clearable=False,
                                        ),
                                    ],
                                    md=4,
                                ),
                                dbc.Col(
                                    [
                                        html.Label("Category", className="filter-label"),
                                        dcc.Dropdown(
                                            id="category-filter",
                                            options=[{"label": c, "value": c} for c in _category_options],
                                            value="All",
                                            clearable=False,
                                        ),
                                    ],
                                    md=4,
                                ),
                                dbc.Col(
                                    [
                                        html.Label("Date range", className="filter-label"),
                                        dcc.DatePickerRange(
                                            id="date-filter",
                                            min_date_allowed=_monthly["year"].min(),
                                            max_date_allowed=_monthly["year"].max(),
                                            start_date=None,
                                            end_date=None,
                                        ),
                                    ],
                                    md=4,
                                ),
                            ]
                        )
                    )
                )
            )
        ),
        html.Hr(),
        # ---- revenue trend + category ------------------------------------
        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.H5("Revenue Trend (monthly)"),
                                dcc.Graph(id="trend-chart"),
                            ]
                        )
                    ),
                    md=8,
                ),
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.H5("Revenue by Category"),
                                dcc.Graph(id="category-chart"),
                            ]
                        )
                    ),
                    md=4,
                ),
            ],
            className="mb-3",
        ),
        # ---- top products + region ----------------------------------------
        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.H5("Top Products by Revenue"),
                                dcc.Graph(id="product-chart"),
                            ]
                        )
                    ),
                    md=6,
                ),
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.H5("Revenue by Region"),
                                dcc.Graph(id="region-chart"),
                            ]
                        )
                    ),
                    md=6,
                ),
            ],
            className="mb-3",
        ),
        # ---- segments + transaction table ---------------------------------
        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.H5("Customer Segments"),
                                dcc.Graph(id="segment-chart"),
                            ]
                        )
                    ),
                    md=4,
                ),
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.H5("Detailed Transactions"),
                                dbc.Input(
                                    id="txn-search",
                                    placeholder="Search product, customer, or order…",
                                    type="text",
                                    className="mb-2",
                                ),
                                dcc.Loading(
                                    children=[
                                        html.Div(id="txn-table", className="table-scroll")
                                    ]
                                ),
                            ]
                        )
                    ),
                    md=8,
                ),
            ]
        ),
        html.Footer(
            "Data refreshed by pipeline.py — ETL · Data Quality · SQL Analytics",
            className="footer",
        ),
    ],
)


# ---------------------------------------------------------------------------
# Callbacks — every chart and KPI reacts to the region / category / date filters
# ---------------------------------------------------------------------------
def _filters(region, category, start, end) -> data_layer.Filters:
    return data_layer.Filters(
        region=region, category=category, start_date=start, end_date=end
    )


def _kpis_from(df: pd.DataFrame):
    return df.iloc[0]


@app.callback(
    [
        Output("kpi-revenue", "children"),
        Output("kpi-orders", "children"),
        Output("kpi-aov", "children"),
        Output("kpi-units", "children"),
    ],
    [
        Input("region-filter", "value"),
        Input("category-filter", "value"),
        Input("date-filter", "start_date"),
        Input("date-filter", "end_date"),
    ],
)
def update_kpis(region, category, start, end):
    row = _kpis_from(data_layer.kpis(_filters(region, category, start, end)))
    return (
        _fmt_usd(row["total_revenue"]),
        _fmt_int(row["total_orders"]),
        _fmt_usd(row["average_order_value"]),
        _fmt_int(row["units_sold"]),
    )


@app.callback(
    Output("trend-chart", "figure"),
    [
        Input("region-filter", "value"),
        Input("category-filter", "value"),
        Input("date-filter", "start_date"),
        Input("date-filter", "end_date"),
    ],
)
def update_trend(region, category, start, end):
    df = data_layer.revenue_by_month(_filters(region, category, start, end))
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["month_name"] + " " + df["year"].astype(str),
            y=df["revenue"], mode="lines+markers",
            line=dict(color=ACCENT, width=3),
            hovertemplate="%{y:,.0f}<extra></extra>",
        )
    )
    fig.update_layout(
        template="plotly_white", margin=dict(l=10, r=10, t=10, b=10),
        yaxis_tickprefix="$", height=320,
    )
    return fig


@app.callback(
    Output("category-chart", "figure"),
    [
        Input("region-filter", "value"),
        Input("category-filter", "value"),
        Input("date-filter", "start_date"),
        Input("date-filter", "end_date"),
    ],
)
def update_category(region, category, start, end):
    raw = data_layer.revenue_by_category(_filters(region, category, start, end))
    fig = px.bar(
        raw, x="category", y="revenue", color="category",
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.update_traces(showlegend=False)
    fig.update_layout(
        template="plotly_white", margin=dict(l=10, r=10, t=10, b=10),
        yaxis_tickprefix="$", height=260,
    )
    return fig


@app.callback(
    Output("product-chart", "figure"),
    [
        Input("region-filter", "value"),
        Input("category-filter", "value"),
        Input("date-filter", "start_date"),
        Input("date-filter", "end_date"),
    ],
)
def update_products(region, category, start, end):
    df = data_layer.top_products(_filters(region, category, start, end), 10)
    df = df.sort_values("revenue")
    fig = px.bar(
        df, x="revenue", y="product", orientation="h",
        color="revenue", color_continuous_scale="Blues",
    )
    fig.update_traces(showlegend=False)
    fig.update_layout(
        template="plotly_white", margin=dict(l=10, r=10, t=10, b=10),
        xaxis_tickprefix="$", height=420,
    )
    return fig


@app.callback(
    Output("region-chart", "figure"),
    [
        Input("region-filter", "value"),
        Input("category-filter", "value"),
        Input("date-filter", "start_date"),
        Input("date-filter", "end_date"),
    ],
)
def update_region(region, category, start, end):
    df = data_layer.revenue_by_region(_filters(region, category, start, end))
    df = df.sort_values("revenue", ascending=False)
    fig = px.bar(
        df, x="region", y="revenue", color="region",
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.update_traces(showlegend=False)
    fig.update_layout(
        template="plotly_white", margin=dict(l=10, r=10, t=10, b=10),
        yaxis_tickprefix="$", height=360,
    )
    return fig


@app.callback(
    Output("segment-chart", "figure"),
    [
        Input("region-filter", "value"),
        Input("category-filter", "value"),
        Input("date-filter", "start_date"),
        Input("date-filter", "end_date"),
    ],
)
def update_segments(region, category, start, end):
    df = data_layer.segments(_filters(region, category, start, end))
    fig = px.pie(
        df, names="segment", values="revenue", hole=0.45,
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.update_traces(textposition="inside", textinfo="percent")
    fig.update_layout(
        template="plotly_white", margin=dict(l=10, r=10, t=10, b=10),
        height=360, showlegend=True, legend=dict(orientation="h", y=-0.1),
    )
    return fig


@app.callback(
    Output("txn-table", "children"),
    [
        Input("txn-search", "value"),
        Input("region-filter", "value"),
        Input("category-filter", "value"),
        Input("date-filter", "start_date"),
        Input("date-filter", "end_date"),
    ],
)
def update_txn_table(search, region, category, start, end):
    df = data_layer.transaction_table(_filters(region, category, start, end), 500)
    if search:
        s = str(search).strip().lower()
        mask = (
            df["product"].astype(str).str.lower().str.contains(s)
            | df["customer_name"].astype(str).str.lower().str.contains(s)
            | df["order_id"].astype(str).str.lower().str.contains(s)
        )
        df = df[mask]
    table = dbc.Table.from_dataframe(
        df[["order_date", "order_id", "customer_name", "product",
            "category", "quantity", "unit_price", "line_total"]]
        .head(50),
        striped=True, bordered=False, hover=True, responsive=True, size="sm",
    )
    table.className = "table table-sm"
    return html.Div(
        [html.Div(f"{len(df)} transactions", className="small text-muted mb-1")]
        + [table],
        style={"maxHeight": "420px", "overflowY": "auto"},
    )


# ---------------------------------------------------------------------------
# Inline CSS (professional, simple, readable)
# ---------------------------------------------------------------------------
app.index_string = (
    "<!DOCTYPE html>"
    "<html>"
    "<head>"
    "{%metas%}"
    "<title>{%title%}</title>"
    "{%favicon%}"
    "{%css%}"
    "<style>"
    f"body{{background:{BG};font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;}}"
    f".title{{color:{ACCENT};font-weight:700;margin-bottom:2px;}}"
    f".subtitle{{color:{GREY};margin-top:0;}}"
    ".header{padding:16px 4px 8px;}"
    ".kpi-label{font-size:13px;color:" + GREY + ";text-transform:uppercase;letter-spacing:.5px;}"
    ".kpi-value{font-size:28px;font-weight:700;color:" + ACCENT + ";}"
    ".kpi-sub{font-size:12px;color:" + GREY + ";}"
    ".kpi-card{border-radius:12px;border:1px solid #e3e8ef;box-shadow:0 1px 3px rgba(0,0,0,.05);}"
    ".filter-label{font-size:12px;font-weight:600;color:" + GREY + ";text-transform:uppercase;}"
    ".footer{margin-top:28px;padding:14px;text-align:center;color:" + GREY + ";font-size:12px;}"
    "h5{color:" + ACCENT + ";font-weight:600;}"
    "</style>"
    "</head>"
    "<body>{%app_entry%}"
    "<footer>{%config%}{%scripts%}{%renderer%}</footer>"
    "</body>"
    "</html>"
)


if __name__ == "__main__":
    setup_logging()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8050
    print(f"E-commerce Analytics Dashboard starting at http://127.0.0.1:{port}")
    app.run(debug=False, host="0.0.0.0", port=port)
