#!/usr/bin/env python3
import csv, os, re, sys, requests

API = "https://prices.azure.com/api/retail/prices"
REGION = os.getenv("AZURE_REGION", "eastus")  # any Azure armRegionName
OUT = sys.argv[1] if len(sys.argv) > 1 else "app/data/gpu_catalog_from_azure.csv"

# Known GPU counts for common SKUs we’re targeting (from Azure ND series docs)
# ND96… H100 v5 => 8x H100; ND96… A100 v4 => 8x A100 (NVLink).
GPU_COUNT_HINTS = {
  "Standard_ND96isr_H100_v5": 8,
  "Standard_ND96iasr_H100_v5": 8,
  "Standard_ND96amsr_A100_v4": 8,
  "Standard_ND96asr_A100_v4": 8,
}

def fetch_items(q):
  url = API
  items = []
  while True:
    r = requests.get(url, params={'$filter': q}) if 'prices?' in url else requests.get(url)
    r.raise_for_status()
    data = r.json()
    items.extend(data.get("Items", []))
    nxt = data.get("NextPageLink")
    if not nxt: break
    url = nxt
  return items

def guess_gpus(arm_sku, product_name, meter_name):
  if arm_sku in GPU_COUNT_HINTS: return GPU_COUNT_HINTS[arm_sku]
  # Try to parse counts like "8x A100" from names if present
  txt = " ".join([arm_sku or "", product_name or "", meter_name or ""])
  m = re.search(r'(\d+)\s*[xX]\s*(A100|H100)', txt)
  if m: return int(m.group(1))
  # Conservative fallback: assume 1 GPU
  return 1

def main():
  # Filter: Virtual Machines, on-demand ("Consumption"), region, and meterName mentioning H100/A100
  base = f"serviceName eq 'Virtual Machines' and priceType eq 'Consumption' and armRegionName eq '{REGION}'"
  q_h100 = base + " and contains(meterName, 'H100')"
  q_a100 = base + " and contains(meterName, 'A100')"
  rows = []
  for q in (q_h100, q_a100):
    for it in fetch_items(q):
      sku = it.get("armSkuName")
      prod = it.get("productName","")
      meter = it.get("meterName","")
      price = float(it.get("retailPrice", 0.0) or 0.0)
      if price <= 0: continue
      gpus = guess_gpus(sku, prod, meter)
      per_gpu = price / max(gpus,1)

      # Normalize to your catalog schema
      if "H100" in (meter + prod + sku):
        model, vram, tflops, tdp = "H100-80GB", 80, 1979, 350  # FP16 TFLOPS, TDP ~350W
      elif "A100" in (meter + prod + sku):
        model, vram, tflops, tdp = "A100-80GB", 80, 312, 300   # FP16 TFLOPS, TDP ~300W
      else:
        continue

      rows.append({
        "gpu_model": model,
        "vram_gb": vram,
        "tflops_fp16": tflops,
        "on_demand_usd_per_hour": f"{per_gpu:.4f}",
        "spot_usd_per_hour": "",        # Azure Retail API doesn’t expose spot here
        "reserved_usd_per_hour": "",    # savings plans/reserved differ; leave blank
        "tdp_watts": tdp,
      })

  # De-dup by model, keep lowest price seen (regions sometimes list multiple meters)
  best = {}
  for r in rows:
    m = r["gpu_model"]
    p = float(r["on_demand_usd_per_hour"])
    if m not in best or p < float(best[m]["on_demand_usd_per_hour"]):
      best[m] = r

  os.makedirs(os.path.dirname(OUT), exist_ok=True)
  with open(OUT, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["gpu_model","vram_gb","tflops_fp16","on_demand_usd_per_hour","spot_usd_per_hour","reserved_usd_per_hour","tdp_watts"])
    w.writeheader()
    for r in best.values():
      w.writerow(r)

  print(f"Wrote {OUT} with {len(best)} rows for region={REGION}")

if __name__ == "__main__":
  main()
