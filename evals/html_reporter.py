from pathlib import Path
from evals.schemas import DatasetEvaluationResult, MetricStatus


def export_html_report(result: DatasetEvaluationResult, output_path: str | Path) -> None:
    """
    Generates a beautiful, responsive, and standalone static HTML report from
    a DatasetEvaluationResult. Includes styling for readability and visual appeal.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Gather stats
    stats = result.evaluation_statistics
    status = result.overall_completion_status
    manifest = result.run_manifest

    # Determine status color
    status_bg = "#1b5e20" if status == "completed" else "#b71c1c" if status == "failed" else "#e65100"
    status_txt = "#ffffff"

    # 2. Build rows for metric summaries
    metric_rows = ""
    for name in sorted(result.metric_summaries.keys()):
        m = result.metric_summaries[name]
        mean_val = f"{m.mean_value:.4f}" if m.mean_value is not None else "N/A"
        min_val = f"{m.min_value:.4f}" if m.min_value is not None else "N/A"
        max_val = f"{m.max_value:.4f}" if m.max_value is not None else "N/A"
        med_val = f"{m.median_value:.4f}" if m.median_value is not None else "N/A"
        
        metric_rows += f"""
        <tr>
            <td><strong>{m.metric_name}</strong></td>
            <td>{m.total_count}</td>
            <td style="color: #4caf50;">{m.success_count}</td>
            <td style="color: #ff9800;">{m.na_count}</td>
            <td style="color: #f44336;">{m.failed_count}</td>
            <td>{min_val}</td>
            <td>{max_val}</td>
            <td>{mean_val}</td>
            <td>{med_val}</td>
        </tr>
        """

    # 3. Build rows for scenario results
    scenario_rows = ""
    for r in result.scenario_results:
        # Determine scenario status
        if not r.errors:
            scn_status = "SUCCESS"
            scn_color = "#4caf50"
        elif len(r.metrics) > 0:
            scn_status = "PARTIAL"
            scn_color = "#ff9800"
        else:
            scn_status = "FAILED"
            scn_color = "#f44336"

        warns = "<br>".join(r.warnings) if r.warnings else "None"
        errs = "<br>".join(r.errors) if r.errors else "None"

        # List metric results for this scenario
        m_details = []
        for m in r.metrics:
            val_str = f"{m.value:.3f}" if m.value is not None else "N/A"
            m_details.append(f"{m.metric_name}: {val_str} ({m.status.value})")
        m_details_str = "<br>".join(m_details) if m_details else "No metrics"

        scenario_rows += f"""
        <tr>
            <td><strong>{r.scenario_id}</strong></td>
            <td style="color: {scn_color}; font-weight: bold;">{scn_status}</td>
            <td>{r.terminal_outcome or 'N/A'}</td>
            <td>{m_details_str}</td>
            <td style="font-size: 0.85em; color: #ff9800;">{warns}</td>
            <td style="font-size: 0.85em; color: #f44336;">{errs}</td>
        </tr>
        """

    # 4. Compile HTML template
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OpsGraph AI — Dataset Evaluation Report</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background-color: #f5f7fa;
            color: #333333;
            margin: 0;
            padding: 0;
        }}
        .container {{
            max-width: 1200px;
            margin: 40px auto;
            padding: 20px;
            background: #ffffff;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.05);
        }}
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid #eaedf0;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}
        h1 {{
            margin: 0;
            font-size: 24px;
            color: #1a1a1a;
        }}
        .status-badge {{
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 14px;
            background-color: {status_bg};
            color: {status_txt};
            text-transform: uppercase;
        }}
        .meta-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .card {{
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            padding: 16px;
        }}
        .card-title {{
            font-size: 12px;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 6px;
        }}
        .card-value {{
            font-size: 20px;
            font-weight: bold;
            color: #0f172a;
        }}
        h2 {{
            font-size: 18px;
            color: #1e293b;
            margin-top: 40px;
            margin-bottom: 16px;
            border-left: 4px solid #3b82f6;
            padding-left: 10px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 30px;
        }}
        th, td {{
            text-align: left;
            padding: 12px 16px;
            border-bottom: 1px solid #e2e8f0;
        }}
        th {{
            background-color: #f1f5f9;
            color: #475569;
            font-weight: 600;
        }}
        tr:hover {{
            background-color: #f8fafc;
        }}
        .footer {{
            text-align: center;
            margin-top: 50px;
            font-size: 12px;
            color: #94a3b8;
            border-top: 1px solid #e2e8f0;
            padding-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>OpsGraph AI — Evaluation Report</h1>
                <small style="color: #64748b;">Run ID: {manifest.run_id} | Version: {manifest.evaluation_version}</small>
            </div>
            <div class="status-badge">{status}</div>
        </header>

        <section>
            <h2>Completion Statistics</h2>
            <div class="meta-grid">
                <div class="card">
                    <div class="card-title">Total Scenarios</div>
                    <div class="card-value">{stats.total_scenarios}</div>
                </div>
                <div class="card">
                    <div class="card-title">Evaluated Scenarios</div>
                    <div class="card-value">{stats.evaluated_scenarios}</div>
                </div>
                <div class="card">
                    <div class="card-title">Successful Evaluations</div>
                    <div class="card-value" style="color: #4caf50;">{stats.successful_evaluations}</div>
                </div>
                <div class="card">
                    <div class="card-title">Partial Evaluations</div>
                    <div class="card-value" style="color: #ff9800;">{stats.partial_evaluations}</div>
                </div>
                <div class="card">
                    <div class="card-title">Failed Evaluations</div>
                    <div class="card-value" style="color: #f44336;">{stats.failed_evaluations}</div>
                </div>
                <div class="card">
                    <div class="card-title">Completion Ratio</div>
                    <div class="card-value">{stats.completion_ratio * 100:.1f}%</div>
                </div>
            </div>
        </section>

        <section>
            <h2>Metric Summaries</h2>
            <table>
                <thead>
                    <tr>
                        <th>Metric Name</th>
                        <th>Total</th>
                        <th>Success</th>
                        <th>N/A</th>
                        <th>Failed</th>
                        <th>Min</th>
                        <th>Max</th>
                        <th>Mean</th>
                        <th>Median</th>
                    </tr>
                </thead>
                <tbody>
                    {metric_rows}
                </tbody>
            </table>
        </section>

        <section>
            <h2>Scenario Results</h2>
            <table>
                <thead>
                    <tr>
                        <th style="width: 120px;">Scenario ID</th>
                        <th style="width: 100px;">Status</th>
                        <th style="width: 150px;">Terminal Outcome</th>
                        <th>Metrics</th>
                        <th>Warnings</th>
                        <th>Errors</th>
                    </tr>
                </thead>
                <tbody>
                    {scenario_rows}
                </tbody>
            </table>
        </section>

        <div class="footer">
            Generated by OpsGraph AI Bounded Evaluation Framework. Mode: {manifest.evaluation_mode.value}
        </div>
    </div>
</body>
</html>
"""

    with open(path, "w", encoding="utf-8") as f:
        f.write(html_content)
