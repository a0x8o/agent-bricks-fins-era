# Databricks notebook source
# Re-bind the chatbot app's MAS + sub-agent CAN_QUERY resources after a
# bundle-only deploy of chatbot-app/. Layer A (Agent Bricks MAS) only.

# COMMAND ----------

import runpy

runpy.run_path("../resources/grant_app_mas_permissions.py", run_name="__main__")
