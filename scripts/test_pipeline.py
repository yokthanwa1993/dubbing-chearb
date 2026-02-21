#!/usr/bin/env python3
"""
ทดสอบ pipeline พากย์เสียงในเครื่อง (flow เดียวกับ production)
ใช้: python scripts/test_pipeline.py video.mp4
ผลลัพธ์: output.mp4
"""
import sys
import os
import json
import re
import base64
import tempfile
import subprocess
import requests

# Get API key from environment variable or use the new one as a fallback for local testing
API_KEY = os.environ.get("GOOGLE_API_KEY", "AIzaSyDO3alwmA6p9xUV2O3VzX1Kfs9vKxycRzU")
MODEL = "gemini-3-flash-preview"

PROMPT = """คุณคือ "เฉียบ" สาวสองนักรีวิวสินค้าสุดแซ่บ พูดจากวนตีน จี๊ดจ๊าด ดราม่าเว่อร์ ชอบแซวคนดู ปากจัดแต่น่ารัก

ดูวิดีโอสินค้านี้แล้วสร้าง script พากย์เสียงสำหรับ Facebook Reels

สไตล์ "เฉียบ":
- เปิดด้วยประโยคจี๊ดๆ เช่น "แม่จ๋าา ของดีมาแล้วค่า!" / "อี๋ย ใครยังไม่มีอันนี้ เชยระเบิดเลยนะคะ!" / "ตายแล้วค่ะ ของมันต้องมี!"
- พูดแบบสาวสองเต็มตัว ใช้คำว่า "ค่ะ" "จ๊ะ" "นะคะ" "แม่" "ตัวเอง" เยอะๆ ดราม่านิดๆ โอเวอร์หน่อยๆ
- แซวคนดูแบบน่ารัก เช่น "ยังใช้ของเดิมอยู่เหรอจ๊ะ น่าสงสารตัวเอง!" / "ใช้แล้วสวยขึ้น ไม่ได้พูดเล่นนะคะ!"
- บรรยายจุดเด่นสินค้าจริงจากวิดีโอ แต่ใส่อารมณ์โอเวอร์ เช่น "โอ้โห เห็นปุ๊บหัวใจแม่สั่นเลยค่ะ!" / "ดีจนอยากกรี๊ดดดด!"
- ปิดด้วยทิ้งท้ายจี๊ดๆ เช่น "กดซื้อเลยค่ะ ไม่งั้นแม่จะโกรธ!" / "ไม่ซื้อก็ได้ค่ะ แต่อย่ามาร้องไห้ตอนของหมดนะจ๊ะ 555!" / "ลิงก์ข้างล่างจ้า แม่จัดให้แล้ว!"

⚠️ ข้อห้าม: ห้ามพูด "สวัสดี" ห้ามเรียบๆ น่าเบื่อ ต้องจี๊ดจ๊าดตั้งแต่คำแรก! กระชับแต่แซ่บ!

ตอบเป็น JSON เท่านั้น:
{
  "thai_script": "script ภาษาไทยสไตล์สาวสองกวนๆ 150-300 ตัวอักษร จี๊ดจ๊าดชวนซื้อ",
  "title": "แคปชั่นสั้นแซ่บๆ ดึงดูดคนกด",
  "category": "หมวดหมู่ (เครื่องมือช่าง/อาหาร/เครื่องครัว/ของใช้ในบ้าน/เฟอร์นิเจอร์/บิวตี้/แฟชั่น/อิเล็กทรอนิกส์/สุขภาพ/กีฬา/สัตว์เลี้ยง/ยานยนต์/อื่นๆ)"
}"""


def resolve_xhs(url):
    """Resolve XHS short link → direct video URL"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml",
    }
    resp = requests.get(url, headers=headers, allow_redirects=True, timeout=15)
    html = resp.text

    for m in re.finditer(r'"masterUrl"\s*:\s*"([^"]+)"', html):
        u = m.group(1).replace("\\u002F", "/")
        if "sns-video" in u:
            return u

    m = re.search(r'"originVideoKey"\s*:\s*"([^"]+)"', html)
    if m:
        return f"https://sns-video-bd.xhscdn.com/{m.group(1)}"
    return None


def download_video(url):
    print(f"📥 ดาวน์โหลดวิดีโอ...")
    resp = requests.get(url, headers={"Referer": "https://www.xiaohongshu.com/"}, timeout=120)
    if resp.status_code != 200:
        raise Exception(f"Download failed: {resp.status_code}")
    print(f"   ✅ ขนาด {len(resp.content)/1024/1024:.1f} MB")
    return resp.content


def get_duration(video_path):
    r = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", video_path
    ], capture_output=True, text=True)
    return float(r.stdout.strip()) if r.stdout.strip() else 15.0


def gemini_upload(video_bytes):
    print(f"🔍 อัพโหลดไป Gemini...")
    resp = requests.post(
        f"https://generativelanguage.googleapis.com/upload/v1beta/files?uploadType=media&key={API_KEY}",
        data=video_bytes,
        headers={"Content-Type": "video/mp4", "X-Goog-Upload-Protocol": "raw"},
        timeout=120,
    )
    data = resp.json()
    if "file" not in data:
        raise Exception(f"Upload failed: {json.dumps(data, indent=2)}")
    uri = data["file"]["uri"]
    name = data["file"]["name"]
    print(f"   ✅ URI: {uri}")
    return uri, name


def gemini_wait(file_name):
    import time
    print(f"   ⏳ รอ Gemini ประมวลผล...")
    for i in range(30):
        r = requests.get(
            f"https://generativelanguage.googleapis.com/v1beta/{file_name}?key={API_KEY}",
            timeout=15
        ).json()
        state = r.get("state", "UNKNOWN")
        if state == "ACTIVE":
            print(f"   ✅ ประมวลผลเสร็จ")
            return
        print(f"   ... {state} ({i+1}/30)")
        time.sleep(3)
    raise Exception("Gemini ประมวลผลนานเกินไป")


def gemini_script(file_uri, video_duration):
    print(f"📝 สร้าง script (สำหรับ {video_duration:.1f} วินาที)...")
    
    # คำนวณความยาว script ที่เหมาะสม (~10 ตัวอักษร/วินาที สำหรับภาษาไทย TTS)
    max_chars = min(int(video_duration * 10), 800)
    min_chars = max(int(video_duration * 7), 80)
    
    prompt = f"""คุณคือ "เฉียบ" สาวสองนักรีวิวสินค้าสุดแซ่บ พูดจากวนตีน จี๊ดจ๊าด ดราม่าเว่อร์ ชอบแซวคนดู ปากจัดแต่น่ารัก

ดูวิดีโอสินค้านี้แล้วสร้าง script พากย์เสียงสำหรับ Facebook Reels

⏱️ สำคัญมาก: วิดีโอนี้ยาว {video_duration:.1f} วินาที เท่านั้น! Script ต้องบรรยายยาวไปจนจบวิดีโอ!

สไตล์ "เฉียบ":
- เปิดด้วยประโยคจี๊ดๆ เช่น "แม่จ๋าา ของดีมาแล้วค่า!" / "อี๋ย ใครยังไม่มีอันนี้ เชยระเบิดเลยนะคะ!" / "ตายแล้วค่ะ ของมันต้องมี!"
- พูดแบบสาวสองเต็มตัว ใช้คำว่า "ค่ะ" "จ๊ะ" "นะคะ" "แม่" "ตัวเอง" เยอะๆ ดราม่านิดๆ โอเวอร์หน่อยๆ
- แซวคนดูแบบน่ารัก เช่น "ยังใช้ของเดิมอยู่เหรอจ๊ะ น่าสงสารตัวเอง!" / "ใช้แล้วสวยขึ้น ไม่ได้พูดเล่นนะคะ!"
- บรรยายจุดเด่นสินค้าจริงจากวิดีโอ แต่ใส่อารมณ์โอเวอร์ เช่น "โอ้โห เห็นปุ๊บหัวใจแม่สั่นเลยค่ะ!" / "ดีจนอยากกรี๊ดดดด!"
- ปิดด้วยทิ้งท้ายจี๊ดๆ เช่น "กดซื้อเลยค่ะ ไม่งั้นแม่จะโกรธ!" / "ไม่ซื้อก็ได้ค่ะ แต่อย่ามาร้องไห้ตอนของหมดนะจ๊ะ 555!" / "ลิงก์ข้างล่างจ้า แม่จัดให้แล้ว!"

⚠️ ข้อห้าม: ห้ามพูด "สวัสดี" ห้ามเรียบๆ น่าเบื่อ ต้องจี๊ดจ๊าดตั้งแต่คำแรก! กระชับแต่แซ่บ!

⚠️ ความยาว: Script ต้องยาว {min_chars}-{max_chars} ตัวอักษรเท่านั้น สำคัญมาก! ห้ามสั้นเกินไปเพราะวิดีโอยาวตั้ง {video_duration:.0f} วินาที

ตอบเป็น JSON เท่านั้น:
{{
  "thai_script": "script ภาษาไทยสไตล์สาวสองกวนๆ {min_chars}-{max_chars} ตัวอักษร จี๊ดจ๊าดชวนซื้อ",
  "title": "แคปชั่นสั้นแซ่บๆ ดึงดูดคนกด",
  "category": "หมวดหมู่ (เครื่องมือช่าง/อาหาร/เครื่องครัว/ของใช้ในบ้าน/เฟอร์นิเจอร์/บิวตี้/แฟชั่น/อิเล็กทรอนิกส์/สุขภาพ/กีฬา/สัตว์เลี้ยง/ยานยนต์/อื่นๆ)"
}}"""

    resp = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}",
        json={"contents": [{"parts": [
            {"file_data": {"mime_type": "video/mp4", "file_uri": file_uri}},
            {"text": prompt}
        ]}]},
        timeout=60,
    ).json()

    if resp.get("error"):
        raise Exception(f"Gemini error: {resp['error'].get('message')}")

    text = resp.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
    text = text.replace("```json", "").replace("```", "").strip()

    try:
        parsed = json.loads(text)
        script = parsed.get("thai_script", "")
        title = parsed.get("title", "")
        category = parsed.get("category", "อื่นๆ")
    except:
        m = re.search(r'"thai_script"\s*:\s*"([^"]+)"', text)
        script = m.group(1) if m else text[:500]
        title = ""
        category = "อื่นๆ"

    print(f"   ✅ Script ({len(script)} ตัวอักษร):")
    print(f"   📝 {script}")
    print(f"   📌 Title: {title}")
    print(f"   📂 Category: {category}")
    return script, title, category


def gemini_tts(script):
    print(f"🎙️ สร้างเสียงพากย์...")
    resp = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent?key={API_KEY}",
        json={
            "contents": [{"parts": [{"text": script}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Puck"}}}
            }
        },
        timeout=60,
    ).json()

    if resp.get("error"):
        raise Exception(f"TTS error: {resp['error'].get('message')}")

    audio_b64 = resp["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
    print(f"   ✅ เสียง {len(audio_b64)//1024} KB")
    return audio_b64


def fix_srt_with_gemini(srt_content, original_script):
    print(f"🤖 ส่งซับไปให้ Gemini Flash จัดบรรทัดและเวลา SRT ใหม่ให้เป๊ะ...")
    prompt = f"""คุณคือผู้เชี่ยวชาญด้านการตัดต่อ Subtitle วิดีโอสั้นสไตล์ TikTok/Reels แบบคำปังๆ เน้นขึ้นโชว์ทีละบรรทัดสั้นๆ
นี่คือต้นฉบับบทพากย์ที่ถูกต้อง (Original Script):
{original_script}

และนี่คือไฟล์ SRT ที่ได้จากเสียงพูด (ซึ่งเวลายังรวบยาวเป็นก้อนใหญ่ๆ และมีคำสะกดผิด):
{srt_content}

คำสั่งบังคับ (สำคัญมากต้องทำตาม):
1. แปลงข้อมูลเป็น SRT ใหม่ ให้เนื้อหาซับไตเติ้ลแสดงผล "ทีละ 1 บรรทัดเท่านั้น" ห้ามมีการขึ้นบรรทัดใหม่ ใน 1 block
2. หั่นประโยคให้สั้น (กะประมาณไม่เกิน 15-20 ตัวอักษรต่อ 1 block SRT) เพื่อให้อ่านทันทีละจังหวะสั้นๆ
3. เนื้อหาและคำศัพท์ต้องถูกต้อง 100% ตาม "Original Script" ห้ามมีคำผิดแหลมมา (แก้คำที่ Whisper แปลงมามั่วให้ถูกเป๊ะๆ)
4. คุณต้อง "คำนวณแบ่งและสร้าง Timestamps ใหม่" โดยซอย block ยาวๆ ให้เป็น block สั้นๆ ตามสัดส่วนความยาวคำให้เนียนที่สุด โดยให้เวลาเริ่มและเวลาจบครอบคลุมตาม SRT ของเดิมอย่าให้ล้น
5. เลี่ยงการตัดคำที่มีความหมายติดกัน (เช่น 'เชยระเบิด' ไม่ควรแยก 'เชย' กับ 'ระเบิด' ข้ามเวลา)
6. ⚠️ ห้ามเอาข้อความสอง block หรือสองวรรคมาต่อกันแบบไม่มีเว้นวรรค เช่น "ดูความแบ๊วสิคะแม่ ขี่" หรือ "งอร้านสะดวกซื้อปาก" จะต้องแบ่งเป็นคำที่มีความหมายสมบูรณ์ "ดูความแบ๊วสิคะแม่", "ง้อร้านสะดวกซื้อปากซอย" 
7. ตอบกลับมาแค่เนื้อหา SRT ล้วนๆ ห้ามตอบอย่างอื่น ห้ามมี markdown ```srt

SRT ที่แก้ไขแล้ว:"""

    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={API_KEY}",
            json={
                "contents": [{"parts": [{"text": prompt}]}]
            },
            timeout=60,
        ).json()
        
        if resp.get("error"):
            print(f"   ⚠️ Gemini Subtitling error: {resp['error'].get('message')}")
            return srt_content
            
        fixed_srt = resp.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        fixed_srt = fixed_srt.replace("```srt", "").replace("```", "").strip()
        print(f"   ✅ Gemini Flash แก้ซับไตเติ้ลเรียบร้อย!")
        return fixed_srt
    except Exception as e:
        print(f"   ⚠️ Gemini Error: {e}")
        return srt_content


def split_script_to_segments(script):
    """แบ่ง script เป็นท่อนสั้นๆ ตามเครื่องหมายวรรคตอน"""
def time_to_seconds(time_str):
    """แปลงเวลา SRT เป็นวินาที"""
    time_str = time_str.replace(',', '.')
    parts = time_str.split(':')
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2])
    return hours * 3600 + minutes * 60 + seconds


def parse_srt(srt_file):
    """อ่านไฟล์ SRT"""
    with open(srt_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    import re
    blocks = re.split(r'\n\s*\n', content.strip())
    subtitles = []
    
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            time_line = lines[1]
            match = re.match(r'(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})', time_line)
            if match:
                start = time_to_seconds(match.group(1))
                end = time_to_seconds(match.group(2))
                text = '\n'.join(lines[2:])
                subtitles.append((start, end, text))
    
    return subtitles


def create_subtitle_image(text, width, height, font_size=50):
    from PIL import Image, ImageDraw, ImageFont
    import numpy as np
    
    # ดึงลิสต์ฟอนต์จาก render_subs แบบฉบับสมบูรณ์
    font_paths = [
        "/Users/yok/Developer/dubbing-chearb/FC Iconic Bold.ttf",
        "/System/Library/Fonts/ThonburiUI.ttc",
        "/System/Library/Fonts/Supplemental/Thonburi.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    font = None
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, font_size)
                break
            except:
                continue
    if font is None:
        font = ImageFont.load_default()

    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # รองรับ Pillow version ใหม่และเก่า
    if hasattr(draw, 'textbbox'):
        bbox = draw.textbbox((0, 0), text, font=font, align='center')
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
    elif hasattr(draw, 'multilinebbox'):
        bbox = draw.multilinebbox((0, 0), text, font=font, align='center')
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
    else:
        text_width, text_height = draw.textsize(text, font=font)
    
    x = (width - text_width) // 2
    # ให้ข้อความอยู่ตรงกลางจอ (ทั้งซ้าย-ขวา และ บน-ล่าง)
    y = (height - text_height) // 2
    
    # ความหนาขอบลดลงเหลือ 5% ของขนาดฟอนต์ (ไม่หนาเกินไปจนดูรก)
    stroke_w = int(font_size * 0.05)
    if stroke_w < 2: stroke_w = 2
    
    # วาดตัวหนังสือสีขาวพร้อมขอบ (ใช้ draw.text ธรรมดาก็พอเพราะมีบรรทัดเดียว 100%)
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255), align='center', stroke_width=stroke_w, stroke_fill=(0, 0, 0, 255))
    
    return np.array(img)


def ffmpeg_merge(video_path, audio_b64, output_path, script=None):
    print(f"🎬 รวมวิดีโอ + เสียง...")
    duration = get_duration(video_path)
    print(f"   วิดีโอยาว {duration:.1f} วินาที")

    with tempfile.TemporaryDirectory() as tmpdir:
        raw_audio = os.path.join(tmpdir, "audio.raw")
        wav_audio = os.path.join(tmpdir, "audio.wav")

        with open(raw_audio, "wb") as f:
            f.write(base64.b64decode(audio_b64))

        subprocess.run([
            "ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1",
            "-i", raw_audio, wav_audio
        ], check=True, capture_output=True)

        ap = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", wav_audio
        ], capture_output=True, text=True)
        audio_dur = float(ap.stdout.strip()) if ap.stdout.strip() else 0
        print(f"   เสียงพากย์ยาว {audio_dur:.1f} วินาที")

        adjusted = os.path.join(tmpdir, "audio_adj.wav")
        diff = duration - audio_dur
        if abs(diff) < 0.5:
            adjusted = wav_audio
        elif diff > 0:
            subprocess.run(["ffmpeg", "-y", "-i", wav_audio, "-af", f"apad=pad_dur={diff}", adjusted], capture_output=True)
        else:
            subprocess.run(["ffmpeg", "-y", "-i", wav_audio, "-t", str(duration), adjusted], capture_output=True)

        # Merge video + audio (ไม่มี subtitle ก่อน)
        merged_nosub = os.path.join(tmpdir, "merged_nosub.mp4")
        mr = subprocess.run([
            "ffmpeg", "-y", "-i", video_path, "-i", adjusted,
            "-c:v", "copy", "-c:a", "aac",
            "-map", "0:v:0", "-map", "1:a:0",
            "-t", str(duration), merged_nosub
        ], capture_output=True, text=True)
        if mr.returncode != 0:
            raise Exception(f"FFmpeg merge failed: {mr.stderr[-500:]}")

        # Burn subtitle ด้วย moviepy + PIL rendering
        # Burn subtitle ด้วย moviepy + PIL rendering + Whisper SRT
        if script:
            import re
            print(f"📝 Transcribing ด้วย Whisper เพื่อเวลาที่เป๊ะที่สุด...")
            subprocess.run([
                "whisper-ctranslate2", adjusted,
                "--model", "turbo",
                "--language", "th",
                "--output_format", "srt",
                "--output_dir", tmpdir,
                "--compute_type", "int8",
                "--word_timestamps", "True",
                "--max_line_width", "20",
                "--max_line_count", "1"
            ], check=True)
            
            srt_name = os.path.splitext(os.path.basename(adjusted))[0] + ".srt"
            srt_path = os.path.join(tmpdir, srt_name)
            
            # อ่าน SRT เก่าที่มาจาก Whisper
            with open(srt_path, "r", encoding="utf-8") as fs:
                raw_srt_text = fs.read()
            
            # โยนให้ Gemini แก้คำผิด + จัดบรรทัดใหม่
            fixed_srt_content = fix_srt_with_gemini(raw_srt_text, script)
            
            # เขียนกลับลงไปที่ไฟล์ (เผื่อไว้ debug ได้)
            with open(srt_path, "w", encoding="utf-8") as fs:
                fs.write(fixed_srt_content)
                
            subtitles = parse_srt(srt_path)
            
            print(f"   ✅ แปลงเป็นซับเสร็จสิ้น: {len(subtitles)} ประโยค")

            from moviepy import VideoFileClip, ImageClip, CompositeVideoClip

            video_clip = VideoFileClip(merged_nosub)
            vw, vh = video_clip.w, video_clip.h

            text_clips = []

            # เพิ่มขนาดฟอนต์ให้ใหญ่ขึ้นอีก (จาก 0.085 -> 0.115 ~ ยักษ์กระแทกตามากๆ)
            font_size = int(vw * 0.115)
            if font_size < 50: font_size = 50

            last_end = 0
            for i, (start, end, raw_text) in enumerate(subtitles):
                # ป้องกันซับทับซ้อน (Overlap) โดยจัด start ใหม่ถ้ามันเริ่มก่อนที่อันเก่าจะจบ
                if start < last_end:
                    start = last_end
                
                # ป้องกันซับทับซ้อน (Overlap) โดยจบให้พอดีกับอันถัดไปถ้ามันล้ำ
                if i + 1 < len(subtitles):
                    next_start = subtitles[i+1][0]
                    if end > next_start:
                        end = next_start

                seg_dur = end - start
                if seg_dur <= 0:
                    continue
                last_end = end
                
                # เอาเฉพาะซับที่พอดี video
                if start >= duration:
                    break
                
                # ลบเครื่องหมายประหลาด และเอา \n ออกเพื่อบังคับให้เป็นบรรทัดเดียวตามที่ Gemini ตัดมาให้
                seg = raw_text.replace("\n", " ").strip()
                
                try:
                    img_np = create_subtitle_image(seg, vw, vh, font_size=font_size)
                    img_clip = ImageClip(img_np)
                    img_clip = img_clip.with_start(start).with_duration(seg_dur)
                    text_clips.append(img_clip)
                except Exception as e:
                    print(f"   ⚠️ ข้ามซับ: {e}")

            if text_clips:
                final = CompositeVideoClip([video_clip] + text_clips)
                final.write_videofile(output_path, codec='libx264', audio_codec='aac',
                                     preset='fast', logger=None)
                video_clip.close()
                final.close()
            else:
                video_clip.close()
                import shutil
                shutil.move(merged_nosub, output_path)
        else:
            import shutil
            shutil.move(merged_nosub, output_path)

    out_size = os.path.getsize(output_path) / 1024 / 1024
    print(f"   ✅ เสร็จ! ขนาด {out_size:.1f} MB → {output_path}")


def main():
    if len(sys.argv) < 2:
        print("ใช้: python scripts/test_pipeline.py <video_file_or_url>")
        print("ตัวอย่าง:")
        print("  python scripts/test_pipeline.py video.mp4")
        print("  python scripts/test_pipeline.py https://xhslink.com/xxxxx")
        sys.exit(1)

    input_path = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) > 2 else "output.mp4"

    print(f"\n{'='*50}")
    print(f"🎬 ทดสอบ Pipeline พากย์เสียง — เฉียบ")
    print(f"{'='*50}\n")

    is_local = os.path.exists(input_path)

    if is_local:
        print(f"📁 ใช้ไฟล์ local: {input_path}")
        tmp_video = input_path
        with open(input_path, "rb") as f:
            video_bytes = f.read()
        print(f"   ✅ ขนาด {len(video_bytes)/1024/1024:.1f} MB")
    else:
        url = input_path
        video_url = url
        if "xhs" in url or "xiaohongshu" in url:
            print(f"🔗 Resolve XHS link...")
            video_url = resolve_xhs(url)
            if not video_url:
                print("❌ ไม่พบวิดีโอใน XHS link")
                sys.exit(1)
            print(f"   ✅ {video_url[:80]}...")

        video_bytes = download_video(video_url)
        tmp_video = "temp_input.mp4"
        with open(tmp_video, "wb") as f:
            f.write(video_bytes)

    try:
        file_uri, file_name = gemini_upload(video_bytes)
        gemini_wait(file_name)
        
        duration = get_duration(tmp_video)
        script, title, category = gemini_script(file_uri, duration)
        audio_b64 = gemini_tts(script)
        ffmpeg_merge(tmp_video, audio_b64, output, script=script)

        print(f"\n{'='*50}")
        print(f"🎉 สำเร็จ!")
        print(f"📁 ไฟล์: {output}")
        print(f"📝 Script: {script}")
        print(f"📌 Title: {title}")
        print(f"📂 Category: {category}")
        print(f"{'='*50}\n")

    finally:
        if not is_local and os.path.exists(tmp_video):
            os.remove(tmp_video)


if __name__ == "__main__":
    main()
