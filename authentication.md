# Claude Code Authentication Guide

This document provides a comprehensive guide to authenticating Claude Code within the Innovation Radar (Fendt PESTEL-EL Sentinel) project environment.

---

## 🔐 Authentication Overview

The Fendt PESTEL-EL Sentinel uses **Claude Code**, an agentic CLI from Anthropic, to execute its autonomous agents (Scout, Analyst, Critic, Writer). 

We support three primary authentication methods:
1. **OAuth (Claude Pro)**: Best for local development. Free usage tied to your subscription.
2. **Anthropic API Key**: Best for local testing or secondary setups.
3. **GitHub Actions Secrets**: **Recommended for Production.** Fully autonomous and serverless.

---

## 🌐 Method 1: OAuth (Claude Pro) - Local Development

This is the recommended method for development, as it allows for unlimited reasoning without direct API costs.

1.  **Initiate Login**:
    ```bash
    claude code --login
    ```
2.  **Authorize**:
    - The CLI will provide a unique URL.
    - Copy and paste this URL into your web browser.
    - Click **Authorize** on the Anthropic dashboard.
3.  **Verify Status**:
    ```bash
    claude auth status
    ```
    *Output should confirm: `loggedIn: true` and `subscriptionType: pro`.*

---

## 🔑 Method 2: Anthropic API Key - Local Backup

Use this if you require programmatic authentication or don't have a Claude Pro subscription.

1.  **Obtain API Key**: Get your key from the [Anthropic Console](https://console.anthropic.com/settings/keys).
2.  **Configure Environment**:
    Add your key to a `.env` file in the project root:
    ```env
    ANTHROPIC_API_KEY=sk-ant-api03-XXXXXXXXXXXX
    ```

> [!WARNING]
> Using an API key incurs costs based on token usage. Monitor your billing dashboard.

---

## 🚀 Method 3: GitHub Actions (Production)

This is the **Gold Standard** for the autonomous Sentinel. It runs serverlessly on GitHub's infrastructure.

1.  **Setup Secrets**:
    - In your GitHub Repo, go to **Settings** → **Secrets and variables** → **Actions**.
    - Add a **New repository secret**:
      - Name: `ANTHROPIC_API_KEY`
      - Value: Your `sk-ant-api03-...` key.
2.  **Workflow**:
    The system is pre-configured with `.github/workflows/sentinel.yml`. It will automatically use this secret to run the pipeline daily.

---

## 🛠️ Session Management

| Action | Command |
| :--- | :--- |
| **Check Auth Status** | `claude auth status` |
| **Log Out** | `claude code --logout` |
| **Switch Account** | `claude code --logout` followed by `--login` |

---

## 🆘 Troubleshooting

### "Command Not Found"
- Ensure you installed the CLI globally: `npm install -g @anthropic-ai/claude-code`.

### API Key Not Recognized Locally
- Ensure `.env` is in the same directory as `sentinel.py`.
- If using `sentinel.py`, the CLI will prioritize the API key if the `--api-key-priority` flag is used (it is by default in the new scripts).
