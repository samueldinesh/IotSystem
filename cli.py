import argparse
import sqlite3
from prettytable import PrettyTable
import os

from app.database import DB_PATH

def get_connection():
    if not os.path.exists(DB_PATH):
        print("Database not found. Please run the service first to initialize it.")
        exit(1)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def add_rule(args):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO rules (name, type, primary_sensor, operator, threshold, duration, shunt_sensor, shunt_operator, shunt_threshold)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            args.name, args.type, args.primary_sensor, args.operator, args.threshold, args.duration,
            args.shunt_sensor, args.shunt_operator, args.shunt_threshold
        ))
        conn.commit()
        print(f"Successfully added rule '{args.name}' with ID: {cursor.lastrowid}")
    except Exception as e:
        print(f"Error adding rule: {e}")
    finally:
        conn.close()

def list_rules(args):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM rules")
    rules = cursor.fetchall()
    
    if not rules:
        print("No rules found.")
        return

    table = PrettyTable()
    table.field_names = ["ID", "Name", "Type", "Primary Sensor", "Condition", "Duration(s)", "Shunt Sensor", "Shunt Condition", "Created At"]
    
    for r in rules:
        condition = f"{r['operator']} {r['threshold']}"
        shunt_condition = f"{r['shunt_operator']} {r['shunt_threshold']}" if r['shunt_sensor'] else "N/A"
        shunt_sensor = r['shunt_sensor'] if r['shunt_sensor'] else "N/A"
        # Format the timestamp for better readability
        created_at = r['created_at'][:19] if r['created_at'] else "N/A"
        table.add_row([r['id'], r['name'], r['type'], r['primary_sensor'], condition, r['duration'], shunt_sensor, shunt_condition, created_at])
        
    print(table)
    conn.close()

def active_alarms(args):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT a.rule_id, r.name, a.sensor_id, a.breach_start_time, a.status 
        FROM alarm_tracking a
        JOIN rules r ON a.rule_id = r.id
    ''')
    alarms = cursor.fetchall()
    
    if not alarms:
        print("No active alarms or evaluations.")
        return

    table = PrettyTable()
    table.field_names = ["Rule ID", "Rule Name", "Sensor ID", "Breach Start Time", "Status"]
    
    for a in alarms:
        table.add_row([a['rule_id'], a['name'], a['sensor_id'], a['breach_start_time'], a['status']])
        
    print(table)
    conn.close()

def alarm_history(args):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT h.id, h.rule_id, r.name, h.sensor_id, h.triggered_at
        FROM alarm_history h
        JOIN rules r ON h.rule_id = r.id
        ORDER BY h.triggered_at DESC
        LIMIT ?
    ''', (args.limit,))
    history = cursor.fetchall()
    
    if not history:
        print("No alarm history found.")
        return

    table = PrettyTable()
    table.field_names = ["History ID", "Rule ID", "Rule Name", "Sensor ID", "Triggered At"]
    
    for h in history:
        table.add_row([h['id'], h['rule_id'], h['name'], h['sensor_id'], h['triggered_at']])
        
    print(table)
    conn.close()

def list_sensors(args):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sensor_state ORDER BY sensor_id ASC")
    sensors = cursor.fetchall()

    if not sensors:
        print("No sensor data found. Has the service received any MQTT messages?")
        return

    table = PrettyTable()
    table.field_names = ["Sensor ID", "Latest Value", "Last Updated"]
    
    for s in sensors:
        # Format timestamp
        last_updated = s['last_updated'][:19] if s['last_updated'] else "N/A"
        table.add_row([s['sensor_id'], s['value'], last_updated])
        
    print(table)
    conn.close()

def delete_rule(args):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM rules WHERE id = ?", (args.id,))
        if cursor.rowcount > 0:
            conn.commit()
            print(f"Successfully deleted rule with ID: {args.id}")
        else:
            print(f"No rule found with ID: {args.id}")
    except Exception as e:
        print(f"Error deleting rule: {e}")
    finally:
        conn.close()

def main():
    parser = argparse.ArgumentParser(description="Edge Alarms Service CLI")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Add Rule Command
    parser_add = subparsers.add_parser('add-rule', help='Add a new alarm rule')
    parser_add.add_argument('--name', required=True, help='Name of the rule')
    parser_add.add_argument('--type', required=True, choices=['SIMPLE', 'CONDITIONAL'], help='Type of the rule')
    parser_add.add_argument('--primary-sensor', required=True, help='ID of the primary sensor (e.g., temp_1)')
    parser_add.add_argument('--operator', required=True, choices=['>', '<', '>=', '<=', '==', '!='], help='Operator for the primary threshold')
    parser_add.add_argument('--threshold', required=True, type=float, help='Threshold value for the primary sensor')
    parser_add.add_argument('--duration', required=True, type=int, help='Duration in seconds the threshold must be breached to trigger alarm')
    
    # Conditional args
    parser_add.add_argument('--shunt-sensor', help='ID of the shunt sensor (required for CONDITIONAL)')
    parser_add.add_argument('--shunt-operator', choices=['>', '<', '>=', '<=', '==', '!='], help='Operator for the shunt threshold')
    parser_add.add_argument('--shunt-threshold', type=float, help='Threshold value for the shunt sensor')
    
    # List Rules Command
    parser_list = subparsers.add_parser('list-rules', help='List all configured rules')
    
    # Active Alarms Command
    parser_active = subparsers.add_parser('active-alarms', help='View currently evaluating and triggered alarms')
    
    # Alarm History Command
    parser_history = subparsers.add_parser('history', help='View historical triggered alarms')
    parser_history.add_argument('--limit', type=int, default=50, help='Number of records to fetch')

    # List Sensors Command
    parser_sensors = subparsers.add_parser('sensors', help='View latest sensor values and status')

    # Delete Rule Command
    parser_delete = subparsers.add_parser('delete-rule', help='Delete an existing alarm rule')
    parser_delete.add_argument('--id', required=True, type=int, help='ID of the rule to delete')

    args = parser.parse_args()

    if args.command == 'add-rule':
        if args.type == 'CONDITIONAL':
            if not all([args.shunt_sensor, args.shunt_operator, args.shunt_threshold is not None]):
                parser.error("CONDITIONAL rules require --shunt-sensor, --shunt-operator, and --shunt-threshold")
        add_rule(args)
    elif args.command == 'list-rules':
        list_rules(args)
    elif args.command == 'active-alarms':
        active_alarms(args)
    elif args.command == 'history':
        alarm_history(args)
    elif args.command == 'sensors':
        list_sensors(args)
    elif args.command == 'delete-rule':
        delete_rule(args)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
