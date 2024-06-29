import subprocess
import json
import time
import pika
import os
import tempfile
import base64

# Константы путей к словарям
WORDLIST_PATHS = {
    1: '/dictionaries/rockyou.txt',
    2: '/dictionaries/rockyou.txt',
    3: '/dictionaries/BIG-WPA-LIST-1',
    4: '/dictionaries/weakpass_3w'
}

def convert_cap_to_hc22000(cap_file):
    with tempfile.NamedTemporaryFile(suffix='.hc22000', delete=False) as temp_hc22000:
        hc22000_file = temp_hc22000.name
    
    convert_cmd = [
        'hcxpcapngtool', '-o', hc22000_file, cap_file
    ]
    
    process = subprocess.run(convert_cmd, capture_output=True, text=True)
    
    if process.returncode != 0:
        print(f"Conversion failed: {process.stderr}")
        return None
    
    return hc22000_file

def run_hashcat(filepath, wordlist_file, output_file, channel):
    hc22000_file = convert_cap_to_hc22000(filepath)
    hashcat_cmd = [
        'hashcat' , '-m', '22000', '-a', '0',
        hc22000_file, wordlist_file,
        '--status', '--status-json', '--outfile', output_file, '--potfile-disable'
    ]

    process = subprocess.Popen(hashcat_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    while True:
        output = process.stdout.readline()
        if output == '' and process.poll() is not None:
            break
        if output.strip().startswith('{'):
            status = json.loads(output.strip())
            send_progress(channel, filepath, status)
        print(output.strip())  # Вывод в консоль для дебаггинга

    stderr_output = process.stderr.read()
    if stderr_output:
        print(f"Hashcat failed with error: {stderr_output.strip()}")

    process.stdout.close()
    process.stderr.close()

    # Отправка результата после завершения работы Hashcat
    read_output(output_file, filepath, channel)

def send_progress(channel, filepath, status):
    progress = status.get("progress", [0, 0])
    recovered_hashes = status.get("recovered_hashes", [0, 1])
    devices = status.get("devices", [])
    time_start = status.get("time_start")
    estimated_stop = status.get("estimated_stop")

    current_time = time.time()
    elapsed_time = current_time - time_start
    remaining_time = estimated_stop - current_time

    elapsed_time_str = format_time(elapsed_time)
    remaining_time_str = format_time(remaining_time)

    progress_message = {
        'filepath': filepath,
        'progress': f"{progress[0]}/{progress[1]} ({(progress[0]/progress[1])*100:.2f}%)",
        'recovered_hashes': f"{recovered_hashes[0]}/{recovered_hashes[1]}",
        'elapsed_time': elapsed_time_str,
        'remaining_time': remaining_time_str,
        'devices': devices
    }

    channel.basic_publish(exchange='', routing_key='progress_queue', body=json.dumps(progress_message))
    print("Progress sent:", progress_message)  # Вывод в консоль для дебаггинга

def format_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    elif m > 0:
        return f"{m}m {s}s"
    else:
        return f"{s}s"

def read_output(output_file, filepath, channel):
    if os.path.exists(output_file):
        with open(output_file, 'r') as f:
            results = f.readlines()
            for result in results:
                result_parts = result.strip().split(':')
                if len(result_parts) < 5:
                    print("Invalid result format:", result)
                    continue

                bssid = result_parts[1]
                ssid = result_parts[3]
                password = result_parts[4]
                success = bool(password)  # Assuming non-empty password means success

                result_message = {
                    'filepath': filepath,
                    'bssid': bssid,
                    'ssid': ssid,
                    'password': password,
                    'success': success
                }

                channel.basic_publish(exchange='', routing_key='result_queue', body=json.dumps(result_message))
                print("Result sent:", result_message)  # Вывод в консоль для дебаггинга


def on_request(ch, method, properties, body):
    request = json.loads(body)
    filepath = request.get('filepath')
    wordlist_size = request.get('wordlist_size')
    output_file = 'hashcat_output.txt'

    wordlist_file = WORDLIST_PATHS.get(wordlist_size)
    if not wordlist_file:
        print(f"Invalid wordlist size: {wordlist_size}")
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

    print(f"Received request: {request}")  # Вывод в консоль для дебаггинга
    if os.path.exists(output_file):
        os.remove(output_file)
        print(f"File {output_file} has been deleted.")
    else:
        print(f"File {output_file} does not exist.")
    run_hashcat(filepath, wordlist_file, output_file, ch)

    ch.basic_ack(delivery_tag=method.delivery_tag)

def start_service():
    RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
    RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'guest')
    RABBITMQ_PASS = os.getenv('RABBITMQ_PASS', 'guest')

    # Connection setup
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST, credentials=credentials))
    channel = connection.channel()

    channel.queue_declare(queue='request_queue')
    channel.queue_declare(queue='progress_queue')
    channel.queue_declare(queue='result_queue')

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue='request_queue', on_message_callback=on_request)

    print(f"Waiting for requests...")  # Вывод в консоль для дебаггинга
    channel.start_consuming()

start_service()
