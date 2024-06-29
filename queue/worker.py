import pika
import json
import os
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, func
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "sqlite:///./data/handshakes.db"

Base = declarative_base()
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Handshake(Base):
    __tablename__ = "handshakes"
    id = Column(Integer, primary_key=True, index=True)
    filepath = Column(String, unique=True, index=True)
    bssid = Column(String)
    ssid = Column(String)
    elapsed_time = Column(String)
    estimated_remaining_time = Column(String)
    progress = Column(String)
    device_info = Column(String)
    password = Column(String)
    processed = Column(Boolean, default=False)
    in_process = Column(Boolean, default=False)
    success = Column(Boolean, default=False)

Base.metadata.create_all(bind=engine)

def send_to_processor_queue(channel, handshake):
    channel.queue_declare(queue='request_queue')
    message = {
        'filepath': handshake.filepath,
        'wordlist_size': 1
    }
    channel.basic_publish(exchange='',
                          routing_key='request_queue',
                          body=json.dumps(message))
    print(f"Handshake sent to processor queue: {handshake.filepath}")

def add_handshake_to_db(session, filepath, bssid, ssid):
    existing_handshake = session.query(Handshake).filter(Handshake.filepath == filepath).first()
    if existing_handshake:
        print(f"Duplicate handshake found: {filepath}")
        return existing_handshake
    
    new_handshake = Handshake(
        filepath=filepath,
        bssid=bssid,
        ssid=ssid
    )
    session.add(new_handshake)
    session.commit()
    print(f"Handshake added to DB: {filepath}")
    return new_handshake

def update_handshake_progress(session, filepath, progress_data):
    handshake = session.query(Handshake).filter(Handshake.filepath == filepath).first()
    if handshake:
        handshake.progress = progress_data['progress']
        handshake.elapsed_time = progress_data['elapsed_time']
        handshake.estimated_remaining_time = progress_data['remaining_time']
        handshake.device_info = json.dumps(progress_data['devices'])
        session.commit()
        print(f"Updated progress for handshake: {filepath}")
    else:
        print(f"Handshake not found: {filepath}")


def update_handshake_result(session, filepath, bssid, ssid, password, success):
    handshake = session.query(Handshake).filter(Handshake.filepath == filepath).first()
    if handshake:
        handshake.password = password
        handshake.bssid = bssid
        handshake.ssid = ssid
        handshake.processed = True
        handshake.in_process = False
        handshake.success = success
        session.commit()
        print(f"Updated result for handshake: BSSID={bssid}, SSID={ssid}")
    else:
        print(f"Handshake not found: BSSID={bssid}, SSID={ssid}")


def progress_callback(ch, method, properties, body):
    data = json.loads(body)
    filepath = data.get('filepath')
    
    session = SessionLocal()
    update_handshake_progress(session, filepath, data)
    session.close()


def result_callback(ch, method, properties, body):
    data = json.loads(body)
    filepath = data.get('filepath')
    bssid = data.get('bssid')
    ssid = data.get('ssid')
    password = data.get('password')
    success = data.get('success')
    
    session = SessionLocal()
    update_handshake_result(session, filepath, bssid, ssid, password, success)
    session.close()

def handle_api_request(ch, method, properties, body):
    data = json.loads(body)
    filepath = data.get('filepath')
    bssid = data.get('bssid')
    ssid = data.get('ssid')

    http_method = properties.headers.get('method', 'GET')

    session = SessionLocal()
    
    handshake = session.query(Handshake).filter(Handshake.filepath == filepath).first()
    
    if http_method == 'POST' and not handshake:
        handshake = add_handshake_to_db(session, filepath, bssid, ssid)
    
    response = {}
    
    if handshake:
        if handshake.in_process:
            response = {
                'status': 'in_process',
                'elapsed_time': handshake.elapsed_time,
                'estimated_remaining_time': handshake.estimated_remaining_time,
                'progress': handshake.progress,
                'device_info': json.loads(handshake.device_info) if handshake.device_info else None
            }
        elif not handshake.processed:
            if http_method == 'POST':
                send_to_processor_queue(ch, handshake)
            position = session.query(func.count(Handshake.id)).filter(
                Handshake.processed == False,
                Handshake.id <= handshake.id
            ).scalar()
            response = {
                'status': 'queued',
                'position': position
            }
        else:
            response = {
                'status': 'processed',
                'success': handshake.success,
                'password': handshake.password if handshake.success else None
            }
    else:
        response = {
            'status': 'not_found',
            'message': 'Handshake not found in database'
        }
    
    session.close()

    ch.basic_publish(exchange='',
                     routing_key=properties.reply_to,
                     properties=pika.BasicProperties(correlation_id=properties.correlation_id),
                     body=json.dumps(response))
    
    ch.basic_ack(delivery_tag=method.delivery_tag)

def process_unprocessed_handshakes(channel):  
    
    session = SessionLocal()
    if session.query(Handshake).filter(Handshake.in_process == True).count() > 0:
        return 1
    
    unprocessed_handshakes = session.query(Handshake).filter(
        Handshake.processed == False,
        Handshake.in_process == False
    ).order_by(Handshake.id).all()

    for handshake in unprocessed_handshakes:
        handshake.in_process = True
        session.commit()
        send_to_processor_queue(channel, handshake)

    session.close()
    return 0

def start_worker():
    print(f'start_worker')
    RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
    RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'guest')
    RABBITMQ_PASS = os.getenv('RABBITMQ_PASS', 'guest')

    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST, credentials=credentials))
    channel = connection.channel()

    channel.queue_declare(queue='request_queue')
    channel.queue_declare(queue='progress_queue')
    channel.queue_declare(queue='result_queue')
    channel.queue_declare(queue='api_request_queue')

    channel.basic_consume(queue='progress_queue', on_message_callback=progress_callback, auto_ack=True)
    channel.basic_consume(queue='result_queue', on_message_callback=result_callback, auto_ack=True)
    channel.basic_consume(queue='api_request_queue', on_message_callback=handle_api_request)

    print(f'Waiting for messages. To exit press CTRL+C')

    # Обработка необработанных handshake'ов при запуске
    process_unprocessed_handshakes(channel)

    # Периодическая проверка и обработка необработанных handshake'ов
    def check_unprocessed():
        process_unprocessed_handshakes(channel)
        connection.call_later(30, check_unprocessed) 

    connection.call_later(30, check_unprocessed)

    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    
    connection.close()

start_worker()