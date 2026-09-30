# Defense Lab case study

This case study describes a local high-demand ticket sale simulation. The system layers are Edge/WAF, Bot Manager, Waiting Room, Auth Gate, form CAPTCHA, Booking/Seat Hold, fraud scoring, and mock payment verification. No real ticketing service is contacted.

The gateway enforces IP and route limits, sensor submission, and workflow gates. The queue issues an IP and Sensor Session bound Admit Token. The Booking Layer applies a fraud score before an atomic Seat Hold. Payment becomes a permanent sold seat only after a successful mock 3DS or QR verification. Expired holds are released and repeated failed holds can trigger a temporary session/IP block.

Profiles A–D place Login, CAPTCHA and admission differently. See [WORKFLOW.md](WORKFLOW.md) for exact gates and [SCENARIOS.md](SCENARIOS.md) for the reproducible scenario matrix. The built-in load generator writes raw JSON results to `reports/`; use [AFTER_ACTION_REPORT.md](AFTER_ACTION_REPORT.md) to record denominators and layer evidence. A successful synthetic bot scenario demonstrates a gap in this simulated configuration, not a claim about any production system.

Start the lab with `docker compose -f docker-compose.defense.yml up --build`. Open `/admin` for Live Audit, or enable the `observability` Compose profile for Prometheus and Grafana. Run `lab-tests` and `lab-smoke` from the `test` profile to verify Redis state transitions and full A–D purchases.
