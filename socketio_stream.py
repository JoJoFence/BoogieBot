from flask import Flask, render_template, Response, send_from_directory, url_for
from flask_socketio import SocketIO, emit
import cv2
from imutils.video import VideoStream
from picamera2 import Picamera2
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput
import threading
from threading import Condition
import serial
from serial.tools import list_ports
import time
import io
import os
import re

app = Flask(__name__)
socketio = SocketIO(app)


def detect_qr(frame):
    detector = cv2.QRCodeDetector()
    
    try:
        data, vertices, _ = detector.detectAndDecode(frame)
        if data:
            bbox = vertices[0].astype(int)
            cv2.polylines(frame, [bbox], True, (0, 255, 0), 2)
            
            # Sending detected data to socket server
            label = data.split("@")
            name = label[0]
            friend_ip_address = label[1]
            socketio.emit("qr_detected", {"name": name, "ip": friend_ip_address})
             
            # Drawing bounding box and setting name as label
            label = data.split("@")
            name = label[0]
            friend_ip_address = label[1]
            font = cv2.FONT_HERSHEY_SIMPLEX
            
            fontScale = 3.5*(bbox[1][0] - bbox[0][0]) / bbox[1][0]

            textsize = cv2.getTextSize(name, font, fontScale, 2)[0]
            textX = ((bbox[1][0] + bbox[0][0]) - textsize[0]) / 2
            textY = (bbox[0][1] - 8)
            cv2.putText(frame, name, (int(textX), int(textY)), font, fontScale, (0, 250, 50), 2)
    except:
        pass

    return frame

def generate_frames():
    # This is your existing function that captures frames from the camera
    picam2 = Picamera2()
    preview_config = picam2.create_video_configuration(main={"size": (640, 480)})
    picam2.configure(preview_config)
    picam2.start()

    while True:
        frame = picam2.capture_array()
        frame = detect_qr(frame) 
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/')
def index():
    # Return your main HTML page here
    return render_template("index.html")

@app.route('/video_feed')
def video_feed():
    # Video streaming route
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@socketio.on('command')
def handle_command(command):
    print('Received Command:', command)

    usb_serial.flush()
    usb_serial.write(command.encode())
    usb_serial.flush()
    time.sleep(0.07)
    

# Receive dance request from friend
@socketio.on('dance_request')
def handle_dance_request(data):
    print("INCOMING DANCE REQUEST FROM: " + data["name"] + "|" + data["ip"])
    print("Accept request?")
    socketio.emit("accept_request")
    
# Confirming Blockly code received
@socketio.on('confirm_code_exchange')
def handle_confirm_code(data):
    # Check confirmation status
    if (data["confirmed"]):
        print("DANCE ACCEPTED BY " + data["name"] + "|" + data["ip"])
        socketio.emit("enable_boogie_button", data)
    
@socketio.on('execute_dance')
def handle_dance_code(data):
    print("DANCE CODE:", data)
    dance_moves = str(data).split('\n')

    repeat = 1
    if "count" in data:
        repeat = int(re.search("< (.*?);", str(data)).group(1))
        dance_moves = str(re.search("{\n  (.*)\n}", str(data)).group(1))
        dance_moves = dance_moves.split('\n')
    
    dance_moves.append("Z;150:0>")  # Always end dance routine by stopping robot
    
    for i in range(repeat):
        print(dance_moves)
        for move in dance_moves:
            usb_serial.flush()
            usb_serial.write(move.encode())
            usb_serial.flush()
            time.sleep(0.07)
            
    socketio.emit('dance_finished')
    
    
if __name__ == '__main__':
    usb_ports = list(list_ports.comports())
    for p in usb_ports:
        teensy_port = str(p.device)

    usb_serial = serial.Serial(teensy_port, 9600, timeout=10)
    if usb_serial.isOpen() == False:
        usb_serial.open()    
    time.sleep(2)

    print("USB Connection Initialized.")

    socketio.run(app, host='0.0.0.0', port=5000)
