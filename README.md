# Edge Alarms Service

A robust, stateful, multi-process Alarm Evaluation Service for Linux-based IoT Gateways.

## Architecture Highlights
- **Parallel Execution**: Uses Python's `multiprocessing` to distribute rule evaluation across CPU cores.
- **Stateful via SQLite**: Utilizes SQLite with WAL (Write-Ahead Logging) to persist evaluation states across unexpected reboots, ensuring time-based rules are not reset.
- **MQTT Ingestion & Egress**: Integrates cleanly into existing local IoT topologies via Mosquitto.

## Prerequisites
- Docker & Docker Compose (for running Mosquitto easily)
- Python 3.8+
- Git

## 1. Setup

### Start the MQTT Broker
We use Eclipse Mosquitto as the local MQTT broker.
```bash
docker-compose up -d
```

### Install Dependencies
```bash
python -m venv venv
# On Windows: venv\Scripts\activate
# On Linux: source venv/bin/activate
pip install -r requirements.txt
```

## 2. Running the Service

Start the main alarm daemon. This will automatically initialize the database (`data/alarms.db`) if it doesn't exist, spawn worker processes, and connect to MQTT.
```bash
python -m app.main
```

## 3. Configuring Rules via CLI

Open a new terminal (ensure the venv is activated).

**Add a Simple Rule:**
Trigger if `temp_1` is > 24 for 10 seconds.
```bash
python cli.py add-rule --name "High Temp Warning" --type SIMPLE --primary-sensor temp_1 --operator ">" --threshold 24 --duration 10
```

**Add a Conditional Rule:**
Trigger if `temp_1` > 24 for 10 seconds, BUT ONLY IF `current_1` > 0.
```bash
python cli.py add-rule --name "High Temp While Running" --type CONDITIONAL --primary-sensor temp_1 --operator ">" --threshold 24 --duration 10 --shunt-sensor current_1 --shunt-operator ">" --shunt-threshold 0
```

**List Rules:**
```bash
python cli.py list-rules
```

## 4. Testing & Verification

We have provided a mock device script to publish data.

1. **Publish Data (Below Threshold):**
   ```bash
   python mock_device.py --sensor temp_1 --value 20
   ```
   Check the daemon logs. Nothing should happen.

2. **Publish Data (Above Threshold):**
   ```bash
   python mock_device.py --sensor temp_1 --value 25
   ```
   The daemon logs will show: `[Worker] Rule High Temp Warning breached. Starting evaluation.`

3. **Check Active Alarms:**
   Run `python cli.py active-alarms`. You will see the rule is in the `EVALUATING` state.

4. **Wait for Duration (10s), then publish again:**
   ```bash
   python mock_device.py --sensor temp_1 --value 26
   ```
   The daemon logs will show `ALARM TRIGGERED`. The alarm is published to the `alarms/active` MQTT topic.

5. **Check Alarm History:**
   ```bash
   python cli.py history
   ```
   You will see the historical record of the trigger.

6. **Recover the Alarm:**
   ```bash
   python mock_device.py --sensor temp_1 --value 20
   ```
   The daemon logs will show: `[Worker] Rule High Temp Warning recovered.`

## 5. Listening to Output Alarms
To verify the service is publishing alarms correctly, you can subscribe to the output topic using mosquitto clients or a python script:
```bash
docker exec -it mosquitto-broker mosquitto_sub -t "alarms/active"
```
