# Edge Alarms Service

A robust, stateful, multi-process Alarm Evaluation Service for Linux-based IoT Gateways.

---

## 🛠️ Platform Setup & Prerequisites

Before running the service, ensure you have the following installed on your system:

- **Python 3.8+** (Required for the service and CLI)
- **Docker & Docker Compose** (Required for the MQTT Broker)
- **Git** (For version control)

### 💻 Environment Specifics

#### Windows (Native)

1. **Virtual Env**: `python -m venv venv` then `venv\Scripts\activate`.
2. **Dependencies**: `pip install -r requirements.txt`.

#### Linux (Ubuntu/Debian) / Windows (WSL 2)

1. **System Deps**: `sudo apt update && sudo apt install python3-pip python3-venv sqlite3 -y`.
2. **Virtual Env**: `python3 -m venv venv` then `source venv/bin/activate`.
3. **Dependencies**: `pip install -r requirements.txt`.

---

## 🚀 Quick Start Guide

### 1. Start the MQTT Broker

Ensure Docker is running and execute:

```bash
docker-compose up -d
```

### 2. Run the Alarm Service

This daemon subscribes to MQTT, spawns parallel worker processes, and evaluates rules.

```bash
# Ensure venv is activated
python -m app.main
```

### 3. Configure Alarm Rules (CLI)

Open a **new terminal** (with venv active) to use the Command Line Interface.

**Add a Simple Rule:**

```bash
python cli.py add-rule --name "High Temp" --type SIMPLE --primary-sensor temp_1 --operator ">" --threshold 24 --duration 10
```

**Add a Conditional Rule:**

```bash
python cli.py add-rule --name "Machine Overheat" --type CONDITIONAL --primary-sensor temp_1 --operator ">" --threshold 24 --duration 10 --shunt-sensor motor_status --shunt-operator "==" --shunt-threshold 1
```

---

## 🧪 Testing & Verification

We have provided a **Mock Device** script to simulate real IoT sensor data.

1. **Simulate a Breach**:
   ```bash
   python mock_device.py --sensor temp_1 --value 28
   ```
2. **Observe Logs**: The service will log `Starting evaluation duration timer`.
3. **Wait for Duration**: After 10 seconds, the alarm will trigger and publish to the `alarms/active` MQTT topic.
4. **Check Status**:
    ```bash
    # View all current rules
    python cli.py list-rules

    # View latest incoming sensor data
    python cli.py sensors

    # View triggered or evaluating alarms
    python cli.py active-alarms
    
    # View historical alarms
    python cli.py history

    # Delete a rule by ID
    python cli.py delete-rule --id 1
    ```

---

## 🧹 Shutdown & Cleanup

To stop the system and clear temporary data:

1. **Stop the Alarm Service**: Press `Ctrl+C` in the terminal where `app.main` is running.
2. **Stop the MQTT Broker**:
   ```bash
   docker-compose down
   ```
3. **Reset the Database (Optional)**:
   ```bash
   # Remove the local SQLite database
   rm data/alarms.db
   ```

---

## 📑 Architecture & Data Flow

This project follows an **Event-Driven Architecture**:
- **Ingestion**: Decoupled via `multiprocessing.Queue`.
- **Parallelism**: Adaptive worker pool based on CPU core count.
- **Persistence**: Stateful evaluation stored in SQLite (WAL mode) to survive power cycles.
- **Standards**: All timing is evaluated using Naive UTC to ensure industrial precision.

> [!TIP]
> This project is designed for **Linux-based IoT Gateways**. Running in WSL 2 is the recommended way to test the Linux-like behavior on a Windows machine.
