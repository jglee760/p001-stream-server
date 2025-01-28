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
        self.is_selected = False
        self.logger = logging.getLogger(name)
        self.running = False
        
    def process_high_quality_frame(self, frame):
        """고품질 프레임 처리 메소드"""
        try:
            # 노이즈 제거
            denoised = cv2.fastNlMeansDenoisingColored(frame, None, 10, 10, 7, 21)
            
            # 선명도 개선
            kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
            sharpened = cv2.filter2D(denoised, -1, kernel)
            
            # 크기 조정 (320x240)
            return cv2.resize(sharpened, (320, 240), interpolation=cv2.INTER_LANCZOS4)
        except Exception as e:
            self.logger.error(f"Error processing high quality frame: {e}")
            # 에러 발생 시 기본 리사이징만 수행
            return cv2.resize(frame, (320, 240), interpolation=cv2.INTER_AREA)

    async def handle_message(self, message):
        try:
            data = json.loads(message)
            if data.get('type') == 'select':
                old_state = self.is_selected
                self.is_selected = data.get('selected', False)
                self.logger.info(f"Stream selection changed: {old_state} -> {self.is_selected}")
        except Exception as e:
            self.logger.error(f"Error handling message: {e}")

    async def stream_video(self):
        frame_count = 0
        last_log_time = datetime.now()

        while self.running:
            try:
                ret, frame = self.cap.read()
                if not ret:
                    self.logger.warning("Failed to read frame")
                    continue

                frame_count += 1
                current_time = datetime.now()
                if (current_time - last_log_time).seconds >= 5:
                    self.logger.debug(f"Frame captured. Count: {frame_count}")
                    last_log_time = current_time

                # 항상 작은 썸네일 생성
                thumbnail = cv2.resize(frame, (80, 60), interpolation=cv2.INTER_AREA)
                
                if self.is_selected:
                    # 선택된 경우 고품질 스트림 전송 (320x240)
                    processed_frame = self.process_high_quality_frame(frame)
                    encode_params = [
                        cv2.IMWRITE_JPEG_QUALITY, 98,
                        cv2.IMWRITE_JPEG_OPTIMIZE, 1,
                        cv2.IMWRITE_JPEG_PROGRESSIVE, 1
                    ]
                    _, buffer = cv2.imencode('.jpg', processed_frame, encode_params)
                else:
                    # 선택되지 않은 경우 썸네일 전송
                    encode_params = [
                        cv2.IMWRITE_JPEG_QUALITY, 85,
                        cv2.IMWRITE_JPEG_OPTIMIZE, 1
                    ]
                    _, buffer = cv2.imencode('.jpg', thumbnail, encode_params)

                # 스트림 데이터 전송
                message = {
                    'type': 'stream',
                    'server_id': self.server_id,
                    'data': base64.b64encode(buffer).decode(),
                    'is_selected': self.is_selected
                }
                await self.relay_ws.send(json.dumps(message))

                # 프레임 레이트 조절
                await asyncio.sleep(0.033 if self.is_selected else 0.1)

            except Exception as e:
                self.logger.error(f"Error during streaming: {e}")
                await asyncio.sleep(1)

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

            self.running = True
            video_task = asyncio.create_task(self.stream_video())
            
            try:
                async for message in self.relay_ws:
                    await self.handle_message(message)
            except websockets.exceptions.ConnectionClosed:
                self.logger.error("WebSocket connection closed")
                self.running = False
                await video_task
                await self.reconnect(websocket_url, websocket_port)
            
        except Exception as e:
            self.logger.error(f"Failed to connect to relay server: {e}")
            self.running = False
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
                await asyncio.sleep(5)
                
    def __del__(self):
        self.running = False
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
            await asyncio.sleep(5)
        
if __name__ == "__main__":
    asyncio.run(main())