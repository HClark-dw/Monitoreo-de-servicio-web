===============================================================================
       API & MONITORING ENGINE FOR SERVER AND WEB SERVICE STATUS
===============================================================================

TECHNICAL PORTFOLIO PROJECT
Language: Python 3.10+ / Python 3.14+
External Dependencies: None (100% Python Standard Library)
License: MIT


1. GENERAL DESCRIPTION
-------------------------------------------------------------------------------
This application is a lightweight, concurrent, and highly resilient solution
for continuous monitoring of web service (HTTP/HTTPS) and IP/network port (TCP)
availability (Uptime) and latency.

Key Features:
- Multi-Threaded Concurrent Polling: Uses ThreadPoolExecutor to check multiple
  services in parallel without blocking.
- Granular Network Diagnostics: Precisely identifies the root cause of outages
  (DNS failure, connection timeout, closed port, or HTTP 4xx/5xx errors).
- Real-Time Web Panel: Self-contained HTML5/CSS/JS dashboard that automatically
  refreshes every 5 seconds.
- Integrated REST API: JSON endpoints to query status, health, and metrics.
- Dual Logging System:
  * logs/monitor.log   -> Human-readable rotating log format (RotatingFileHandler).
  * logs/monitor.jsonl -> Structured JSON Lines format for ingestion into systems
                          like Datadog, ElasticSearch, or Grafana Loki.
- Zero Dependencies: Requires no 'pip install' to run; executes natively on
  any machine with Python installed.


2. KEY POINTS FOR TECHNICAL INTERVIEWS
-------------------------------------------------------------------------------
This project was designed to demonstrate strong software engineering and
backend development skills:

a) Advanced Network and Socket Handling:
   Implements application-layer polling (HttpProber) and transport-layer polling
   (TcpProber). The latter measures the SYN/ACK handshake at the socket level
   without requiring ICMP superuser privileges.

b) Exhaustive Exception Handling:
   Avoids generic try-except catches ('except Exception'). Categorically handles:
   - socket.gaierror: DNS domain name resolution failures.
   - socket.timeout / TimeoutError: Connection response timeouts.
   - ConnectionRefusedError: Unstarted service or firewall block.
   - ssl.SSLError: Invalid certificates or TLS handshake failures.
   - urllib.error.HTTPError: Differentiation between 4xx (degraded) and 5xx codes.

c) Concurrency and Thread-Safe Synchronization:
   In-memory state and accumulated metrics are protected using 'threading.RLock',
   guaranteeing thread-safe concurrent access between polling threads and incoming
   HTTP web server requests.

d) Clean Data Structuring and Modeling:
   Uses typed Dataclasses ('TargetConfig', 'CheckResult', 'TargetMetrics') for
   immutability and mathematical calculation of cumulative uptime SLAs (%)
   and moving averages of latency in milliseconds.

e) Graceful Shutdown:
   Captures termination signals (SIGINT / Ctrl+C, SIGTERM) to cleanly stop the
   thread pool and close sockets without leaving zombie processes.


3. PROJECT STRUCTURE
-------------------------------------------------------------------------------
Server Status Monitoring API/
|-- config.json           <- URL/IP configurations, timeouts, and intervals.
|-- main.py               <- CLI entry point and HTTP server.
|-- requirements.txt      <- Technical specs (0 dependencies).
|-- README.md             <- Full documentation in Markdown format.
|-- readme.txt            <- This quick guide document.
|-- .gitignore            <- Files excluded from version control.
|-- monitor/              <- Internal logic package
|   |-- __init__.py
|   |-- config.py         <- JSON configuration loading and validation.
|   |-- models.py         <- Typed Dataclasses and data models.
|   |-- probers.py        <- Network probers (HTTP and TCP Sockets).
|   |-- engine.py         <- Concurrent engine using ThreadPoolExecutor.
|   |-- store.py          <- Thread-safe in-memory store and SLA calculation.
|   |-- logger.py         <- Structured rotating and JSON Lines logging.
|   `-- api.py            <- HTTP REST Server and Real-Time Web Dashboard.
|-- tests/                <- Automated test suite (18 tests)
|   |-- test_config.py    <- URL, port, and schema validation.
|   |-- test_probers.py   <- Network mocks (DNS, Timeout, Refused, 500).
|   |-- test_store.py     <- Availability and latency calculations.
|   `-- test_api.py       <- Functional tests for HTTP endpoints.
`-- logs/                 <- Auto-generated logs directory
    |-- monitor.log
    `-- monitor.jsonl


4. USAGE AND EXECUTION GUIDE
-------------------------------------------------------------------------------
1) Full Mode (Console + HTTP Server + Web Panel):
   python main.py

   The service will start and print an informational banner.
   You can open the following address in your browser:
   http://127.0.0.1:8080/

2) Single Probe Mode (Ideal for CI/CD, Cron Jobs, or Quick Checks):
   python main.py --once

3) Console Only Mode (Without HTTP Server):
   python main.py --no-api

4) Custom Port:
   python main.py -p 9090

5) Run Automated Unit Tests:
   python -m unittest discover -s tests -v


5. REST API ENDPOINTS
-------------------------------------------------------------------------------
GET  /         -> Interactive visual dashboard (HTML5 + CSS + JS).
GET  /status   -> Full telemetry in JSON format (status, SLAs, latencies).
GET  /health   -> Health check of the monitor itself (HTTP 200).
GET  /metrics  -> Aggregated system metrics (total services, UP, DOWN).
GET  /targets  -> List of configured targets.
POST /targets  -> On-the-fly registration of new services to monitor.

Sample JSON payload for POST /targets:
{
  "name": "New Web Server",
  "type": "http",
  "url": "https://my-domain.com/api",
  "interval_seconds": 15,
  "timeout_seconds": 3.0,
  "expected_status": 200
}


6. STEPS TO UPLOAD THE PROJECT TO GITHUB
-------------------------------------------------------------------------------
To publish this repository on your GitHub account, run the following terminal commands:

1) Initialize local Git repository:
   git init

2) Add all files to staging:
   git add .

3) Make the initial commit:
   git commit -m "feat: initial implementation of concurrent server monitor"

4) Create an empty repository on https://github.com/new (e.g., 'server-monitor')

5) Link to your remote repository and push the main branch:
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/server-monitor.git
   git push -u origin main