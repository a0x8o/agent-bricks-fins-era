# Databricks notebook source
# Re-bind the chatbot app's MAS + sub-agent CAN_QUERY resources after a
# bundle-only deploy of chatbot-app/. Layer A (Agent Bricks MAS) only.

# COMMAND ----------

import sys

sys.path.append("..")
from resources.grant_app_mas_permissions import main

# Explicit empty argv: running the script as __main__ would let argparse read the
# notebook kernel's own sys.argv ("-f <kernel.json>") and exit on unknown args.
rc = main([])
if rc:
    raise RuntimeError(f"grant_app_mas_permissions exited {rc}")
