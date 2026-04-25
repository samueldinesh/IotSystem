import os
import time
import json
import sqlite3
import subprocess
import paho.mqtt.client as mqtt
from datetime import datetime, timedelta

# Configuration
BROKER = "localhost"
PORT = 1883
DATA_TOPIC = "devices/{}/data"
ALARM_TOPIC = "alarms/active"
import sys
sys.path.append(os.getcwd())
from app.database import DB_PATH

class IntegrationTester:
    def __init__(self):
        self.received_alarms = []
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_message = self.on_message
        
    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            rule_name = payload.get('rule_name', 'Unknown')
            value = payload.get('trigger_value', 'N/A')
            print(f"   [TEST] Received Alarm: {rule_name} (Value: {value})")
            self.received_alarms.append(payload)
        except Exception as e:
            print(f"   [TEST] Error decoding alarm: {e}")

    def setup_db(self):
        print("1. Resetting Database...")
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS rules")
        cursor.execute("DROP TABLE IF EXISTS alarm_tracking")
        cursor.execute("DROP TABLE IF EXISTS alarm_history")
        cursor.execute("DROP TABLE IF EXISTS sensor_state")
        conn.commit()
        conn.close()
        
        from app.database import init_db
        init_db()
        print("Database initialized with production schema.")

    def add_rules(self):
        print("2. Adding Test Rules via CLI...")
        # 30-second duration for testing
        subprocess.run(["python", "cli.py", "add-rule", "--name", "HighTemp", "--type", "SIMPLE", 
                        "--primary-sensor", "temp_1", "--operator", ">", "--threshold", "30", "--duration", "30"], check=True)
        
        subprocess.run(["python", "cli.py", "add-rule", "--name", "FireAlarm", "--type", "CONDITIONAL", 
                        "--primary-sensor", "smoke_1", "--operator", ">", "--threshold", "50", "--duration", "30",
                        "--shunt-sensor", "sprinkler_1", "--shunt-operator", "==", "--shunt-threshold", "0"], check=True)

    def publish_data(self, sensor_id, value):
        topic = DATA_TOPIC.format(sensor_id)
        payload = {"sensor_id": sensor_id, "value": float(value), "timestamp": time.time()}
        self.client.publish(topic, json.dumps(payload))

    def run_tests(self):
        self.client.connect(BROKER, PORT, 60)
        self.client.subscribe(ALARM_TOPIC)
        self.client.loop_start()

        print("\n[INFO] Starting app.main as a background process...")
        service_process = subprocess.Popen(["python", "-m", "app.main"])
        time.sleep(3) # Wait for service to initialize

        try:
            print("\n--- TEST SCENARIO 1: Simple Threshold Violation (30s) ---")
            self.received_alarms = []
            print("Injecting temp_1 = 35 for 32 seconds...")
            for i in range(32):
                self.publish_data("temp_1", 35)
                time.sleep(1)
            
            triggered = any(a.get('rule_name') == 'HighTemp' for a in self.received_alarms)
            print(f"RESULT: {'PASS' if triggered else 'FAIL'}")

            print("\n--- TEST SCENARIO 2: Flapping Prevention ---")
            self.received_alarms = []
            conn = sqlite3.connect(DB_PATH); conn.execute("DELETE FROM alarm_tracking"); conn.commit(); conn.close()
            print("Injecting temp_1 = 35 for 10s, then 25 for 1s, then 35 for 10s...")
            for _ in range(10): self.publish_data("temp_1", 35); time.sleep(1)
            self.publish_data("temp_1", 25); time.sleep(1)
            for _ in range(10): self.publish_data("temp_1", 35); time.sleep(1)
            
            triggered = any(a.get('rule_name') == 'HighTemp' for a in self.received_alarms)
            print(f"RESULT: {'PASS (No alarm triggered)' if not triggered else 'FAIL (Alarm triggered despite flap)'}")

            print("\n--- TEST SCENARIO 3: Conditional Alarm (Shunt Active) ---")
            self.received_alarms = []
            conn = sqlite3.connect(DB_PATH); conn.execute("DELETE FROM alarm_tracking"); conn.commit(); conn.close()
            print("Injecting Smoke=60 AND Sprinkler=1 (Shunt Active) for 32 seconds...")
            for i in range(32):
                self.publish_data("smoke_1", 60)
                self.publish_data("sprinkler_1", 1)
                time.sleep(1)
            
            triggered = any(a.get('rule_name') == 'FireAlarm' for a in self.received_alarms)
            print(f"RESULT: {'PASS (Alarm suppressed)' if not triggered else 'FAIL'}")

            print("\n--- TEST SCENARIO 4: Conditional Alarm (Trigger) ---")
            self.received_alarms = []
            conn = sqlite3.connect(DB_PATH); conn.execute("DELETE FROM alarm_tracking"); conn.commit(); conn.close()
            print("Injecting Smoke=60 AND Sprinkler=0 for 32 seconds...")
            for i in range(32):
                self.publish_data("smoke_1", 60)
                self.publish_data("sprinkler_1", 0)
                time.sleep(1)
            
            triggered = any(a.get('rule_name') == 'FireAlarm' for a in self.received_alarms)
            print(f"RESULT: {'PASS' if triggered else 'FAIL'}")

            print("\n--- TEST SCENARIO 5: Reboot Persistence ---")
            self.received_alarms = []
            conn = sqlite3.connect(DB_PATH); conn.execute("DELETE FROM alarm_tracking"); conn.commit(); conn.close()
            print("Injecting temp_1 = 35 for 15s...")
            for i in range(15):
                self.publish_data("temp_1", 35)
                time.sleep(1)
            
            print("KILLING the Alarm Service...")
            service_process.terminate()
            service_process.wait()
            
            print("Waiting 10 seconds (Downtime)...")
            time.sleep(10)
            
            print("RESTARTING the Alarm Service...")
            service_process = subprocess.Popen(["python", "-m", "app.main"])
            time.sleep(3)
            
            print("Injecting temp_1 = 35 for 10 more seconds...")
            for i in range(10):
                self.publish_data("temp_1", 35)
                time.sleep(1)
            
            # Total elapsed time: 15s + 10s + 10s = 35s > 30s
            triggered = any(a.get('rule_name') == 'HighTemp' for a in self.received_alarms)
            print(f"RESULT: {'PASS (Alarm triggered across reboot)' if triggered else 'FAIL'}")

            print("\n--- TEST SCENARIO 6: Concurrent Multi-Sensor Processing ---")
            self.received_alarms = []
            conn = sqlite3.connect(DB_PATH); conn.execute("DELETE FROM alarm_tracking"); conn.commit(); conn.close()
            subprocess.run(["python", "cli.py", "add-rule", "--name", "ConcurrentTemp", "--type", "SIMPLE", 
                            "--primary-sensor", "temp_2", "--operator", ">", "--threshold", "30", "--duration", "5"], check=True)
            
            print("Injecting temp_1 and temp_2 simultaneously...")
            for _ in range(10):
                self.publish_data("temp_1", 35)
                self.publish_data("temp_2", 35)
                time.sleep(1)
                
            # Total window is 10s. 
            # HighTemp (30s) should NOT trigger.
            # ConcurrentTemp (5s) SHOULD trigger.
            temp1_triggered = any(a.get('rule_name') == 'HighTemp' for a in self.received_alarms)
            temp2_triggered = any(a.get('rule_name') == 'ConcurrentTemp' for a in self.received_alarms)
            
            if not temp1_triggered and temp2_triggered:
                print("RESULT: PASS (ConcurrentTemp triggered, HighTemp correctly suppressed due to duration)")
            else:
                print(f"RESULT: FAIL (Unexpected behavior: Temp1={temp1_triggered}, Temp2={temp2_triggered})")

        finally:
            print("\nCleaning up...")
            service_process.terminate()
            self.client.loop_stop()
            self.client.disconnect()

if __name__ == "__main__":
    tester = IntegrationTester()
    tester.setup_db()
    tester.add_rules()
    tester.run_tests()
    print("\nIntegration Testing Complete.")
