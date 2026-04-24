import paho.mqtt.client as mqtt
import json
import multiprocessing
import time
import datetime
from .database import get_connection, init_db
from .rule_engine import check_rule

MQTT_BROKER = "localhost"
MQTT_PORT = 1883
TOPIC_SUBSCRIBE = "devices/+/data" # e.g. devices/sensor1/data
TOPIC_PUBLISH = "alarms/active"

def update_sensor_state(conn, sensor_id, value):
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO sensor_state (sensor_id, value, last_updated)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(sensor_id) DO UPDATE SET value=excluded.value, last_updated=CURRENT_TIMESTAMP
    ''', (sensor_id, value))
    conn.commit()

def process_message(msg_payload):
    """
    Worker function executed in parallel.
    msg_payload: dict with sensor_id, value, timestamp
    """
    sensor_id = msg_payload.get('sensor_id')
    value = msg_payload.get('value')
    if sensor_id is None or value is None:
        return
        
    conn = get_connection()
    try:
        # 1. Update the latest state for this sensor
        update_sensor_state(conn, sensor_id, value)
        
        # 2. Fetch all rules where this sensor is primary
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM rules WHERE primary_sensor=?", (sensor_id,))
        rules = cursor.fetchall()
        
        current_time = datetime.datetime.utcnow()
        
        for rule in rules:
            rule_id = rule['id']
            
            # Check conditional rules for shunt value
            shunt_value = None
            if rule['type'] == 'CONDITIONAL' and rule['shunt_sensor']:
                cursor.execute("SELECT value FROM sensor_state WHERE sensor_id=?", (rule['shunt_sensor'],))
                row = cursor.fetchone()
                if row:
                    shunt_value = row['value']
                    
            # Check immediate condition
            is_breached = check_rule(rule, value, shunt_value)
            
            # Get current tracking state
            cursor.execute("SELECT * FROM alarm_tracking WHERE rule_id=? AND sensor_id=?", (rule_id, sensor_id))
            tracking = cursor.fetchone()
            
            if is_breached:
                if not tracking:
                    # New breach
                    print(f"[Worker] Rule {rule['name']} breached. Starting evaluation.")
                    cursor.execute('''
                        INSERT INTO alarm_tracking (rule_id, sensor_id, breach_start_time, status)
                        VALUES (?, ?, ?, 'EVALUATING')
                    ''', (rule_id, sensor_id, current_time.isoformat()))
                    conn.commit()
                    tracking_start = current_time
                    status = 'EVALUATING'
                else:
                    tracking_start = datetime.datetime.fromisoformat(tracking['breach_start_time'])
                    status = tracking['status']
                    
                # Check if duration is met
                duration_sec = rule['duration']
                elapsed = (current_time - tracking_start).total_seconds()
                
                if elapsed >= duration_sec and status == 'EVALUATING':
                    # ALARM TRIGGERED!
                    print(f"[Worker] ALARM TRIGGERED for Rule: {rule['name']}")
                    
                    # Update state
                    cursor.execute('''
                        UPDATE alarm_tracking SET status='TRIGGERED' 
                        WHERE rule_id=? AND sensor_id=?
                    ''', (rule_id, sensor_id))
                    
                    # Record history
                    cursor.execute('''
                        INSERT INTO alarm_history (rule_id, sensor_id, triggered_at)
                        VALUES (?, ?, ?)
                    ''', (rule_id, sensor_id, current_time.isoformat()))
                    conn.commit()
                    
                    # Publish Alarm
                    publish_alarm(rule, sensor_id, value)
                    
            else:
                # Condition is no longer met, clear tracking if it exists
                if tracking:
                    print(f"[Worker] Rule {rule['name']} recovered.")
                    cursor.execute("DELETE FROM alarm_tracking WHERE rule_id=? AND sensor_id=?", (rule_id, sensor_id))
                    conn.commit()
                    
    except Exception as e:
        print(f"Error processing message: {e}")
    finally:
        conn.close()

def publish_alarm(rule, sensor_id, current_value):
    payload = {
        "rule_id": rule['id'],
        "rule_name": rule['name'],
        "sensor_id": sensor_id,
        "trigger_value": current_value,
        "timestamp": datetime.datetime.utcnow().isoformat()
    }
    # Simple one-off publish (for production, use a dedicated publish queue/process)
    import paho.mqtt.publish as publish
    try:
        publish.single(TOPIC_PUBLISH, json.dumps(payload), hostname=MQTT_BROKER, port=MQTT_PORT)
    except Exception as e:
        print(f"Failed to publish alarm: {e}")

def worker_main(queue):
    print("Worker process started.")
    while True:
        msg = queue.get()
        if msg == "QUIT":
            break
        process_message(msg)

# MQTT Callbacks
def on_connect(client, userdata, flags, rc):
    print("Connected to MQTT broker with result code " + str(rc))
    client.subscribe(TOPIC_SUBSCRIBE)

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode('utf-8'))
        # Payload format expected: {"sensor_id": "temp_1", "value": 25.5}
        # We push to the multiprocessing queue
        userdata['queue'].put(payload)
    except json.JSONDecodeError:
        print("Received invalid JSON")

def start_service():
    init_db()
    
    # Create multiprocessing queue
    manager = multiprocessing.Manager()
    queue = manager.Queue()
    
    # Start workers
    num_workers = multiprocessing.cpu_count()
    workers = []
    for _ in range(num_workers):
        p = multiprocessing.Process(target=worker_main, args=(queue,))
        p.start()
        workers.append(p)
        
    # Start MQTT Client
    client = mqtt.Client(userdata={'queue': queue})
    client.on_connect = on_connect
    client.on_message = on_message
    
    print(f"Connecting to MQTT Broker at {MQTT_BROKER}:{MQTT_PORT}...")
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_forever()
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        for _ in workers:
            queue.put("QUIT")
        for p in workers:
            p.join()

if __name__ == "__main__":
    start_service()
