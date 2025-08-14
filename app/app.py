from flask import Flask, request, jsonify
from estimator import load_catalog, training_estimate
from planner import load_policy, plan_training, policy_check, sign_attestation
import os, time

app = Flask(__name__)
CATALOG = load_catalog("data/gpu_catalog.csv")    # merges gpu_catalog_from_azure.csv if present
POLICY  = load_policy("policy/policy.json")

@app.route("/")
def root():
    return "Hello, the secure AI service is up!"

# Back-compat simple estimator
@app.route("/estimate")
def simple_estimate():
    try:
        nodes = int(request.args.get("nodes", 1))
        hours = int(request.args.get("hours", 1))
    except ValueError:
        return jsonify({"error": "Invalid input. 'nodes' and 'hours' must be integers."}), 400
    cost_per_node_hour = 10
    total_cost = nodes * hours * cost_per_node_hour
    return jsonify({"nodes": nodes, "hours": hours, "estimated_cost_usd": total_cost})

@app.route("/catalog")
def catalog():
    return jsonify({"gpus": list(CATALOG.values())})

# Optimizer: propose N best plans by cost/time (respects target_time_days/budget if provided)
@app.route("/plan/training", methods=["POST"])
def plan_training_ep():
    p = request.get_json(force=True)
    plans = plan_training(
        CATALOG,
        model_params_b=float(p.get("model_params_b", 7.0)),
        tokens_b=float(p.get("tokens_b", 1.0)),
        gpu_models=p.get("gpu_models"),
        num_gpus_list=p.get("num_gpus_list"),
        price_tiers=p.get("price_tiers"),
        target_time_days=p.get("target_time_days"),
        budget_usd=p.get("budget_usd"),
        efficiency=float(p.get("efficiency", 0.30)),
        utilization=float(p.get("utilization", 0.85)),
    )
    return jsonify({"plans": plans})

# Pre-flight policy gate + attestation (HMAC)
@app.route("/submit", methods=["POST"])
def submit_job():
    m = request.get_json(force=True)
    # choose a plan using the optimizer
    plans = plan_training(
        CATALOG,
        model_params_b=float(m.get("model_params_b", 7.0)),
        tokens_b=float(m.get("tokens_b", 1.0)),
        gpu_models=m.get("gpu_models"),
        num_gpus_list=m.get("num_gpus_list"),
        price_tiers=m.get("price_tiers"),
        target_time_days=m.get("target_time_days"),
        budget_usd=m.get("budget_usd"),
        efficiency=float(m.get("efficiency", 0.30)),
        utilization=float(m.get("utilization", 0.85)),
    )
    if not plans:
        return jsonify({"error":"no feasible plan found"}), 400
    best = plans[0]
    violations = policy_check(m, best, POLICY)
    status = "approved" if not violations else "rejected"
    att = {
        "status": status,
        "timestamp": int(time.time()),
        "manifest": m,
        "plan": best,
        "policy_version": "policy/policy.json"
    }
    key = os.getenv("ATTEST_HMAC_KEY")
    if not key:
        return jsonify({"error":"attestation key missing (ATTEST_HMAC_KEY)","attestation":att,"violations":violations}), 500
    signed = sign_attestation(key, att)
    code = 200 if status=="approved" else 400
    return jsonify({**signed, "violations": violations}), code

# Original training estimator (kept for convenience via GET/POST)
@app.route("/estimate/training", methods=["POST","GET"])
def estimate_training():
    payload = request.get_json(silent=True) or {}
    qp = request.args or {}
    def g(name, default=None, cast=float):
        if name in payload: return cast(payload[name])
        if name in qp:      return cast(qp.get(name))
        return default
    gpu_model = g("gpu_model", "H100-80GB", str)
    model_params_b = g("model_params_b", 7.0)
    tokens_b = g("tokens_b", 1.0)
    num_gpus = g("num_gpus", None, int)
    target_time_days = g("target_time_days", None)
    efficiency = g("efficiency", 0.30)
    utilization = g("utilization", 0.85)
    price_tier = (g("price_tier", "on_demand", str) or "on_demand").lower()
    energy_cost_per_kwh = g("energy_cost_per_kwh", 0.12)
    tdp_factor = g("tdp_factor", 0.70)
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
