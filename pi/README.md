# Raspberry Pi camera server

The Pi 5 streams two cameras with [MediaMTX](https://github.com/bluenviron/mediamtx). The dispatch console shows them in its video panel.

| Camera | WebRTC (dispatch console) | RTSP (computer vision) |
|---|---|---|
| Day: imx708, Camera Module 3 (camera 1) | `http://raspberrypi.local:8889/cam` | `rtsp://raspberrypi.local:8554/cam` |
| IR: imx219, NoIR (camera 0) | `http://raspberrypi.local:8889/ir` | `rtsp://raspberrypi.local:8554/ir` |

## 1. Connect the cameras

- The Pi 5 uses the **small 22-pin camera connector**, not the wide 15-pin one on older Pis and most camera modules. You need a **Pi 5 camera cable (22-pin to 15-pin)**. The standard cable that comes with the camera won't fit.
- Turn the Pi **off** before plugging cables in. Lift the connector latch, insert the cable fully with its contacts lined up with the connector's contacts, and press the latch down. The [Raspberry Pi camera docs](https://www.raspberrypi.com/documentation/accessories/camera.html) have photos of the right orientation.
- The Pi 5 has two ports, **CAM/DISP 0** and **CAM/DISP 1**. On our Pi the **IR camera (imx219) is camera 0** and the **day camera (imx708) is camera 1**.

## 2. Check the Pi sees both cameras

```bash
rpicam-hello --list-cameras
```

You should see two cameras: `0` = **imx219** (IR) and `1` = **imx708** (day). If one is missing, re-seat its cable (with the Pi off). If the numbers come out the other way round, swap the two `rpiCameraCamID` values in `pi/mediamtx.yml` and run the setup script again.

## 3. Install MediaMTX

Copy the whole `pi/` folder to the Pi (`setup_mediamtx.sh` needs `mediamtx.yml` next to it), or `git clone` this repo on the Pi, then in that folder:

```bash
sudo bash setup_mediamtx.sh
```

It downloads the latest MediaMTX for 64-bit ARM, installs it to `/usr/local/bin`, installs `mediamtx.yml` as `/usr/local/etc/mediamtx.yml`, and sets it up as a service that starts on boot. Running it again updates MediaMTX and backs up the old config first.

### Stream settings (`pi/mediamtx.yml`)

| Path | Camera | Size | Frame rate | Bitrate | Full picture every |
|---|---|---|---|---|---|
| `cam` | 1 (imx708, day) | 960×540 | 15 fps | 1.5 Mbps | 15 frames (1 s) |
| `ir` | 0 (imx219, IR) | 640×480 | 10 fps | 0.8 Mbps | 10 frames (1 s) |

Both use `softwareH264` (the Pi 5 has no hardware H.264 encoder). These are the settings that worked on the phone hotspot: about 2.3 Mbps for both streams together, and a full picture every second so the video recovers quickly after a drop. To change them, edit `pi/mediamtx.yml` and run `sudo bash setup_mediamtx.sh` again (or copy the file to `/usr/local/etc/mediamtx.yml` and `sudo systemctl restart mediamtx`).

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
