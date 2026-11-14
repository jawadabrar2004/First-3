// =====================================================================
// video.js - shows the drone camera in the big video panel.
// Reads VIDEO_SOURCE from config.js and builds the right HTML element.
// =====================================================================

const TYPE_NAMES = {
  webcam: "Webcam (mock drone cam)",
  mjpeg: "MJPEG stream",
  webrtc: "WebRTC stream",
  file: "Demo video file",
};

function startVideo(source) {
  const stage = document.getElementById("video-stage");
  const sourceLabel = document.getElementById("video-source");
  stage.innerHTML = "";
  sourceLabel.textContent = TYPE_NAMES[source.type] || source.type;

  if (source.type === "webcam") {
    // A <video> element fed by the laptop camera
    const video = makeVideoElement();
    stage.appendChild(video);
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      showVideoError("This browser can't use the webcam. Open the page at http://localhost:8000.");
      return;
    }
    navigator.mediaDevices
      .getUserMedia({ video: { width: 1280, height: 720 }, audio: false })
      .then((stream) => { video.srcObject = stream; })
      .catch((err) => showVideoError("Camera unavailable: " + err.message + ". Allow camera access and reload."));

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

function makeVideoElement() {
  const video = document.createElement("video");
  video.autoplay = true;
  video.muted = true;        // browsers only autoplay muted video
  video.playsInline = true;  // stops phones from going fullscreen
  return video;
}

function showVideoError(message) {
  const stage = document.getElementById("video-stage");
  stage.innerHTML = "";
  const box = document.createElement("div");
  box.className = "video-error";
  box.textContent = message;
  stage.appendChild(box);
}

startVideo(VIDEO_SOURCE);
