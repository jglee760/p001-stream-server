import cv2
import numpy as np
import asyncio
import websockets
import json
import base64
import uuid
import logging
import sys
from datetime import datetime

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

class VideoStreamServer:
    def __init__(self, name, camera_id=0):
        self.name = name
        self.camera_id = camera_id
        self.server_id = str(uuid.uuid4())
        self.cap = None
        self.is_selected = False
        self.logger = logging.getLogger(name)
        
    async def start_server(self, websocket_url='192.168.227.252', websocket_port=8765):
        self.logger.info(f"Starting server with camera ID: {self.camera_id}")
        try:
            self.relay_ws = await websockets.connect(
                f'ws://{websocket_url}:{websocket_port}/register',
                ping_interval=20,
                ping_timeout=20
            )
            
            # 서버 등록
            register_message = {
                'type': 'register',
                'server_id': self.server_id,
                'name': self.name
            }
            await self.relay_ws.send(json.dumps(register_message))
            
            # 카메라 초기화
            self.cap = cv2.VideoCapture(self.camera_id)
            if not self.cap.isOpened():
                self.logger.error(f"Failed to open camera {self.camera_id}")
                return
                
            frame_count = 0
            last_log_time = datetime.now()

            while True:
                try:
                    ret, frame = self.cap.read()
                    if not ret:
                        continue
                        
                    frame_count += 1
                    current_time = datetime.now()
                    if (current_time - last_log_time).seconds >= 5:
                        self.logger.debug(f"Frame captured. Count: {frame_count}")
                        last_log_time = current_time

                    # 작은 썸네일 생성 (160x120)
                    thumbnail = cv2.resize(frame, (160, 120))
                    
                    # 스트림 데이터 전송 준비
                    if self.is_selected:
                        # 선택된 경우 640x480 크기로 전송
                        frame = cv2.resize(frame, (640, 480))
                        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                    else:
                        # 선택되지 않은 경우 작은 썸네일 전송
                        _, buffer = cv2.imencode('.jpg', thumbnail, [cv2.IMWRITE_JPEG_QUALITY, 75])
                    
                    jpg_as_text = base64.b64encode(buffer).decode()
                    
                    message = {
                        'type': 'stream',
                        'server_id': self.server_id,
                        'data': jpg_as_text,
                        'is_selected': self.is_selected
                    }
                    await self.relay_ws.send(json.dumps(message))
                    
                    # 프레임 레이트 조절
                    if self.is_selected:
                        await asyncio.sleep(0.033)  # 선택된 영상 ~30fps
                    else:
                        await asyncio.sleep(0.1)    # 선택되지 않은 영상 ~10fps
                    
                except websockets.exceptions.ConnectionClosed:
                    self.logger.error("WebSocket connection closed")
                    await self.reconnect(websocket_url, websocket_port)
                except Exception as e:
                    self.logger.error(f"Error during streaming: {e}")
                    await asyncio.sleep(1)
                    
        except Exception as e:
            self.logger.error(f"Failed to connect to relay server: {e}")
            raise

    async def handle_message(self, message):
        try:
            data = json.loads(message)
            if data.get('type') == 'select' and data.get('server_id') == self.server_id:
                self.is_selected = data.get('selected', False)
                self.logger.info(f"Stream selection changed: {self.is_selected}")
        except Exception as e:
            self.logger.error(f"Error handling message: {e}")

    async def reconnect(self, websocket_url, websocket_port):
        while True:
            try:
                self.logger.info("Attempting to reconnect...")
                await self.start_server(websocket_url, websocket_port)
                break
            except Exception as e:
                self.logger.error(f"Reconnection failed: {e}")
                await asyncio.sleep(5)
                
    def __del__(self):
        if self.cap:
            self.cap.release()

async def main():
    server = VideoStreamServer("Camera 1")
    while True:
        try:
            await server.start_server()
        except KeyboardInterrupt:
            logging.info("Shutting down server...")
            break
        except Exception as e:
            logging.error(f"Server error: {e}")
            await asyncio.sleep(5)
        
if __name__ == "__main__":
    asyncio.run(main())