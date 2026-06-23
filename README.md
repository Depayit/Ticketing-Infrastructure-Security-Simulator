# Ticketing Infrastructure Security Simulator

A distributed security research platform designed to study large-scale ticketing systems, queue protection mechanisms, fraud detection controls, and automation-driven attacks in a controlled environment.

---

## Overview

Modern ticketing platforms face increasing challenges from automated purchasing systems, proxy networks, session farming, and large-scale bot operations.

This project provides a research environment for analyzing both offensive automation techniques and defensive security controls commonly found in ticketing infrastructures.

The platform is designed around a distributed architecture consisting of multiple workers, centralized orchestration, real-time monitoring, and fraud-defense simulation components.

---

## Key Features

### Distributed Worker Architecture

* Centralized task orchestration
* Multi-worker execution model
* Horizontal scaling support
* Redis-based coordination

### Automation Research

* Session lifecycle simulation
* Request scheduling
* Behavioral pattern analysis
* Queue interaction modeling

### Defense Simulation

* Fraud detection engine
* Rate limiting simulation
* Queue protection mechanisms
* Behavioral anomaly detection

### Monitoring & Telemetry

* Real-time worker monitoring
* Event collection
* Execution statistics
* Operational dashboard

### Frontend Dashboard

* Live worker status
* Task monitoring
* Queue visibility
* System management interface

---

# System Architecture

![System Architecture](docs/images/ChatGPTImage23มิ.ย.256912_25_09.png)

---

## Components

### Manager

Responsible for:

* Task scheduling
* Worker coordination
* System state management
* Event aggregation

### Workers

Responsible for:

* Task execution
* Session management
* Queue interaction simulation
* Result reporting

### Proxy Rotator

Responsible for:

* Proxy pool management
* Rotation policies
* Request distribution

### Defense Demo

Responsible for:

* Simulated protection mechanisms
* Fraud scoring
* Detection logic evaluation

### Frontend

Provides:

* Operational visibility
* Worker control
* Real-time monitoring
* Research analytics

---

## Security Research Objectives

This project focuses on understanding:

* Automated purchasing behavior
* Queue system resilience
* Fraud prevention effectiveness
* Detection evasion techniques
* Infrastructure bottlenecks

The platform is intended for educational, research, and defensive security purposes.

---

## Technology Stack

### Backend

* Python
* FastAPI
* Redis
* WebSocket

### Frontend

* React
* TypeScript
* Vite

### Infrastructure

* Docker
* Docker Compose

---

## Project Structure

```text
project/
├── manager/
├── worker/
├── frontend/
├── proxy-rotator/
├── bot-connector/
├── defense-demo/
├── docs/
└── docker/
```

---

## Future Roadmap

* Threat Modeling Framework
* Advanced Fraud Analytics
* Grafana Integration
* Prometheus Metrics
* CI/CD Security Pipeline
* Distributed Load Testing
* Behavioral Detection Engine
* AI-assisted Security Analysis

---

## Disclaimer

This project is intended for security research, educational use, and defensive testing in authorized environments only.

Users are responsible for ensuring compliance with applicable laws, regulations, and platform terms of service.

---

## Author

Jacob Nuttapong (Depayit)

Cybersecurity Researcher | Security Automation | Distributed Systems | AI Security
