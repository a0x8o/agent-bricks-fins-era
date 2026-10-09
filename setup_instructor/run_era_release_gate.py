# Databricks notebook source
# ERA release gate. Exit 0 is the contract with a deploy job.
# Runs offline fixtures + conf/release_gate.yaml; no serving endpoint required.

# COMMAND ----------

import sys

sys.path.append("..")

from era.eval import run_eval

code = run_eval.main(["--offline-fixtures", "../era/eval/fixtures.example.json"])
if code != 0:
    raise SystemExit(code)
print("Release gate passed.")
