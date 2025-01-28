# -*- coding: utf-8 -*-

import cv2
import asyncio
import websockets
import json
import base64
import uuid
import logging
import sys
from datetime import datetime

# 로깅 설정
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
        self.connected_clients = set()
        self.logger = logging.getLogger(name)
        
    async def start_server(self, websocket_url='192.168.227.252', websocket_port=8765):
        self.logger.info(f"Starting server with camera ID: {self.camera_id}")
        try:
            self.relay_ws = await websockets.connect(
                f'ws://{websocket_url}:{websocket_port}/register',
                ping_interval=20,
                ping_timeout=20
            )
            self.logger.info("Connected to relay server")
            
            # 서버 등록
            register_message = {
                'type': 'register',
                'server_id': self.server_id,
                'name': self.name
            }
            await self.relay_ws.send(json.dumps(register_message))
            self.logger.info(f"Registered with server_id: {self.server_id}")
            
            # 카메라 초기화
            self.cap = cv2.VideoCapture(self.camera_id)
            if not self.cap.isOpened():
                self.logger.error(f"Failed to open camera {self.camera_id}")
                return
                
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
            self.logger.info("Camera initialized successfully")
            
            frame_count = 0
            last_log_time = datetime.now()

            while True:
                try:
                    ret, frame = self.cap.read()
                    if not ret:
                        self.logger.warning("Failed to read frame")
                        continue
                        
                    frame_count += 1
                    current_time = datetime.now()
                    if (current_time - last_log_time).seconds >= 5:  # 5초마다 로그 출력
                        self.logger.debug(f"Frame captured. Shape: {frame.shape}, Count: {frame_count}")
                        last_log_time = current_time
                    
                    # JPEG으로 인코딩
                    _, buffer = cv2.imencode('.jpg', frame)
                    # base64로 인코딩
                    jpg_as_text = base64.b64encode(buffer).decode()
                    
                    # 스트림 데이터 전송
                    message = {
                        'type': 'stream',
                        'server_id': self.server_id,
                        'data': jpg_as_text
                    }
                    await self.relay_ws.send(json.dumps(message))
                    
                    await asyncio.sleep(0.033)  # ~30fps
                    
                except websockets.exceptions.ConnectionClosed:
                    self.logger.error("WebSocket connection closed")
                    await self.reconnect(websocket_url, websocket_port)
                except Exception as e:
                    self.logger.error(f"Error during streaming: {e}")
                    await asyncio.sleep(1)  # 에러 발생시 1초 대기
                    
        except Exception as e:
            self.logger.error(f"Failed to connect to relay server: {e}")
            raise

    async def reconnect(self, websocket_url, websocket_port):
        """연결이 끊어졌을 때 재연결을 시도하는 메서드"""
        while True:
            try:
                self.logger.info("Attempting to reconnect...")
                await self.start_server(websocket_url, websocket_port)
                break
            except Exception as e:
                self.logger.error(f"Reconnection failed: {e}")
                await asyncio.sleep(5)  # 5초 후 재시도
                
    def __del__(self):
        if self.cap:
            self.cap.release()
            self.logger.info("Camera released")

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
            await asyncio.sleep(5)  # 5초 후 재시도
        
if __name__ == "__main__":
    asyncio.run(main())