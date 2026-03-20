# Video Plugins

Video plugins work on the file locally. No frames are uploaded to an external service. Each plugin registers extractors for common video formats and returns structured metadata: timestamps, bounding boxes, detected text, object tags.

## Scene Detection

**Libraries:** [`scenedetect`](https://github.com/Breakthrough/PySceneDetect), [`opencv-python`](https://github.com/opencv/opencv-python)

Cuts a video into segments at scene boundaries. Each segment gets a keyframe image, a timestamp range, and an optional caption if a vision model is configured. Enables queries like "show me the segment starting around the 12-minute mark where someone is at a whiteboard."

## Object Detection

**Library:** [`ultralytics`](https://github.com/ultralytics/ultralytics) (YOLOv8)

Tags video segments by detected objects. Classes come from COCO (80 categories) by default; you can swap in a custom YOLOv8 model for domain-specific detection. Useful for security footage review, sports analysis, or any archive where visual content varies widely.

## OCR on Frames

**Libraries:** [`pytesseract`](https://github.com/madmaze/pytesseract), [`paddleocr`](https://github.com/PaddlePaddle/PaddleOCR)

Extracts text visible in video frames: slide decks recorded as screen captures, signs, whiteboards, lower-third graphics. The extracted text is indexed alongside the timestamp so a search for a specific term can return the moment it appears on screen.

PaddleOCR handles more languages and is faster on most hardware. Tesseract is the simpler dependency if you only need Latin-script text.

## Video Understanding

**Stack:** [`ollama`](https://ollama.com) + LLaVA-Video

Sends keyframes to a local multimodal model and asks natural-language questions. Returns answers grounded to specific timestamps. Slower than the other plugins, but covers questions that structured metadata cannot: "what is the presenter pointing at here?" or "what does the diagram in this frame show?"

Requires a running Ollama instance with a video-capable model loaded.

## VOD Transcription (Twitch / YouTube / etc.)

**Libraries:** [`yt-dlp`](https://github.com/yt-dlp/yt-dlp), [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper)

Downloads audio from any platform VOD that yt-dlp supports, then runs transcription. Makes a streamer's back-catalog, a conference recording archive, or a channel's full history searchable by spoken content. Respects local storage: the audio file and transcript live on your hardware.
