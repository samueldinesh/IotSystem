# Architecture & Design Document: Edge Alarms Service

## 1. Overview
The Edge Alarms Service is designed to run on a Linux-based IoT Gateway. It ingests sensor data via a local MQTT broker, evaluates this data against pre-defined rules (both simple thresholds and conditional logic involving multiple sensors), and triggers alarms.

## 2. Architectural Components

### 2.1. Mosquitto (MQTT Broker)
- **Role**: The central message bus for the local gateway.
- **Why Mosquitto**: It is open-source, highly lightweight, and an industry standard for edge gateways. It has minimal CPU and RAM footprints, making it perfect for resource-constrained devices like Raspberry Pis or industrial gateways.

### 2.2. Ingestion & Message Routing (app/main.py)
- **Role**: Connects to Mosquitto, subscribes to sensor topics (e.g., `devices/+/data`), and routes incoming messages to a multiprocessing Queue.
- **Design Choice**: Decoupling the MQTT network I/O from the rule evaluation logic using a Queue prevents the system from dropping messages during heavy processing loads.

### 2.3. Rule Processing Engine (app/main.py & app/rule_engine.py)
- **Role**: A pool of worker processes that consume messages from the Queue.
- **Design Choice**: `multiprocessing` is used to allow true parallel execution across multiple CPU cores on the edge device. This ensures scalability if the number of devices or rules increases.

### 2.4. State Management & Storage (SQLite)
- **Role**: Maintains persistent state.
- **Why SQLite**: SQLite is embedded, requires no background daemon, and stores data in a single file (`alarms.db`). It is highly reliable and perfect for edge gateways.
- **Configuration**: The database connection is configured to use Write-Ahead Logging (`pragma journal_mode=wal`). This allows simultaneous read and write operations, avoiding `database is locked` errors when multiple worker processes update the state simultaneously.

## 3. Data Flow
1. **Device -> MQTT**: A sensor publishes payload `{"sensor_id": "temp_1", "value": 25.5}` to `devices/temp_1/data`.
2. **MQTT -> Main Process**: The Paho-MQTT client receives the message in the `on_message` callback and pushes it to the `multiprocessing.Queue`.
3. **Queue -> Worker Process**: An idle worker process dequeues the message.
4. **Worker -> SQLite (Update State)**: The worker updates the `sensor_state` table with the latest value.
5. **Worker -> Rule Engine**: The worker queries active rules for this sensor.
6. **Rule Engine -> SQLite (Track Breach)**: If a condition is met (e.g. Temp > 24), a record is inserted into `alarm_tracking` with the current timestamp.
7. **Rule Engine -> Evaluation**: The worker checks if the time elapsed since `breach_start_time` is greater than or equal to the rule's `duration`.
8. **Alarm Trigger -> SQLite**: If duration is met, the tracking state is updated to `TRIGGERED` and a record is inserted into `alarm_history`.
9. **Alarm Trigger -> MQTT**: The alarm payload is published to `alarms/active`.

## 4. Data Models

### 4.1. Rules Table
Stores both Simple and Conditional rules.
- `id` (INTEGER): Primary Key
- `name` (TEXT): Human-readable name
- `type` (TEXT): 'SIMPLE' or 'CONDITIONAL'
- `primary_sensor` (TEXT): Target sensor ID
- `operator` (TEXT): >, <, >=, <=, ==, !=
- `threshold` (REAL): Value to compare against
- `duration` (INTEGER): Seconds the condition must be maintained
- `shunt_sensor` (TEXT): Secondary sensor ID for Conditional rules
- `shunt_operator` (TEXT): Operator for secondary sensor
- `shunt_threshold` (REAL): Threshold for secondary sensor

### 4.2. Sensor State Table
Keeps the latest known value of all sensors. Used to evaluate shunt conditions.
- `sensor_id` (TEXT): Primary Key
- `value` (REAL)
- `last_updated` (TIMESTAMP)

### 4.3. Alarm Tracking Table
Manages the stateful tracking of active evaluations to survive gateway reboots.
- `rule_id` (INTEGER)
- `sensor_id` (TEXT)
- `breach_start_time` (TIMESTAMP)
- `status` (TEXT): 'EVALUATING' or 'TRIGGERED'

## 5. Assumptions & Corner Cases Addressed
- **Reboot Resilience**: By persisting the `breach_start_time` in SQLite, if the gateway reboots in the middle of a 60-minute duration, the evaluation resumes exactly where it left off once the service restarts.
- **Concurrent DB Access**: Using SQLite WAL mode mitigates locking issues when multiple worker processes attempt to update sensor states or alarm histories simultaneously.
- **Missing Shunt Data**: If a conditional rule requires a shunt sensor (e.g., `Current > 0`) but that sensor hasn't published any data yet, the conditional rule evaluates to `False` until the data arrives.
- **Flip-Flopping Values**: If a temperature bounces between 24.1 and 23.9, the continuous condition is broken. The worker will delete the `alarm_tracking` record, effectively resetting the duration timer.

## 6. Future Enhancements
- **HTTP Webhook Publishing**: The publisher module can easily be extended to make async POST requests to a cloud endpoint.
- **Web UI**: The SQLite database can be exposed via a lightweight REST API (e.g., FastAPI) to support a React/Vue frontend for configuration, bypassing the CLI.
