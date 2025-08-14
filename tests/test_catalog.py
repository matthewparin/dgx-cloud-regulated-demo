import os
import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1] / "app"))
from estimator import load_catalog


def write_csv(path, rows):
    with open(path, 'w') as f:
        f.write('gpu_model,vram_gb,tflops_fp16,on_demand_usd_per_hour,spot_usd_per_hour,reserved_usd_per_hour,tdp_watts\n')
        for r in rows:
            f.write(','.join(map(str, r)) + '\n')


def test_load_catalog_single_file(tmp_path):
    rows = [
        ('H100-80GB', 80, 800, 6.5, 3.9, 5.0, 350),
    ]
    csv_path = tmp_path / 'gpu_catalog.csv'
    write_csv(csv_path, rows)

    catalog = load_catalog(str(csv_path))
    assert 'H100-80GB' in catalog
    assert catalog['H100-80GB']['vram_gb'] == 80


def test_load_catalog_merge_azure(tmp_path):
    base_rows = [
        ('H100-80GB', 80, 800, 6.5, 3.9, 5.0, 350),
    ]
    azure_rows = [
        ('H100-80GB', 80, 800, 7.0, 4.0, 5.5, 350),
        ('A100-80GB', 80, 312, 4.1, 2.5, 3.2, 300),
    ]
    write_csv(tmp_path / 'gpu_catalog.csv', base_rows)
    write_csv(tmp_path / 'gpu_catalog_from_azure.csv', azure_rows)

    catalog = load_catalog(str(tmp_path / 'gpu_catalog.csv'))

    assert catalog['H100-80GB']['rates']['on_demand'] == 7.0
    assert 'A100-80GB' in catalog
