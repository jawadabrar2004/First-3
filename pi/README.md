# Raspberry Pi camera server

The Pi 5 streams two cameras with [MediaMTX](https://github.com/bluenviron/mediamtx). The dispatch console shows them in its video panel.

| Camera | WebRTC (dispatch console) | RTSP (computer vision) |
|---|---|---|
| Day (camera 0) | `http://raspberrypi.local:8889/cam` | `rtsp://raspberrypi.local:8554/cam` |
| IR (camera 1) | `http://raspberrypi.local:8889/ir` | `rtsp://raspberrypi.local:8554/ir` |

## 1. Connect the cameras

- The Pi 5 uses the **small 22-pin camera connector**, not the wide 15-pin one on older Pis and most camera modules. You need a **Pi 5 camera cable (22-pin to 15-pin)**. The standard cable that comes with the camera won't fit.
- Turn the Pi **off** before plugging cables in. Lift the connector latch, insert the cable fully with its contacts lined up with the connector's contacts, and press the latch down. The [Raspberry Pi camera docs](https://www.raspberrypi.com/documentation/accessories/camera.html) have photos of the right orientation.
- The Pi 5 has two ports, **CAM/DISP 0** and **CAM/DISP 1**. Put the day camera in **0** and the IR camera in **1**.

## 2. Check the Pi sees both cameras

```bash
rpicam-hello --list-cameras
```

You should see two cameras, numbered `0` and `1`. If one is missing, re-seat its cable (with the Pi off). Day = `0` and IR = `1` must match the order in step 1; if they're swapped, swap `rpiCameraCamID` in `/usr/local/etc/mediamtx.yml`.

## 3. Install MediaMTX

Copy `setup_mediamtx.sh` to the Pi (or `git clone` this repo on the Pi), then:

```bash
sudo bash setup_mediamtx.sh
```

It downloads the latest MediaMTX for 64-bit ARM, installs it to `/usr/local/bin`, writes `/usr/local/etc/mediamtx.yml` (both cameras at 1280×720, software H.264), and sets it up as a service that starts on boot. Running it again updates MediaMTX and backs up the old config first.

## 4. Manage the service

```bash
sudo systemctl status mediamtx      # is it running?
sudo systemctl restart mediamtx     # restart (e.g. after editing the config)
sudo systemctl stop mediamtx        # stop
journalctl -u mediamtx -f           # live logs (Ctrl+C to quit)
journalctl -u mediamtx -n 50 --no-pager   # last 50 log lines
```

## 5. Test from the Windows laptop

The laptop and Pi must be on the same network (same Wi-Fi or phone hotspot). In PowerShell:

```powershell
Test-NetConnection raspberrypi.local -Port 8889
```

`TcpTestSucceeded : True` means the camera server is reachable. Then open `http://raspberrypi.local:8889/cam` in a browser; you should see the day camera.

## IPv6 / IPv4 tip (phone hotspots)

On a phone hotspot, `raspberrypi.local` often resolves to an **IPv6** address, and WebRTC can fail over IPv6: the page loads but the video stays black. Use the Pi's **IPv4** address instead:

1. On the Pi, run `hostname -I`. Use the address that looks like `172.20.10.14` or `192.168.x.x`, not the long one with colons.
2. Test it: `Test-NetConnection 172.20.10.14 -Port 8889`
3. Put it in the dispatch console as `PI_HOST` (see the main README, "Raspberry Pi cameras").

The hotspot can give the Pi a different address after it reconnects, so check `hostname -I` again if the video stops working.
