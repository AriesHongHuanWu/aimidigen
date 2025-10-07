# 🎼 AI MIDI 音樂生成器 (PySide6 + Groq + Mido)

> 以 **Groq LLM** 生成「嚴格 JSON」音符序列，並用 **Mido** 寫入 MIDI；提供 **PySide6** 圖形介面與進度回報，一鍵產生、播放、導出。

---

## 📘 專案簡介

本工具透過雲端 LLM 產生**只含 JSON** 的音符資料，再將其轉換為標準 MIDI 檔（`.mid`）。  
支援旋律與和聲（同一拍多音），可設定小節數與樂器音色，內建進度條、載入動畫與產出後的播放與導出。

**設計目標**
- 每次生成的開頭不同且符合風格
- 在同一個 **key** 與節奏下產生旋律與和弦
- 嚴格 JSON 輸出，並包含容錯解析

---

## 🧩 主要功能

- 風格提示（Style Prompt）→ 生成旋律＋和聲
- 長度選擇：4 / 8 / 16 / 32 小節（4/4，`480 ticks = 1 拍`）
- 樂器音色（**Program Change**）下拉選擇
- 進度條與載入動畫
- 生成後：**播放 MIDI**、**導出 MIDI**
- 失敗重試提示與 UI 控制狀態管理

---

## 🖥️ 介面與操作流程

1. 輸入音樂風格（如：*hip‑hop, jazz, funk*）。  
2. 選擇小節數與樂器音色。  
3. 按「產生 MIDI」。UI 顯示載入與進度。  
4. 生成成功後可直接「播放 MIDI」或「導出 MIDI」。

---

## 🧮 LLM 輸出資料格式（嚴格 JSON）

模型需回傳**僅 JSON**：

```json
{
  "notes": [
    { "pitch": 64, "start_time": 0,   "duration": 480, "velocity": 80 },
    { "pitch": 67, "start_time": 0,   "duration": 480, "velocity": 70 },
    { "pitch": 71, "start_time": 0,   "duration": 480, "velocity": 60 },
    { "pitch": 72, "start_time": 480, "duration": 240, "velocity": 80 }
  ]
}
```

規則：
- `pitch`：0–127 的 MIDI 音高
- `start_time`：以 **tick** 計（`ticks_per_beat = 480`）
- `duration`：tick 長度
- `velocity`：40–100 之間
- **和弦**：相同 `start_time` 的多個音符同時發聲

---

## ⚙️ 安裝需求

| 套件 | 用途 | 安裝 |
|---|---|---|
| Python 3.9+ | 執行環境 | — |
| `PySide6` | GUI | `pip install PySide6` |
| `requests` | 呼叫 API | `pip install requests` |
| `mido` | 寫入 MIDI | `pip install mido` |
| `python-rtmidi`* | 若需即時回放 | `pip install python-rtmidi` |

\* 本專案以**開啟系統預設播放器**播放 `.mid`。如需內嵌播放，可自行整合 `mido` + `python-rtmidi`。

**一次安裝**
```bash
pip install PySide6 requests mido python-rtmidi
```

---

## 🔑 API 設定（Groq）

- 於程式中設定：`API_KEY`、`API_URL`、`MODEL_NAME`  
  ```python
  API_KEY = "你的金鑰"
  API_URL = "https://api.groq.com/openai/v1/chat/completions"
  MODEL_NAME = "llama-3.1-70b-versatile"
  ```
- 建議改用**環境變數**並在程式讀取：
  - Windows：`setx GROQ_API_KEY "xxxxx"`
  - macOS / Linux：`export GROQ_API_KEY="xxxxx"`

> 務必避免將金鑰提交到版本庫。

---

## ▶️ 執行

```bash
python main.py
```

- 生成完成後，點「播放 MIDI」會使用**系統預設應用**開啟檔案。
- 「導出 MIDI」可選擇儲存路徑。

---

## 🧠 程式架構

```
main.py
│
├─ MusicGeneratorThread(QThread)
│  ├─ 構建強化 Prompt → 呼叫 Groq API
│  ├─ 解析嚴格 JSON（容錯處理：補齊、裁切）
│  └─ create_midi_from_notes() 生成 MIDI（含 Program Change）
│
├─ MusicGeneratorApp(QWidget)
│  ├─ 風格 / 小節 / 樂器 UI
│  ├─ 進度條、載入動畫、結果提示
│  ├─ 播放（呼叫系統預設）與導出
│  └─ 例外處理與執行緒管理
```

**MIDI 寫入重點**
- `mid.ticks_per_beat = 480`
- 依 `start_time` 分組，同步 `note_on`
- 立即寫入對應 `note_off`（簡化處理；如需更精確可改為事件排程表）

---

## 🔧 參數與可調項

- **小節數**：4 / 8 / 16 / 32（每小節 4 拍）  
- **Program Number**：標準 GM 音色號（0 = Acoustic Grand Piano …）  
- **LLM**：`MODEL_NAME`、`temperature`、`max_tokens` 可視風格調整  
- **強化 Prompt**：已要求「同一 key、旋律＋和聲、每次開頭不同、節奏多變」

---

## ❗ 常見問題（FAQ）

**Q1：API 回傳非 JSON 導致失敗？**  
A：已內建容錯解析與補齊；若仍失敗，請降低 `temperature` 或縮短小節。

**Q2：播放按鈕沒反應？**  
A：系統需關聯 `.mid` 的預設播放器。或手動用 DAW / 播放器開啟。

**Q3：和弦太少或旋律單調？**  
A：提高 `bars`，或在風格中加入「和弦豐富、節奏切分、多段發展」。

**Q4：需要實時聽到輸出？**  
A：整合 `mido + python-rtmidi` 或其他合成器，即時送出 MIDI。

---

## 🧱 專案結構範例

```
📂 ai-midi-generator
├─ main.py
└─ README.md
```

---

## 🔐 安全建議

- 使用環境變數儲存 API Key。
- 排除敏感檔案（`.env`、測試 MIDI）於 `.gitignore`。
- 控制權限與用量上限，避免濫用。
