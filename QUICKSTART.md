# Quick Start Guide: Fendt PESTEL-EL Sentinel

Follow these steps to get the autonomous sentinel running using the Python-native architecture.

---

## 🛠️ Step 1: Environment Setup

1.  **Install Prerequisites**: Ensure you have Python 3.10+ and the Claude Code CLI installed.
2.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

---

## 🔑 Step 2: Claude Code Authentication

Link your Claude Pro subscription to the CLI:

1.  **Login**:
    ```bash
    claude code --login
    ```
2.  **Verify**:
    ```bash
    claude auth status
    ```
    *See [authentication.md](authentication.md) for detailed help.*

---

## 🤖 Step 3: Running the Sentinel

The **Sentinel Orchestrator** replaces the previous n8n setup with a more stable, robust Python pipeline.

### Manual One-Time Run
Run the full chain (Scout -> Analyst -> Critic -> Writer):
```bash
python sentinel.py --run-once
```

### Autonomous Scheduled Run
Keep the terminal open to run the pipeline automatically every 24 hours:
```bash
python sentinel.py --autonomous 24
```

---

## 📊 Step 4: Monitoring via Dashboard

Launch the premium Streamlit dashboard to visualize the Knowledge Graph and monitor agent status.

1.  **Start Dashboard**:
    ```bash
    streamlit run dashboard.py
    ```
2.  **Access**: Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## 📂 Data & Monitoring

*   **Knowledge Graph**: Check `./data/graph.json`.
*   **System Logs**: See `./logs/sentinel.log` for execution details.
*   **Strategic Briefs**: Read generated reports in `./output/briefs/*.md`.

---

## ⚡ Quick Reference Table

| Goal | Command |
| :--- | :--- |
| **Run Pipeline** | `python sentinel.py --run-once` |
| **Start UI** | `streamlit run dashboard.py` |
| **Reset Auth** | `claude code --logout` then `--login` |
| **Run Single Agent** | `python sentinel.py --agent scout` |

---

## 🆘 Troubleshooting
- **Claude Not Found**: Install via `npm install -g @anthropic-ai/claude-code`.
- **Import Error**: Re-run `pip install -r requirements.txt`.
- **Access Error**: Ensure you have write permissions to the `/data` and `/logs` folders.
