# Project Midas: Deployment Guide

## 1. Local Development Setup (Windows/Mac/Linux)
1. **Clone/Download the Repository**
2. **Initialize Virtual Environment:**
   * Windows: `python -m venv venv` then `venv\Scripts\activate`
   * Mac/Linux: `python3 -m venv venv` then `source venv/bin/activate`
3. **Install Dependencies:**
   * Run: `pip install flask ccxt ib_insync python-dotenv`
4. **Environment Variables:**
   * Ensure a `.env` file exists in the root directory.
   * Do not commit `.env` to version control.
5. **Run the Application:**
   * Execute: `python app.py`
   * Open a web browser to `http://127.0.0.1:5000`

## 2. Cloud Deployment (Future Scope)
To run Project Midas 24/7 without a local machine:
* **Recommended Host:** DigitalOcean Droplet or AWS EC2 (Ubuntu).
* **Web Server:** Gunicorn (to replace the Flask development server) + Nginx as a reverse proxy.
* **Process Manager:** `systemd` or `pm2` to ensure the bot automatically restarts if the server reboots.
* **Security:** Must place the dashboard behind an authentication layer (e.g., HTTP Basic Auth or Flask-Login) to prevent unauthorized executions over the public internet.