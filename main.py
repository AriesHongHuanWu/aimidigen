# -*- coding: utf-8 -*-
import sys
import os
import subprocess
import json
import requests
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtWidgets import QFileDialog, QMessageBox
from mido import Message, MidiFile, MidiTrack

API_KEY = "xxx"
API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL_NAME = "llama-3.1-70b-versatile"

class MusicGeneratorThread(QtCore.QThread):
    progress_signal = QtCore.Signal(int)
    generation_done_signal = QtCore.Signal(str)

    def __init__(self, style_prompt, bars, program_number):
        super().__init__()
        self.style_prompt = style_prompt
        self.bars = bars
        self.program_number = program_number

    def run(self):
        try:
            # 加強版 prompt
            prompt = (
                f"你是一個嚴格的 JSON MIDI 音符生成器，只能輸出可解析的 JSON。\n"
                f"風格：{self.style_prompt}，開頭每次都要不同，且符合風格，並且要符合樂理和弦確保歌在同一個音調(key)上\n"
                f"長度：約 {self.bars} 小節，4/4拍（480 ticks=1拍），總共約 {self.bars*4} 拍。\n"
                "請產生包含旋律與和聲(和弦)的音符序列，音高不限，力度(velocity)40~100。\n"
                "請嘗試不同的和弦組合與節奏變化，讓音樂更自然有層次，開頭不要是do re mi，每次開頭都要不同。\n"
                "務必在同一個 start_time 有多個音符以形成和弦（例如同一組 notes 有相同的 start_time）。\n"
                "輸出格式嚴格為JSON，範例如下（無多餘文字）(以下僅為參考，請優先參考風格跟長度)：\n"
                "{\n"
                "  \"notes\": [\n"
                "    {\"pitch\": 64, \"start_time\": 0, \"duration\": 480, \"velocity\": 80},\n"
                "    {\"pitch\": 67, \"start_time\": 0, \"duration\": 480, \"velocity\": 70},\n"
                "    {\"pitch\": 71, \"start_time\": 0, \"duration\": 480, \"velocity\": 60},\n"
                "    {\"pitch\": 72, \"start_time\": 480, \"duration\": 240, \"velocity\": 80}\n"
                "  ]\n"
                "}\n"
                "請只輸出JSON，不要其他解說。如果無法產生完整JSON，請自行重試直到成功。"
            )

            headers = {
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": MODEL_NAME,
                "messages": [
                    {"role": "system", "content": "You are a strict JSON MIDI note generator. Only output valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 2000,
                "temperature": 0.3
            }

            response = requests.post(API_URL, headers=headers, json=payload)
            if response.status_code != 200:
                print(f"Groq API error: {response.status_code}, {response.text}")
                self.generation_done_signal.emit("")
                return

            data = response.json()
            text = ""
            if "choices" in data and len(data["choices"]) > 0:
                text = data["choices"][0]["message"]["content"].strip()

            print("Groq Model output:", text)

            notes = self.parse_json_notes(text)
            if not notes:
                self.generation_done_signal.emit("")
                return

            filename = self.get_unique_filename('generated_music.mid')
            self.create_midi_from_notes(notes, filename, self.program_number)
            self.generation_done_signal.emit(filename)
        except Exception as e:
            print(f"Error during MIDI generation: {e}")
            self.generation_done_signal.emit("")

    def parse_json_notes(self, text):
        def try_parse(t):
            try:
                music_data = json.loads(t)
                return music_data.get("notes", [])
            except json.JSONDecodeError:
                return None

        notes = try_parse(text)
        if notes:
            return notes

        start_index = text.find('"notes": [')
        if start_index == -1:
            return None

        fixed_text = text.strip()
        if not fixed_text.endswith(']}'):
            if not fixed_text.endswith(']'):
                fixed_text += ']'
            if not fixed_text.endswith(']}'):
                fixed_text += '}'

        notes = try_parse(fixed_text)
        if notes:
            return notes

        # 嘗試刪除不完整的音符
        import re
        pattern = r'\{[^}]*\}'
        start = fixed_text.find('[')
        end = fixed_text.rfind(']')
        if start == -1 or end == -1:
            return None
        content = fixed_text[start+1:end].strip()
        matches = list(re.finditer(pattern, content))
        while matches:
            last_match = matches[-1]
            truncated_content = content[:last_match.start()].rstrip(', \n')
            attempt_text = fixed_text[:start+1] + truncated_content + ']}'
            notes = try_parse(attempt_text)
            if notes:
                return notes
            matches.pop()

        return None

    def create_midi_from_notes(self, notes, filename, program_number):
        # 假設notes有pitch, start_time, duration, velocity欄位
        # 先依 start_time 排序
        notes = sorted(notes, key=lambda n: n.get("start_time", 0))

        mid = MidiFile()
        track = MidiTrack()
        mid.tracks.append(track)
        track.append(Message('program_change', program=program_number, time=0))
        mid.ticks_per_beat = 480

        current_time = 0
        # 我們將同一個 start_time 的音符一次性處理
        from itertools import groupby
        # groupby 依 start_time 分組
        for start_time, group in groupby(notes, key=lambda x: x.get("start_time", 0)):
            chord_notes = list(group)
            # 計算delta_time
            delta_time = max(0, start_time - current_time)
            # 同時note_on
            for i, note_data in enumerate(chord_notes):
                pitch = note_data.get("pitch", 60)
                duration = note_data.get("duration", 480)
                velocity = note_data.get("velocity", 80)
                # 同一起始點的音符同時發聲，除了第一個有delta_time，其餘time=0
                track.append(Message('note_on', note=pitch, velocity=velocity, time=(delta_time if i == 0 else 0)))
                # 將 note_off 延後加入，先暫存起來
                # 為簡化，我們直接在同一組音符後馬上note_off，實際上可先記錄再分配
                track.append(Message('note_off', note=pitch, velocity=velocity, time=duration))
                # 更新progress (粗略)
                self.progress_signal.emit(int((track.__len__() / (len(notes)*2)) * 100))
                self.msleep(10)

            current_time = start_time
            # 所有該start_time的音符結束後，current_time只到start_time最初開始點
            # note_off已加duration,故current_time更新為start_time+duration不準確
            # 但在此簡單處理即可，如要更嚴謹，需要重算next delta_time

        mid.save(filename)

    def get_unique_filename(self, base_name):
        if not os.path.exists(base_name):
            return base_name
        base, ext = os.path.splitext(base_name)
        counter = 1
        while True:
            new_name = f"{base}_{counter}{ext}"
            if not os.path.exists(new_name):
                return new_name
            counter += 1

class MusicGeneratorApp(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.generator_thread = None
        self.current_midi = None
        self.loading_timer = None
        self.loading_state = 0
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("AI MIDI 音樂生成器")
        self.setFixedSize(450, 500)

        layout = QtWidgets.QVBoxLayout()

        title_label = QtWidgets.QLabel("AI MIDI 音樂生成器")
        title_label.setAlignment(QtCore.Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title_label)

        desc_label = QtWidgets.QLabel("請輸入音樂風格、長度與樂器，然後產生MIDI！\nAI將嘗試產生和弦、多變的音樂")
        desc_label.setAlignment(QtCore.Qt.AlignCenter)
        desc_label.setStyleSheet("font-size: 14px;")
        layout.addWidget(desc_label)

        input_container = QtWidgets.QWidget()
        input_layout = QtWidgets.QVBoxLayout(input_container)
        input_layout.setAlignment(QtCore.Qt.AlignCenter)

        style_label = QtWidgets.QLabel("音樂風格:")
        style_label.setAlignment(QtCore.Qt.AlignCenter)
        style_label.setStyleSheet("font-size: 16px; font-weight: bold;")

        self.style_input = QtWidgets.QLineEdit()
        self.style_input.setPlaceholderText("例如: hip-hop, jazz, funky")
        self.style_input.setStyleSheet("font-size: 14px; padding: 5px;")

        input_layout.addWidget(style_label)
        input_layout.addWidget(self.style_input)

        bars_label = QtWidgets.QLabel("MIDI 長度(小節數):")
        bars_label.setAlignment(QtCore.Qt.AlignCenter)
        bars_label.setStyleSheet("font-size:16px; font-weight: bold;")
        self.bars_combo = QtWidgets.QComboBox()
        self.bars_combo.addItem("4 小節", 4)
        self.bars_combo.addItem("8 小節", 8)
        self.bars_combo.addItem("16 小節", 16)
        self.bars_combo.addItem("32 小節", 32)
        self.bars_combo.setStyleSheet("font-size:14px; padding: 3px;")

        input_layout.addWidget(bars_label)
        input_layout.addWidget(self.bars_combo)

        instrument_label = QtWidgets.QLabel("選擇樂器音色:")
        instrument_label.setAlignment(QtCore.Qt.AlignCenter)
        instrument_label.setStyleSheet("font-size:16px; font-weight: bold;")
        self.instrument_combo = QtWidgets.QComboBox()
        self.instrument_combo.addItem("Acoustic Grand Piano (0)", 0)
        self.instrument_combo.addItem("Bright Acoustic Piano (1)", 1)
        self.instrument_combo.addItem("Electric Grand Piano (2)", 2)
        self.instrument_combo.addItem("Acoustic Guitar (nylon) (24)", 24)
        self.instrument_combo.addItem("Electric Guitar (jazz) (26)", 26)
        self.instrument_combo.addItem("Electric Piano 1 (4)", 4)
        self.instrument_combo.addItem("Synth Lead (80)", 80)
        self.instrument_combo.setStyleSheet("font-size:14px; padding:3px;")

        input_layout.addWidget(instrument_label)
        input_layout.addWidget(self.instrument_combo)

        layout.addWidget(input_container)

        self.generate_btn = QtWidgets.QPushButton("產生MIDI")
        self.generate_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border-radius: 8px;
                font-size: 16px;
                padding: 8px 20px;
            }
            QPushButton:hover {
                background-color: #45A049;
            }
        """)
        self.generate_btn.clicked.connect(self.start_generation)
        layout.addWidget(self.generate_btn, alignment=QtCore.Qt.AlignCenter)

        self.loading_label = QtWidgets.QLabel("")
        self.loading_label.setAlignment(QtCore.Qt.AlignCenter)
        self.loading_label.setStyleSheet("font-size: 14px; color: gray;")
        self.loading_label.hide()

        self.loading_text = QtWidgets.QLabel("音樂生成中，請稍候 ")
        self.loading_text.setAlignment(QtCore.Qt.AlignCenter)
        self.loading_text.setStyleSheet("font-size:14px; color:gray;")
        self.loading_text.hide()

        layout.addWidget(self.loading_text)
        layout.addWidget(self.loading_label)

        self.completed_label = QtWidgets.QLabel("完成！")
        self.completed_label.setAlignment(QtCore.Qt.AlignCenter)
        self.completed_label.setStyleSheet("font-size:16px; color:green; font-weight:bold;")
        self.completed_label.hide()
        layout.addWidget(self.completed_label)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedWidth(300)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid grey;
                border-radius: 5px;
                text-align: center;
                font-size:14px;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                width: 20px;
            }
        """)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar, alignment=QtCore.Qt.AlignCenter)

        self.button_frame = QtWidgets.QFrame()
        self.button_layout = QtWidgets.QHBoxLayout(self.button_frame)
        self.button_layout.setSpacing(10)

        self.play_btn = QtWidgets.QPushButton("播放MIDI")
        self.play_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border-radius: 8px;
                font-size:14px;
                padding:5px 15px;
            }
            QPushButton:hover {
                background-color: #1E88E5;
            }
        """)
        self.play_btn.clicked.connect(self.play_music)
        self.play_btn.hide()
        self.button_layout.addWidget(self.play_btn)

        self.export_btn = QtWidgets.QPushButton("導出MIDI")
        self.export_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                border-radius: 8px;
                font-size:14px;
                padding:5px 15px;
            }
            QPushButton:hover {
                background-color: #FB8C00;
            }
        """)
        self.export_btn.clicked.connect(self.export_midi)
        self.export_btn.hide()
        self.button_layout.addWidget(self.export_btn)

        self.generate_next_btn = QtWidgets.QPushButton("生成下一個")
        self.generate_next_btn.setStyleSheet("""
            QPushButton {
                background-color: #9C27B0;
                color: white;
                border-radius: 8px;
                font-size:14px;
                padding:5px 15px;
            }
            QPushButton:hover {
                background-color: #8E24AA;
            }
        """)
        self.generate_next_btn.clicked.connect(self.generate_next)
        self.generate_next_btn.hide()
        self.button_layout.addWidget(self.generate_next_btn)

        layout.addWidget(self.button_frame, alignment=QtCore.Qt.AlignCenter)

        self.setLayout(layout)

        self.loading_timer = QtCore.QTimer()
        self.loading_timer.timeout.connect(self.update_loading_animation)
        self.loading_timer.setInterval(500) # 0.5秒切換一次

    def start_generation(self):
        style = self.style_input.text().strip()
        if not style:
            QMessageBox.warning(self, "警告", "請輸入音樂風格！")
            return

        bars = self.bars_combo.currentData()
        if not bars:
            bars = 8

        program_number = self.instrument_combo.currentData()
        if program_number is None:
            program_number = 0

        self.generate_btn.setEnabled(False)
        self.loading_text.show()
        self.loading_label.show()
        self.completed_label.hide()
        self.play_btn.hide()
        self.export_btn.hide()
        self.generate_next_btn.hide()
        self.progress_bar.show()
        self.progress_bar.setValue(0)

        self.loading_state = 0
        self.loading_label.setText(".")
        self.loading_timer.start()

        self.generator_thread = MusicGeneratorThread(style, bars, program_number)
        self.generator_thread.progress_signal.connect(self.update_progress)
        self.generator_thread.generation_done_signal.connect(self.on_generation_done)
        self.generator_thread.start()

    def on_generation_done(self, filename):
        self.loading_timer.stop()
        self.loading_label.hide()
        self.loading_text.hide()
        if filename and os.path.exists(filename):
            self.completed_label.setText("完成！")
            self.completed_label.setStyleSheet("font-size:16px; color:green; font-weight:bold;")
            self.completed_label.show()
            self.play_btn.show()
            self.export_btn.show()
            self.generate_next_btn.show()
            self.current_midi = filename
            self.progress_bar.setValue(100)
            self.generate_btn.setEnabled(True)
        else:
            self.completed_label.setText("生成失敗！請嘗試更改風格或重試")
            self.completed_label.setStyleSheet("font-size:16px; color:red; font-weight:bold;")
            self.completed_label.show()
            self.generate_btn.setEnabled(True)
            self.progress_bar.hide()

    def play_music(self):
        try:
            if not self.current_midi or not os.path.exists(self.current_midi):
                raise FileNotFoundError("找不到 MIDI 檔案。")
            if sys.platform.startswith('win'):
                os.startfile(self.current_midi)
            elif sys.platform.startswith('darwin'):
                subprocess.call(['open', self.current_midi])
            else:
                subprocess.call(['xdg-open', self.current_midi])
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Information)
            msg.setText("音樂正在播放中！請使用預設程式欣賞。")
            msg.setWindowTitle("播放中")
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec()
        except Exception as e:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setText(f"播放音樂時出錯: {e}")
            msg.setWindowTitle("錯誤")
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec()

    def export_midi(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存 MIDI 文件", "", "MIDI Files (*.mid);;All Files (*)", options=options)
        if file_path:
            try:
                if not self.current_midi or not os.path.exists(self.current_midi):
                    raise FileNotFoundError("找不到 MIDI 檔案。")
                with open(self.current_midi, 'rb') as src, open(file_path, 'wb') as dst:
                    dst.write(src.read())
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Information)
                msg.setText("MIDI 文件已成功導出！")
                msg.setWindowTitle("成功")
                msg.setStandardButtons(QMessageBox.Ok)
                msg.exec()
            except Exception as e:
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Critical)
                msg.setText(f"導出 MIDI 時出錯: {e}")
                msg.setWindowTitle("錯誤")
                msg.setStandardButtons(QMessageBox.Ok)
                msg.exec()

    def generate_next(self):
        self.completed_label.hide()
        self.play_btn.hide()
        self.export_btn.hide()
        self.generate_next_btn.hide()
        self.generate_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.progress_bar.hide()

    def closeEvent(self, event):
        if self.generator_thread and self.generator_thread.isRunning():
            self.generator_thread.terminate()
            self.generator_thread.wait()
        event.accept()

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def update_loading_animation(self):
        states = [".", "..", "..."]
        self.loading_state = (self.loading_state + 1) % len(states)
        self.loading_label.setText(states[self.loading_state])


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MusicGeneratorApp()
    window.show()
    sys.exit(app.exec())
