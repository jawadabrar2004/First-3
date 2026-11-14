// =====================================================================
// video.js - mock mode video (VIDEO_MODE = "mock" in config.js).
// Reads VIDEO_SOURCE from config.js and builds the right HTML element in
// the Day pane. camera.js mirrors it into the IR pane (in grey).
// =====================================================================

const TYPE_NAMES = {
  webcam: "Laptop camera",
  mjpeg: "MJPEG stream",
  webrtc: "WebRTC stream",
  file: "Demo video file",
};

function startVideo(source) {
  const stage = document.getElementById("feed-day");
  stage.innerHTML = "";
  setVideoLabel(TYPE_NAMES[source.type] || source.type);

  if (source.type === "webcam") {
    startLaptopCamera(source.camera);

  } else if (source.type === "mjpeg") {
    // MJPEG streams work directly in an <img> tag
    const img = document.createElement("img");
    img.src = source.url;
    img.alt = "Drone camera";
    img.onerror = () => showVideoError("Can't reach the MJPEG stream at " + source.url);
    stage.appendChild(img);

  } else if (source.type === "webrtc") {
    // MediaMTX serves a ready-made WebRTC player page; we just embed it
    const frame = document.createElement("iframe");
    frame.src = source.url;
    frame.title = "Drone camera";
    frame.allow = "autoplay; fullscreen";
    stage.appendChild(frame);

  } else if (source.type === "file") {
    const video = makeVideoElement();
    video.src = source.url;
    video.loop = true;
    video.onerror = () => showVideoError("Can't load the video file " + source.url);
    stage.appendChild(video);

  } else {
    showVideoError('Unknown VIDEO_SOURCE type "' + source.type + '". Check static/config.js.');
  }
}

// ---------------------------------------------------------------------
// Laptop camera
// ---------------------------------------------------------------------

// Words that mean "not the real built-in camera" (virtual cameras, phones, etc.)
const NOT_BUILT_IN = /virtual|obs|droid|phone|link|snap|broadcast|ndi|iriun|epoccam|manycam|xsplit|ir camera|infrared/i;
// Words that usually mean the built-in camera
const BUILT_IN = /integrated|built-?in|facetime|avstream|front|hd webcam|user facing|internal/i;

async function startLaptopCamera(wantedName) {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    showVideoError("This browser can't use the camera. Open the page at http://localhost:8000 (not an IP address or file).");
    return;
  }

  try {
    // 1. Ask for any camera first. This shows the browser's permission
    //    prompt, and after it the camera names become readable.
    let stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });

    // 2. Find the laptop's camera in the list and switch to it if needed
    const cameras = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "videoinput");
    const current = stream.getVideoTracks()[0].getSettings().deviceId;
    const best = pickCamera(cameras, wantedName);
    if (best && best.deviceId && best.deviceId !== current) {
      stream.getTracks().forEach((t) => t.stop());
      stream = await navigator.mediaDevices.getUserMedia({
        video: { deviceId: { exact: best.deviceId }, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
    }

    // 3. Show it
    const video = makeVideoElement();
    video.srcObject = stream;
    document.getElementById("feed-day").replaceChildren(video);

    const label = stream.getVideoTracks()[0].label || "Laptop camera";
    setVideoLabel(label);
    console.log("Drone camera (mock) is using:", label, "| cameras found:", cameras.map((c) => c.label));
  } catch (err) {
    showVideoError(cameraErrorMessage(err));
    console.error("Camera error:", err);
  }
}

// Choose which camera to use: the one named in config.js, otherwise the built-in one
function pickCamera(cameras, wantedName) {
  if (wantedName) {
    const named = cameras.find((c) => c.label.toLowerCase().includes(wantedName.toLowerCase()));
    if (named) return named;
  }
  return (
    cameras.find((c) => BUILT_IN.test(c.label) && !NOT_BUILT_IN.test(c.label)) ||
    cameras.find((c) => !NOT_BUILT_IN.test(c.label)) ||
    cameras[0]
  );
}

// Turn the browser's error into something a person can act on
function cameraErrorMessage(err) {
  switch (err.name) {
    case "NotAllowedError":
      return "Camera access is blocked. Click the camera icon in the address bar, choose Allow, then reload the page. " +
             "If it's still blocked: Windows Settings > Privacy & security > Camera > let desktop apps / your browser use the camera.";
    case "NotReadableError":
    case "TrackStartError":
      return "The laptop camera is being used by another app (Camera, Teams, Zoom, another browser tab...). Close it and reload the page.";
    case "NotFoundError":
    case "OverconstrainedError":
      return "No camera was found. Check the laptop camera is turned on (some laptops have a camera switch or F-key).";
    default:
      return "Camera unavailable: " + err.message;
  }
}

function makeVideoElement() {
  const video = document.createElement("video");
  video.autoplay = true;
  video.muted = true;        // browsers only autoplay muted video
  video.playsInline = true;  // stops phones from going fullscreen
  return video;
}

function setVideoLabel(text) {
  document.getElementById("video-source").textContent = "Camera: " + text;
}

function showVideoError(message) {
  const box = document.createElement("div");
  box.className = "video-error";
  box.textContent = message;
  document.getElementById("feed-day").replaceChildren(box);
}

// In "pi" mode camera.js shows the Raspberry Pi cameras instead
if (VIDEO_MODE !== "pi") startVideo(VIDEO_SOURCE);
