"""Evidence-backed insights.

An insight may only repeat what a metric already proved. It never invents a
number and never approves data that failed a rule.
"""

from __future__ import annotations

import json

SEVERITIES = ("info", "watch", "action")
_OPERATORS = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


def _format(template: str, context: dict) -> str:
    try:
        return template.format(**context)
    except (KeyError, IndexError, ValueError):
        return template


def evaluate(config, payloads: list[dict], run_summary: dict, analytics: dict | None = None) -> list[dict]:
    """Apply the project's insight rules plus the built-in data-health rules."""

    values = {p["id"]: p.get("value") for p in payloads if p.get("kind") == "kpi"}
    results: list[dict] = []

    for rule in config.insights:
        condition = rule.get("when", {})
        metric_id = condition.get("metric")
        operator = condition.get("operator", ">")
        threshold = condition.get("value")
        actual = values.get(metric_id)
        if actual is None or metric_id not in values:
            continue
        compare = _OPERATORS.get(operator)
        if compare is None:
            continue
        try:
            triggered = compare(float(actual), float(threshold))
        except (TypeError, ValueError):
            triggered = compare(str(actual), str(threshold))
        if not triggered:
            continue
        context = {"value": actual, "threshold": threshold, **values}
        results.append({
            "id": rule.get("id", metric_id),
            "severity": rule.get("severity", "watch"),
            "title": _format(rule.get("title", metric_id), context),
            "body": _format(rule.get("body", ""), context),
            "evidence": {"metric": metric_id, "value": actual, "operator": operator,
                         "threshold": threshold},
        })

    rejected = run_summary.get("rows_rejected", 0)
    if rejected:
        results.append({
            "id": "rows_need_attention",
            "severity": "action",
            "title": f"{rejected} row(s) were not used",
            "body": ("These rows did not pass the agreed rules. They are listed under "
                     "'Rows needing attention' with the file name and row number."),
            "evidence": {"rows_rejected": rejected},
        })
    blocked = [c for c in run_summary.get("reconciliation", []) if c.get("status") == "BLOCK"]
    if blocked:
        results.append({
            "id": "totals_do_not_match",
            "severity": "action",
            "title": "Totals did not match",
            "body": "The result was not published because a control total did not reconcile.",
            "evidence": {"checks": blocked},
        })

    results.extend(_automatic_analytics_insights(analytics))
    # Keep the decision panel concise. Configured/action insights come first;
    # automatic context fills the remaining slots.
    unique = []
    seen = set()
    for item in results:
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        unique.append(item)
    return unique[:14]



def _automatic_analytics_insights(analytics: dict | None) -> list[dict]:
    """Derive decision signals from the verified analytical cube only.

    The rules intentionally describe *what changed*, concentration and unusual
    movement.  They never invent a root cause or recommendation that is not in
    the data.
    """

    import statistics

    if not analytics or not analytics.get("cells") or not analytics.get("measures"):
        return []
    periods = list(analytics.get("periods") or [])
    dimensions = list(analytics.get("dimensions") or [])
    additive = list(analytics.get("additive") or [])
    measures_list = list(analytics.get("measures") or [])
    measures = {m["id"]: m for m in measures_list}
    add_index = {mid: i for i, mid in enumerate(additive)}

    def totals(cells):
        sums = {mid: 0.0 for mid in additive}
        for cell in cells:
            for mid, index in add_index.items():
                sums[mid] += float(cell["m"][index] or 0)
        for mid, measure in measures.items():
            if measure.get("aggregate") == "ratio":
                den = sums.get(measure.get("denominator"), 0)
                sums[mid] = (sums.get(measure.get("numerator"), 0) / den) if den else None
        return sums

    def period_value(period, metric_id):
        return totals([c for c in analytics["cells"] if c["p"] == period]).get(metric_id)

    out: list[dict] = []
    primary = next((m for m in measures_list
                    if m.get("id") in analytics.get("kpis", []) and m.get("aggregate") != "count"),
                   measures_list[0] if measures_list else None)
    if not primary:
        return out
    metric_id = primary["id"]
    metric_title = primary.get("title", metric_id)
    goal = primary.get("goal_direction", "up")

    # Latest period movement.
    if len(periods) >= 2:
        current_period, prior_period = periods[-1], periods[-2]
        current = period_value(current_period, metric_id)
        prior = period_value(prior_period, metric_id)
        if current is not None and prior not in (None, 0):
            change = (float(current) - float(prior)) / abs(float(prior)) * 100
            direction = "increased" if change >= 0 else "decreased"
            good = (change >= 0 and goal == "up") or (change <= 0 and goal == "down")
            out.append({
                "id": f"auto_period_change_{metric_id}",
                "severity": "info" if good else "watch",
                "title": f"{metric_title} {direction} {abs(change):.1f}%",
                "body": f"Latest period {current_period} versus {prior_period}. The movement is verified; its cause requires investigation.",
                "evidence": {"type": "period_change", "metric": metric_id, "current_period": current_period,
                             "previous_period": prior_period, "current": current, "previous": prior,
                             "change_percent": round(change, 2), "goal_direction": goal},
            })

    # Robust latest-period anomaly versus historical baseline. Median/MAD is
    # deliberately used instead of mean/std-dev so one earlier outlier does not
    # make the detector blind to another one.
    if len(periods) >= 5:
        values = [period_value(period, metric_id) for period in periods]
        numeric = [float(v) for v in values[:-1] if v is not None]
        latest = values[-1]
        if latest is not None and len(numeric) >= 4:
            median = statistics.median(numeric)
            deviations = [abs(v - median) for v in numeric]
            mad = statistics.median(deviations)
            if mad > 0:
                robust_z = 0.6745 * (float(latest) - median) / mad
                if abs(robust_z) >= 3.5:
                    out.append({
                        "id": f"auto_anomaly_{metric_id}",
                        "severity": "watch",
                        "title": f"{metric_title} is unusually far from its recent pattern",
                        "body": f"The latest period differs materially from the historical median. Treat this as an investigation signal, not a root-cause conclusion.",
                        "evidence": {"type": "robust_anomaly", "metric": metric_id, "period": periods[-1],
                                     "value": latest, "baseline_median": round(median, 6),
                                     "robust_z": round(robust_z, 2)},
                    })

    # Trend reversal: the latest direction flips after a prior move.
    if len(periods) >= 3:
        a, b, c = [period_value(period, metric_id) for period in periods[-3:]]
        if None not in (a, b, c):
            first = float(b) - float(a)
            second = float(c) - float(b)
            if first and second and (first > 0) != (second > 0):
                out.append({
                    "id": f"auto_reversal_{metric_id}",
                    "severity": "watch",
                    "title": f"{metric_title} changed direction",
                    "body": f"The latest movement reversed the direction seen in the previous period. This is a verified pattern change worth reviewing.",
                    "evidence": {"type": "trend_reversal", "metric": metric_id,
                                 "periods": periods[-3:], "values": [a, b, c]},
                })

    # Concentration + top three share for the first dimensions.
    if metric_id in add_index:
        latest_period = periods[-1] if periods else None
        latest_cells = [c for c in analytics["cells"] if not latest_period or c["p"] == latest_period]
        for d_index, dimension in enumerate(dimensions[:2]):
            labels = dimension.get("values", [])
            buckets = [0.0 for _ in labels]
            for cell in latest_cells:
                if d_index >= len(cell.get("k", [])):
                    continue
                idx = cell["k"][d_index]
                if 0 <= idx < len(buckets):
                    buckets[idx] += float(cell["m"][add_index[metric_id]] or 0)
            total = sum(buckets)
            if not total or not labels:
                continue
            order = sorted(range(len(buckets)), key=lambda i: buckets[i], reverse=True)
            top = order[0]
            share = buckets[top] / total * 100
            top3 = sum(buckets[i] for i in order[:3]) / total * 100
            out.append({
                "id": f"auto_top_{dimension.get('id')}_{metric_id}",
                "severity": "watch" if share >= 60 or top3 >= 85 else "info",
                "title": f"{labels[top]} is the largest {dimension.get('title', 'segment')}",
                "body": f"It contributes {share:.1f}% of {metric_title.lower()} in the latest period; the top three contribute {top3:.1f}%.",
                "evidence": {"type": "concentration", "metric": metric_id, "dimension": dimension.get("id"),
                             "member": labels[top], "value": buckets[top], "share_percent": round(share, 2),
                             "top3_share_percent": round(top3, 2), "period": latest_period},
            })

    # Biggest positive and negative member movements, not merely absolute change.
    if len(periods) >= 2 and metric_id in add_index:
        for d_index, dimension in enumerate(dimensions[:2]):
            labels = dimension.get("values", [])
            if not labels:
                continue
            previous, latest = periods[-2], periods[-1]
            by_period = {previous: [0.0] * len(labels), latest: [0.0] * len(labels)}
            for cell in analytics["cells"]:
                if cell["p"] not in by_period or d_index >= len(cell.get("k", [])):
                    continue
                idx = cell["k"][d_index]
                if 0 <= idx < len(labels):
                    by_period[cell["p"]][idx] += float(cell["m"][add_index[metric_id]] or 0)
            changes = [by_period[latest][i] - by_period[previous][i] for i in range(len(labels))]
            if not changes or not any(value != 0 for value in changes):
                continue
            gain_idx = max(range(len(changes)), key=lambda i: changes[i])
            loss_idx = min(range(len(changes)), key=lambda i: changes[i])
            if changes[gain_idx] > 0:
                out.append({
                    "id": f"auto_gainer_{dimension.get('id')}_{metric_id}",
                    "severity": "info" if goal == "up" else "watch",
                    "title": f"Largest increase: {labels[gain_idx]}",
                    "body": f"{metric_title} increased by {changes[gain_idx]:+,.2f} versus the previous period for this {dimension.get('title', 'group').lower()}.",
                    "evidence": {"type": "mover", "direction": "increase", "metric": metric_id,
                                 "dimension": dimension.get("id"), "member": labels[gain_idx],
                                 "change": changes[gain_idx], "current_period": latest, "previous_period": previous},
                })
            if changes[loss_idx] < 0:
                out.append({
                    "id": f"auto_decliner_{dimension.get('id')}_{metric_id}",
                    "severity": "watch" if goal == "up" else "info",
                    "title": f"Largest decrease: {labels[loss_idx]}",
                    "body": f"{metric_title} decreased by {abs(changes[loss_idx]):,.2f} versus the previous period for this {dimension.get('title', 'group').lower()}.",
                    "evidence": {"type": "mover", "direction": "decrease", "metric": metric_id,
                                 "dimension": dimension.get("id"), "member": labels[loss_idx],
                                 "change": changes[loss_idx], "current_period": latest, "previous_period": previous},
                })
    return out

def save(connection, run_id: str, results: list[dict]) -> None:
    connection.executemany(
        "INSERT OR REPLACE INTO insights(run_id, insight_id, severity, title, body, evidence_json)"
        " VALUES (?,?,?,?,?,?)",
        [(run_id, r["id"], r.get("severity", "info"), r.get("title", ""), r.get("body", ""),
          json.dumps(r.get("evidence", {}), ensure_ascii=False, default=str)) for r in results])
