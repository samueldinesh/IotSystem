import paho.mqtt.client as mqtt
import time
import json
import random
import argparse

MQTT_BROKER = "localhost"
MQTT_PORT = 1883

def publish_data(client, sensor_id, value):
    topic = f"devices/{sensor_id}/data"
    payload = {
        "sensor_id": sensor_id,
        "value": value,
        "timestamp": time.time()
    }
    client.publish(topic, json.dumps(payload))
    print(f"Published to {topic}: {payload}")

def main():
    parser = argparse.ArgumentParser(description="Mock IoT Device Publisher")
    parser.add_argument('--sensor', type=str, default='temp_1', help='Sensor ID')
    parser.add_argument('--value', type=float, help='Specific value to publish')
    parser.add_argument('--random', action='store_true', help='Publish random values continuously')
    parser.add_argument('--min', type=float, default=20.0)
    parser.add_argument('--max', type=float, default=30.0)
    parser.add_argument('--interval', type=int, default=5, help='Interval in seconds for random publishing')
    
    args = parser.parse_args()
    
    from paho.mqtt.enums import CallbackAPIVersion
    client = mqtt.Client(CallbackAPIVersion.VERSION2)
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
    
    try:
        if args.random:
            print(f"Publishing random data for {args.sensor} every {args.interval}s...")
            while True:
                val = random.uniform(args.min, args.max)
                publish_data(client, args.sensor, round(val, 2))
                time.sleep(args.interval)
        else:
            if args.value is None:
                print("Error: Must provide --value if not using --random")
                return
            publish_data(client, args.sensor, args.value)
            time.sleep(1) # wait for publish
    except KeyboardInterrupt:
        print("Stopping mock device.")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == '__main__':
    main()
