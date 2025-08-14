import csv, math, os

def load_catalog(path: str):
    """Load the GPU catalog and optionally merge Azure-provided data.

    If a sibling file named ``gpu_catalog_from_azure.csv`` exists, its
    contents are merged into the primary catalog. Rows from the Azure file
    override entries with the same ``gpu_model`` found in the base catalog.
    """

    def read_csv(p):
        data = {}
        with open(p, newline="") as f:
            r = csv.DictReader(f)
            for row in r:
                data[row["gpu_model"]] = {
                    "gpu_model": row["gpu_model"],
                    "vram_gb": float(row["vram_gb"]),
                    "tflops_fp16": float(row["tflops_fp16"]),
                    "rates": {
                        "on_demand": float(row["on_demand_usd_per_hour"]),
                        "spot": float(row["spot_usd_per_hour"]),
                        "reserved": float(row["reserved_usd_per_hour"]),
                    },
                    "tdp_watts": float(row["tdp_watts"]),
                }
        return data

    out = read_csv(path)
    azure_path = os.path.join(os.path.dirname(path), "gpu_catalog_from_azure.csv")
    if os.path.exists(azure_path):
        out.update(read_csv(azure_path))
    return out

def choose_rate(catalog_row, price_tier: str):
    tier = price_tier.lower()
    if tier not in catalog_row["rates"]:
        raise ValueError(f"Unknown price_tier '{price_tier}'. Use one of: {list(catalog_row['rates'].keys())}")
    return catalog_row["rates"][tier]

def training_estimate(
    catalog: dict,
    gpu_model: str,
    model_params_b: float,
    tokens_b: float,
    num_gpus: int | None = None,
    target_time_days: float | None = None,
    efficiency: float = 0.30,         # fraction of theoretical TFLOPS you achieve
    utilization: float = 0.85,        # fraction of wall clock used productively
    price_tier: str = "on_demand",
    energy_cost_per_kwh: float = 0.12,
    tdp_factor: float = 0.70,         # average power as a fraction of TDP
):
    if gpu_model not in catalog:
        raise ValueError(f"gpu_model '{gpu_model}' not in catalog. Available: {list(catalog.keys())}")
    row = catalog[gpu_model]

    # Compute demand: FLOPs ≈ 6 × params × tokens (Chinchilla-style approximation)
    params = model_params_b * 1e9
    tokens = tokens_b * 1e9
    total_flops = 6.0 * params * tokens  # FLOPs

    # Supply per GPU
    tflops_theoretical = row["tflops_fp16"]  # TFLOPS at FP16/BF16 class
    tflops_effective = tflops_theoretical * efficiency  # TFLOPS
    # raw_time_hours: total_flops / (num_gpus * TFLOPS * 1e12)  then to hours
    def time_hours_for(num):
        if tflops_effective <= 0:
            raise ValueError("efficiency must yield >0 effective TFLOPS")
        raw = total_flops / (num * tflops_effective * 1e12) / 3600.0
        # utilization <1 means more wall-clock to finish
        return raw / max(min(utilization, 1.0), 1e-6)

    # If target_time_days given and num_gpus not, derive num_gpus
    derived = False
    if num_gpus is None and target_time_days is not None:
        target_hours = max(target_time_days, 1e-6) * 24.0
        # num_gpus >= total_flops / (tflops_effective*1e12*3600*target_hours*utilization)
        need = total_flops / (tflops_effective * 1e12 * 3600.0 * target_hours * max(min(utilization,1.0),1e-6))
        num_gpus = max(1, math.ceil(need))
        derived = True
    if num_gpus is None:
        num_gpus = 1

    wall_hours = time_hours_for(num_gpus)
    rate_per_gpu = choose_rate(row, price_tier)

    # Compute cost: billable = wall-clock hours on N GPUs (includes idle headroom via utilization)
    compute_cost = wall_hours * num_gpus * rate_per_gpu

    # Energy (useful for on-prem / sustainability views)
    avg_watts = row["tdp_watts"] * tdp_factor
    energy_kwh = (avg_watts * num_gpus * wall_hours) / 1000.0
    energy_cost = energy_kwh * energy_cost_per_kwh

    return {
        "inputs": {
            "gpu_model": gpu_model,
            "model_params_b": model_params_b,
            "tokens_b": tokens_b,
            "num_gpus": num_gpus,
            "derived_num_gpus": derived,
            "target_time_days": target_time_days,
            "efficiency": efficiency,
            "utilization": utilization,
            "price_tier": price_tier,
            "energy_cost_per_kwh": energy_cost_per_kwh,
            "tdp_factor": tdp_factor,
        },
        "catalog_row": row,
        "results": {
            "total_flops": total_flops,
            "effective_tflops_per_gpu": tflops_effective,
            "wall_time_hours": wall_hours,
            "rate_per_gpu_usd_per_hour": rate_per_gpu,
            "compute_cost_usd": compute_cost,
            "energy_kwh": energy_kwh,
            "energy_cost_usd": energy_cost,
            "total_cost_usd": compute_cost + energy_cost,  # for on-prem accounting; cloud cost excludes energy
        },
        "notes": [
            "FLOPs approximation: ~6 * params * tokens (dense transformer order-of-magnitude).",
            "efficiency models kernel/comm overhead; utilization models non-productive wall-clock.",
            "Prices and perf are illustrative defaults; update app/data/gpu_catalog.csv with your quotes.",
        ],
    }
