---
sdk: docker
app_port: 7860
pinned: false
short_description: Burmese AI movie recap & dubbing studio
---
# 🎬 KAY AI Movie Recap

YouTube / RedNote / Upload ဗီဒီယိုတွေကို **မြန်မာလို Movie Recap** အဖြစ်ပြောင်းပေးတဲ့ web app —
မြန်မာစာတန်း + မြန်မာအသံ (dubbing) + နောက်ဆုံးဗီဒီယို export အထိ အလိုအလျောက်လုပ်ပေးပါတယ်။

## လိုအပ်ချက်များ

- Python 3.10+
- **ffmpeg** (libx264, aac, libass ပါဝင်ရမယ်)
- Myanmar font (Noto Sans Myanmar) — subtitle render အတွက်

```bash
# Ubuntu/Debian
sudo apt install ffmpeg fonts-noto-core
```

## Setup

```bash
cd kay-ai-movie-recap
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# .env ကို တည်းဖြတ်ပြီး API key တွေထည့်ပါ (အောက်ကြည့်ပါ)
python -m app.main        # http://localhost:8000
```

ပထမဆုံး run မှာ `.env` က `ADMIN_USERNAME` / `ADMIN_PASSWORD` နဲ့ admin အကောင့်အလိုအလျောက်ဖန်တီးပေးပါတယ်။

## API Key များ (.env)

| Key | ဘာအတွက် | မရှိရင်ဘာဖြစ်မလဲ |
|---|---|---|
| `GEMINI_API_KEY` | ဘာသာပြန်, Recap ရေး, ဘာသာစကားသိရှိ, အသံစာသားထုတ် (fallback) | AI အဆင့်တွေ error ပြပြီး ရပ်မယ် — အတုမထုတ်ဘူး |
| `TTS_PROVIDER=google` + `GOOGLE_TTS_API_KEY` | မြန်မာအသံ (my-MM voices) — **Google Cloud Text-to-Speech** | Voice Studio / dubbing အတွက် "API key လိုပါတယ်" လို့ပြမယ် |
| (optional) `pip install faster-whisper` | စက်တွင်း အသံစာသားထုတ် (offline) | မရှိရင် Gemini သုံးမယ် |

**လုံခြုံရေး:** key အားလုံး server-side (.env / database) မှာပဲရှိတယ်။ Frontend JS မှာ key လုံးဝမပါဘူး။

### 🌐 Web UI ကနေ key ထည့်နည်း (အသစ် — .env တည်းဖြတ်စရာမလို)
1. App ကို browser မှာဖွင့် → **admin** အကောင့်နဲ့ login ဝင်ပါ
2. **Admin** tab → **🔑 API Keys** card
3. **Gemini API Key** ထည့်ပါ — [Google AI Studio](https://aistudio.google.com/apikey) က အခမဲ့ရနိုင်ပါတယ်
   (ဘာသာပြန်, Recap ရေး, စကားပြောစာသားထုတ်ဖို့)
4. **Google Cloud TTS API Key** ထည့်ပါ — မြန်မာအသံ (my-MM) ထုတ်ဖို့၊ ပြီးရင် အောက်က
   ⚙️ Settings မှာ `tts_provider` ကို `google` လို့ ပြောင်းပါ
5. **🔑 Key များ သိမ်းရန်** နှိပ်ပါ — key အပြည့်ပြန်မပြပါ၊ `••••1234` လို့ပဲပြပြီး server ထဲမှာပဲ သိမ်းထားပါတယ်

### Google Cloud TTS key ရယူနည်း (အကျဉ်း)
1. [Google Cloud Console](https://console.cloud.google.com) → project ဖွင့်
2. **Text-to-Speech API** ကို Enable လုပ်
3. Credentials → **API key** ဖန်တီး → `.env` မှာ `GOOGLE_TTS_API_KEY=` ထည့်ပြီး `TTS_PROVIDER=google` ထားပါ
4. မြန်မာအသံများ အလိုအလျောက်ပေါ်လာမယ် (ဥပမာ `my-MM-Standard-A`)

## အသုံးပြုပုံ

1. **ဖန်တီးရန်** tab → YouTube link / RedNote link / Upload (MP4/MOV/MKV/WEBM/AVI, 500MB)
2. Video preview + analysis card ကြည့်မယ်
3. Mode ရွေး: ဘာသာပြန်သာ / စာတန်းသာ / မြန်မာအသံသာ / အသံ+စာတန်း / Recap အပြည့် / Recap အတို
4. အသံ၊ စာတန်းစတိုင်း (၅ မျိုး), export setting (TikTok 9:16 အပါအဝင်) ရွေး
5. **✨ CREATE BURMESE MOVIE RECAP** နှိပ် → 12-stage progress ကြည့်မယ်
6. ပြီးရင် ဗီဒီယို / အသံသာ / SRT / Script download

**Timeline Editor** မှာ စာသားတိုင်း (မူရင်း/မြန်မာ/အသံ) နဲ့ အချိန်တွေကို ပြင်နိုင်တယ်။ **Auto Sync** က အချိန်ထပ်နေတာတွေ ပြင်ပေးတယ်။

## Architecture

```
app/
  main.py          FastAPI app + static frontend
  config.py        env-based settings (centralized)
  db.py            SQLite schema (PostgreSQL-migratable design)
  jobs.py          background pipeline (12 stages), credits, resume
  providers/       ai.py (Gemini) / stt.py (whisper→gemini) / tts.py (google)
  services/        ingest.py / analyze.py / audio.py / subtitle.py / render.py / text_ai.py
  routers/         auth / projects / ingest / segments / pipeline / tts_api / admin
frontend/          Burmese-first SPA (index.html / styles.css / app.js)
data/              uploads, projects, exports, thumbs, kay.db (gitignored)
```

Pipeline: uploading → analyzing → extracting_audio → transcribing → translating →
creating_recap → generating_voice → synchronizing → detecting_subtitles →
subtitle_overlay → rendering → finalizing

## Deploy notes

- `uvicorn app.main:app --host 0.0.0.0 --port 8000` (systemd/Docker နဲ့ run နိုင်တယ်)
- `DATA_DIR` env နဲ့ data folder ပြောင်းနိုင်တယ်
- Credit စျေးနှုန်းတွေကို Admin Panel → Settings မှာပြင်နိုင်တယ်
- DB ကို PostgreSQL ပြောင်းချင်ရင် `app/db.py` schema က plain types တွေမို့ table တွေကူးလို့ရတယ်

## ကန့်သတ်ချက်များ (ရိုးသားစွာ)

- **Burmese TTS** က Google Cloud API key မရှိရင် အလုပ်မလုပ်ဘူး — အတုမထုတ်ဘူး
- **STT** က faster-whisper (သို့) Gemini key လိုတယ်
- **Embedded subtitle detection** က heuristic (အောက်ပိုင်း band ခန့်မှန်း) + လက်နဲ့ပြင်နိုင်တယ်; AI inpainting မပါဘူး (blur/အနက်ဖုံး သုံးတယ်)
- YouTube/RedNote download က platform ခွင့်ပြုမှရမယ်; မရရင် မြန်မာလို အသိပေးပြီး upload လမ်းကြောင်းပြပေးတယ်
