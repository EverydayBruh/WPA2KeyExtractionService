import os
import uuid
import json
from flask import Flask, request, jsonify
import pika
from werkzeug.utils import secure_filename

app = Flask(__name__)

UPLOAD_FOLDER = '/uploads'
ALLOWED_EXTENSIONS = {'hc22000', 'cap'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def send_rabbitmq_request(request_data, method):
    RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
    RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'guest')
    RABBITMQ_PASS = os.getenv('RABBITMQ_PASS', 'guest')

    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST, credentials=credentials))
    channel = connection.channel()

    channel.queue_declare(queue='api_request_queue')

    result = channel.queue_declare(queue='', exclusive=True)
    callback_queue = result.method.queue

    correlation_id = str(uuid.uuid4())

    channel.basic_publish(
        exchange='',
        routing_key='api_request_queue',
        properties=pika.BasicProperties(
            reply_to=callback_queue,
            correlation_id=correlation_id,
            headers={'method': method}  # Добавляем метод HTTP-запроса в заголовки
        ),
        body=json.dumps(request_data)
    )

    for method_frame, properties, body in channel.consume(callback_queue):
        if properties.correlation_id == correlation_id:
            channel.basic_ack(method_frame.delivery_tag)
            connection.close()
            return json.loads(body)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        request_data = {
            'filepath': filepath,
            'bssid': request.form.get('bssid'),
            'ssid': request.form.get('ssid')
        }
        
        response = send_rabbitmq_request(request_data, 'POST')
        
        return jsonify(response), 200
    return jsonify({'error': 'File type not allowed'}), 400

@app.route('/status/<path:filename>', methods=['GET'])
def get_status(filename):
    request_data = {
        'filepath': os.path.join(app.config['UPLOAD_FOLDER'], filename)
    }
    
    response = send_rabbitmq_request(request_data, 'GET')
    
    return jsonify(response), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)