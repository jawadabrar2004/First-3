First 4 — Emergency Response Drone + Dispatcher Dashboard

The first 4 minutes change lives. First 4 sends a drone to a 911 caller before ground units arrive. It gives the dispatcher eyes on scene and drops medical supplies to the people who need them. Giving ground units more information to spring into action. 

The problem:

When someone calls 911, the dispatcher only has what the caller can describe, and the first ambulance or police car can be minutes away. In a cardiac arrest, an overdose or a severe bleed, those minutes decide the outcome. We talked with 911 dispatch centers while designing this. The gap they described is information and first aid in the time before responders reach the scene.

"Having a live feed as a dispatcher would be great especially since bystanders are in a panic and I can get the info before crew arrives on scene" - Stamford Dispatcher 

What it does:

- Dispatcher dashboard: The dispatcher answers the call, sees the caller's number and location, and assigns the drone with the appropriate payload to the scene.
- Eyes on scene: The drone streams a live camera feed to the dashboard, with a Day and InfraRed view for night and low visibility.
- Computer vision: The ground station runs detection on the drone feed to count people on scene and flag someone who is down or needs help.
- Medical payload drop: A servo release drops a crisis kit (for example a bleeding-control kit or naloxone) at the caller's location.
- HUD Display: A HUD display for the dispatcher showing a mini-map of the drone and its location, alerts from CV analyzation, live call transcription with status updates, and telemetry data regarding the drone. 

How it works:

 ┌─────────────────────────── DRONE ───────────────────────────┐
 │  Flight controller (MicoAir) ── servo payload release       │
 │  Raspberry Pi 5 ── Pi camera (day) + Pi IR camera (night)   │
 │  ESP32 camera                                  
 └──────────────┬──────────────────────────────────────────────┘
                │ video + audio stream            
                ▼                                  
 ┌──────────────────────── GROUND STATION ─────────────────────┐
 │  Computer vision (people count, person down)                │
 │  Call transcription                                         │
 │  Dispatcher dashboard (this repo): call, drones, feed, notes│
 └─────────────────────────────────────────────────────────────┘


The Pi only streams the camera feeds. All heavy computation (CV and transcription) runs on the ground station, so the drone stays light and its battery lasts longer.

Hardware:

| Part | Use |
| 7" deadcat frame | Airframe, keeps the props out of the camera view |
| 1300KV motors | Lift for a 7" setup carrying a payload |
| MicoAir flight controller | Flight control |
| Bluejay 60A 4-in-1 ESC | Motor Control |
| Taranis X9D Plus 2019  | Radio Link and Telemetry |
| Raspberry Pi 5 | Onboard streaming computer |
| Pi camera module + Pi IR camera module | Day and night video |
| ESP32 camera module | Payload-mounted view |
| Servo + release mechanism | Payload drop |



Team Contributions:

| Name | Focus/Built |
Javier Serrano | UI/UX for Dispatcher, Market research, Demo Orchestrator | 
Abrar Jawad |  Machine Vision, CAD, Electronics, Power Management |
Kyle Burke | Drone mechanics and programming, camera, processor, and battery mounts |
Biraj Patel| Paylod remote communication device, Test and setup Ras PI 5 setup with InfraRed and regular cam |


What we built vs. what we used:

Everything here was built during the hackathon. We used these open-source projects and libraries and give them full credit:

| Ultralytics YOLO11 (`yolo11n-pose` model) | Person and pose detection on the drone's day camera feed. We integrated it into the dashboard UI/UX we designed. | AGPL-3.0 | https://github.com/ultralytics/ultralytics |
| PyTorch | Runs the YOLO model (installed with Ultralytics) | BSD-3-Clause | https://github.com/pytorch/pytorch |
| NCNN | Runs the exported YOLO model faster on the Raspberry Pi 5 | BSD-3-Clause | https://github.com/Tencent/ncnn |
| OpenCV (`opencv-python`) | Reads the camera streams and draws the detection boxes | Apache-2.0 (OpenCV), MIT (Python package) | https://github.com/opencv/opencv |
| FFmpeg | Video decoding inside OpenCV (RTSP stream from the Pi) | LGPL-2.1+ | https://ffmpeg.org |
| NumPy | Image and number crunching for the CV pipeline | BSD-3-Clause | https://github.com/numpy/numpy |
|ArduPilot| Flight control firmware |
| MediaMTX | Streams the Pi's day and IR cameras to the dashboard (WebRTC + RTSP) and records them | MIT | https://github.com/bluenviron/mediamtx |
| rpicam-apps | Captures video from the Pi camera modules | BSD-2-Clause | https://github.com/raspberrypi/rpicam-apps |
| libcamera | Camera driver stack on the Raspberry Pi | LGPL-2.1+ | https://libcamera.org |
| Picamera2 | Python access to the Pi camera for machine vision on the Pi | BSD-2-Clause | https://github.com/raspberrypi/picamera2 |
| Python | Language the dashboard server and machine vision run on | PSF License | https://www.python.org |
| FastAPI | Dashboard server: web page, live updates, dispatcher actions | MIT | https://github.com/fastapi/fastapi |
| Starlette | Web framework underneath FastAPI | BSD-3-Clause | https://github.com/encode/starlette |
| Pydantic | Checks the data sent to the dashboard server | MIT | https://github.com/pydantic/pydantic |
| Uvicorn | Runs the dashboard server | BSD-3-Clause | https://github.com/encode/uvicorn |
| websockets | Live WebSocket connection between the server and the dashboard | BSD-3-Clause | https://github.com/python-websockets/websockets |
| python-multipart | Lets the server receive audio uploads | Apache-2.0 | https://github.com/Kludex/python-multipart |
| Node.js | Serves the separate call page | MIT | https://nodejs.org |
| Leaflet | Search-zone minimap and on-scene map | BSD-2-Clause | https://github.com/Leaflet/Leaflet |
| OpenStreetMap | Map tiles and map data | ODbL (data) | https://www.openstreetmap.org/copyright |
| Public Sans | Dashboard font | SIL OFL 1.1 | https://github.com/uswds/public-sans |
| JetBrains Mono | Dashboard font for numbers and telemetry | SIL OFL 1.1 | https://github.com/JetBrains/JetBrainsMono |

Our own work: the drone build and payload drop mechanism, the dispatcher dashboard (UI/UX design and code), connecting the Pi camera streams to the ground station, and wiring the CV output and transcription into the dispatcher's view.

Run the dashboard:

You need Node.js 18 or newer. There's no `npm install`.

- Mac: double-click `start-mac.command` (the first time, right-click it and choose Open)
- Windows: double-click `start-windows.bat`
- Terminal: `node server.js`

The start scripts open http://localhost:4000 in your browser for you; from the terminal, open it yourself. Press Ctrl+C (or close the window) to stop.

Right now the call is demo data (`CALL` at the top of `js/call.js`), and notes aren't saved. Reload the page to start over.


What's next

- Live call data from a real CAD/911 system instead of demo data
- GPS-based auto-dispatch of the nearest drone to the caller's location
- Testing the payload drop with dispatch partners

