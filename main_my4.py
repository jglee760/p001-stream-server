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
    def __init__(self, name, video_path):
        self.name = name
        self.video_path = video_path
        self.server_id = str(uuid.uuid4())
        self.cap = None
        self.connected_clients = set()
        self.logger = logging.getLogger(name)

    async def start_server(self, websocket_url='192.168.227.252', websocket_port=8765):
        self.logger.info(f"Starting server with video: {self.video_path}")
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

            # 동영상 파일 초기화
            self.cap = cv2.VideoCapture(self.video_path)
            if not self.cap.isOpened():
                self.logger.error(f"Failed to open video file: {self.video_path}")
                return

            frame_count = 0
            last_log_time = datetime.now()

            while True:
                try:
                    ret, frame = self.cap.read()
                    if not ret:
                        self.logger.info("End of video reached. Restarting...")
                        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # 첫 프레임으로 이동
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
            self.logger.info("Video capture released")

async def main():
    video_path = "video.mp4"  # MP4 파일 경로 설정
    server = VideoStreamServer("Video Stream Server", video_path)
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
