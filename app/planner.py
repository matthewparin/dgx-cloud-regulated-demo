import itertools, json, math, time, hmac, hashlib, base64
from estimator import training_estimate

def load_policy(path="policy/policy.json"):
    with open(path, "r") as f:
        return json.load(f)

def pareto(plans):
    # Non-dominated by (cost asc, time asc)
    out=[]
    for p in plans:
        dominated=False
        for q in plans:
            if q is p: continue
            if (q["results"]["compute_cost_usd"] <= p["results"]["compute_cost_usd"] and
                q["results"]["wall_time_hours"]   <= p["results"]["wall_time_hours"] and
                (q["results"]["compute_cost_usd"] < p["results"]["compute_cost_usd"] or
                 q["results"]["wall_time_hours"]  < p["results"]["wall_time_hours"])):
                dominated=True; break
        if not dominated: out.append(p)
    # sort pretty
    return sorted(out, key=lambda r:(r["results"]["compute_cost_usd"], r["results"]["wall_time_hours"]))

def plan_training(catalog, model_params_b, tokens_b,
                  gpu_models=None, num_gpus_list=None, price_tiers=None,
                  target_time_days=None, budget_usd=None,
                  efficiency=0.30, utilization=0.85):
    gpu_models = gpu_models or list(catalog.keys())
    num_gpus_list = num_gpus_list or [1,2,4,8,16,32,64]
    price_tiers = price_tiers or ["on_demand","reserved","spot"]
    plans=[]
    for gm, n, tier in itertools.product(gpu_models, num_gpus_list, price_tiers):
        try:
            r = training_estimate(
                catalog, gm, model_params_b, tokens_b,
                num_gpus=n, target_time_days=None,
                efficiency=efficiency, utilization=utilization,
                price_tier=tier)
            ok_time = (target_time_days is None) or (r["results"]["wall_time_hours"] <= target_time_days*24.0)
            ok_cost = (budget_usd is None) or (r["results"]["compute_cost_usd"] <= budget_usd)
            r["meta"] = {"meets_time": ok_time, "meets_budget": ok_cost, "gpu_model": gm, "num_gpus": n, "price_tier": tier}
            if ok_time and ok_cost:
                plans.append(r)
            else:
                # keep near-misses too for visibility
                plans.append(r)
        except Exception:
            continue
    if not plans: return []
    # prefer those that satisfy constraints; else show best-effort Pareto
    valids = [p for p in plans if p["meta"]["meets_time"] and p["meta"]["meets_budget"]]
    return pareto(valids or plans)[:10]

def policy_check(manifest, plan, policy):
    v=[]
    cls = (manifest.get("classification") or "").upper()
    region = manifest.get("region","")
    price_tier = plan["meta"]["price_tier"]
    gm = plan["meta"]["gpu_model"]
    n = int(plan["meta"]["num_gpus"])
    budget = float(manifest.get("budget_usd", 9e18))
    # allowed regions
    if region and policy.get("allowed_regions") and region not in policy["allowed_regions"]:
        v.append(f"region '{region}' not in allowed_regions")
    # class rules
    cr = policy.get("class_rules",{}).get(cls,{})
    allow_spot = cr.get("allow_spot", True)
    if price_tier=="spot" and not allow_spot:
        v.append(f"class {cls} forbids spot")
    max_gpus = cr.get("max_gpus")
    if max_gpus and n>max_gpus:
        v.append(f"class {cls} max_gpus={max_gpus}, requested {n}")
    req_pref = cr.get("require_region_prefix")
    if req_pref and not region.startswith(req_pref):
        v.append(f"class {cls} requires region prefix '{req_pref}'")
    # allowlist per class
    allowlist = policy.get("gpu_allowlist_by_class",{}).get(cls)
    if allowlist and gm not in allowlist:
        v.append(f"class {cls} allowlist forbids gpu_model {gm}")
    # global budget
    gmax = policy.get("global",{}).get("max_budget_usd")
    if gmax and budget>gmax:
        v.append(f"budget {budget} exceeds global max_budget_usd {gmax}")
    # plan fits manifest budget/time?
    if "budget_usd" in manifest and plan["results"]["compute_cost_usd"]>budget:
        v.append(f"plan cost {plan['results']['compute_cost_usd']:.2f} exceeds budget {budget:.2f}")
    if "target_time_days" in manifest and plan["results"]["wall_time_hours"]>float(manifest["target_time_days"])*24.0:
        v.append("plan time exceeds target_time_days")
    return v

def b64url(b:bytes)->str:
    return base64.urlsafe_b64encode(b).rstrip(b'=').decode()

def sign_attestation(key:str, attestation:dict)->dict:
    body = json.dumps(attestation, separators=(",",":"), sort_keys=True).encode()
    sig  = hmac.new(key.encode(), body, hashlib.sha256).digest()
    return {"attestation": attestation, "signature": b64url(sig), "alg":"HS256"}
