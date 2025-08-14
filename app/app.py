from flask import Flask, request, jsonify
from estimator import load_catalog, training_estimate

app = Flask(__name__)
CATALOG = load_catalog("data/gpu_catalog.csv")  # merges Azure CSV if present

@app.route("/")
def root():
    return "Hello, the secure AI service is up!"

# Simple legacy estimator (kept for convenience)
@app.route("/estimate")
def simple_estimate():
    try:
        nodes = int(request.args.get("nodes", 1))
        hours = int(request.args.get("hours", 1))
    except ValueError:
        return jsonify({"error": "Invalid input. 'nodes' and 'hours' must be integers."}), 400
    return jsonify({"nodes": nodes, "hours": hours, "estimated_cost_usd": nodes * hours * 10})

@app.route("/catalog")
def catalog():
    return jsonify({"gpus": list(CATALOG.values())})

@app.route("/estimate/training", methods=["POST", "GET"])
def estimate_training_ep():
    payload = request.get_json(silent=True) or {}
    qp = request.args or {}

    def g(name, default=None, cast=float):
        if name in payload: return cast(payload[name])
        if name in qp and qp.get(name) is not None: return cast(qp.get(name))
        return default

    gpu_model          = g("gpu_model", "H100-80GB", str)
    model_params_b     = g("model_params_b", 7.0)
    tokens_b           = g("tokens_b", 1.0)
    num_gpus           = g("num_gpus", None, int)
    target_time_days   = g("target_time_days", None)
    efficiency         = g("efficiency", 0.30)
    utilization        = g("utilization", 0.85)
    price_tier         = (g("price_tier", "on_demand", str) or "on_demand").lower()
    energy_cost_per_kwh= g("energy_cost_per_kwh", 0.12)
    tdp_factor         = g("tdp_factor", 0.70)

    try:
        result = training_estimate(
            CATALOG, gpu_model, model_params_b, tokens_b,
            num_gpus=num_gpus, target_time_days=target_time_days,
            efficiency=efficiency, utilization=utilization,
            price_tier=price_tier, energy_cost_per_kwh=energy_cost_per_kwh,
            tdp_factor=tdp_factor,
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/estimate/training-grid", methods=["POST"])
def estimate_training_grid():
    data = request.get_json(force=True)
    gpu_models         = data.get("gpu_models") or ["H100-80GB"]
    num_gpus_list      = data.get("num_gpus_list") or [1, 2, 4, 8]
    model_params_b     = float(data.get("model_params_b", 7.0))
    tokens_b           = float(data.get("tokens_b", 1.0))
    efficiency         = float(data.get("efficiency", 0.30))
    utilization        = float(data.get("utilization", 0.85))
    price_tier         = str(data.get("price_tier", "on_demand")).lower()
    energy_cost_per_kwh= float(data.get("energy_cost_per_kwh", 0.12))
    tdp_factor         = float(data.get("tdp_factor", 0.70))

    rows = []
    for m in gpu_models:
        for n in num_gpus_list:
            try:
                r = training_estimate(
                    CATALOG, m, model_params_b, tokens_b,
                    num_gpus=int(n), target_time_days=None,
                    efficiency=efficiency, utilization=utilization,
                    price_tier=price_tier, energy_cost_per_kwh=energy_cost_per_kwh,
                    tdp_factor=tdp_factor,
                )
                rows.append({
                    "gpu_model": m,
                    "num_gpus": int(n),
                    "wall_time_hours": r["results"]["wall_time_hours"],
                    "compute_cost_usd": r["results"]["compute_cost_usd"],
                    "total_cost_usd": r["results"]["total_cost_usd"],
                })
            except Exception as e:
                rows.append({"gpu_model": m, "num_gpus": int(n), "error": str(e)})
    return jsonify({"grid": rows})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
