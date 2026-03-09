---
name: strategist
description: Generates high-impact PESTEL-EL business questions for Fendt and tasks the agent team to solve them.
---
# Strategist Skill
Whenever the user asks for "On-demand insights" or a "Daily update":
1. **Context Check**: Look at the latest entries in `data/graph.json` to see what information is missing or outdated.
2. **Question Formulation**: Create a "Triple-Thread" question that links 3 PESTEL pillars (e.g., Economic price of wheat + Technological engine efficiency + Legal Data Act).
3. **Tasking**: Automatically trigger the `Scout` to find specific numbers (like "4.1% rise") and the `Analyst` to score them.