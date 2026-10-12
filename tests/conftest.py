import os

# 离线单测用 fixture，不走 heuristic，也不打外网 LLM
os.environ["PARSE_BACKEND"] = "fixture"
