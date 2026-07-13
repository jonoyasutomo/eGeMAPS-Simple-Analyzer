import sys
from pathlib import Path
import tempfile
import os
import json
import re
import subprocess
import uuid

import numpy as np
import pandas as pd
import soundfile as sf
import imageio_ffmpeg

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFileDialog, QMessageBox, QTableWidget, QTableWidgetItem
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


APP_VERSION = "1.7.0"

MAIN_FEATURES = [
    "F0semitoneFrom27.5Hz_sma3nz_pctlrange0-2",
    "loudness_sma3_pctlrange0-2",
    "HNRdBACF_sma3nz_amean",
    "VoicedSegmentsPerSec",
]

SMOOTH_WINDOW_SEC = 0.10
MIN_ACTIVE_SEC = 0.20
MIN_PAUSE_SEC = 0.20
PRE_MARGIN_SEC = 0.05
POST_MARGIN_SEC = 0.10
MIN_REFERENCE_SILENCE_SEC = 1.00
THRESHOLD_METHOD = "reference_silence_p95"


def get_app_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_settings_path():
    base = Path(os.getenv("APPDATA", Path.home())) / "eGeMAPS_Simple_Analyzer"
    base.mkdir(parents=True, exist_ok=True)
    return base / "settings.json"


def load_settings():
    path = get_settings_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(settings):
    get_settings_path().write_text(
        json.dumps(settings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_ffmpeg_path():
    return imageio_ffmpeg.get_ffmpeg_exe()


def subprocess_options():
    options = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "shell": False,
    }
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    return options


def convert_audio_to_analysis_wav(input_path):
    """音声ファイルをmono・16-bit PCM WAVへ変換する。"""
    input_path = Path(input_path)
    ffmpeg_path = get_ffmpeg_path()

    temp_dir = Path(tempfile.gettempdir()) / "egemaps_simple_analyzer"
    temp_dir.mkdir(parents=True, exist_ok=True)
    output_wav = temp_dir / "input_converted_for_analysis.wav"

    command = [
        ffmpeg_path,
        "-y",
        "-i", str(input_path),
        "-vn",
        "-ac", "1",
        "-sample_fmt", "s16",
        str(output_wav),
    ]

    result = subprocess.run(command, **subprocess_options())

    if result.returncode != 0:
        raise RuntimeError(
            "ffmpegによるWAV変換に失敗しました。\n\n"
            f"入力ファイル: {input_path}\n\n"
            f"ffmpeg error:\n{result.stderr}"
        )

    if not output_wav.exists():
        raise FileNotFoundError("変換後WAVファイルが作成されませんでした。")

    info = sf.info(str(output_wav))

    return {
        "converted_wav_path": str(output_wav),
        "input_format": input_path.suffix.lower().replace(".", ""),
        "source_frame_rate_hz": np.nan,
        "source_channels": np.nan,
        "source_sample_width_bytes": np.nan,
        "source_duration_sec": np.nan,
        "converted_channels": 1,
        "converted_sample_width_bytes": 2,
        "converted_sampling_rate_hz": info.samplerate,
        "converted_duration_sec": round(info.duration, 3),
        "converted_to_wav": "yes",
    }


def find_opensmile_components(root):
    """指定フォルダ以下から公式openSMILE実行ファイルとeGeMAPSv02設定を探す。"""
    root = Path(root).resolve()
    if not root.exists():
        return None

    exe_names = {"smilextract.exe", "smilextract"}
    exe_candidates = [
        p for p in root.rglob("*")
        if p.is_file() and p.name.lower() in exe_names
    ]
    config_candidates = [
        p for p in root.rglob("eGeMAPSv02.conf")
        if p.is_file()
    ]

    if not exe_candidates or not config_candidates:
        return None

    def exe_score(path):
        s = str(path).lower()
        score = 0
        if "bin" in path.parts:
            score -= 20
        if "build" in path.parts:
            score += 10
        if path.suffix.lower() == ".exe":
            score -= 5
        return score, len(path.parts)

    def config_score(path):
        s = str(path).lower().replace("\\", "/")
        score = 0
        if "/config/egemaps/v02/" in s:
            score -= 30
        return score, len(path.parts)

    exe_path = sorted(exe_candidates, key=exe_score)[0]
    config_path = sorted(config_candidates, key=config_score)[0]

    return {
        "root": str(root),
        "exe": str(exe_path),
        "config": str(config_path),
    }


def detect_opensmile_version(exe_path):
    try:
        result = subprocess.run([str(exe_path), "-h"], **subprocess_options())
        text = f"{result.stdout}\n{result.stderr}"
        match = re.search(
            r"openSMILE(?:\s+version|\s+v)?\s*([0-9]+(?:\.[0-9]+){1,3})",
            text,
            flags=re.IGNORECASE,
        )
        if match:
            return match.group(1)
        for line in text.splitlines():
            if "opensmile" in line.lower():
                return line.strip()[:160]
    except Exception:
        pass
    return "unknown"


def read_opensmile_csv(path):
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        raise FileNotFoundError(f"openSMILE出力CSVが作成されませんでした: {path}")

    attempts = [
        {"sep": None, "engine": "python"},
        {"sep": ";"},
        {"sep": ","},
        {"sep": "\t"},
    ]
    best = None
    for kwargs in attempts:
        try:
            df = pd.read_csv(path, encoding="utf-8-sig", **kwargs)
            if best is None or df.shape[1] > best.shape[1]:
                best = df
        except Exception:
            continue

    if best is None or best.empty:
        raise ValueError(f"openSMILE出力CSVを読み取れませんでした: {path}")

    best.columns = [str(c).strip().strip('"') for c in best.columns]
    return best


def run_opensmile_command(exe_path, config_path, args):
    exe_path = Path(exe_path).resolve()
    config_path = Path(config_path).resolve()

    if not exe_path.exists():
        raise FileNotFoundError(f"SMILExtractが見つかりません: {exe_path}")
    if not config_path.exists():
        raise FileNotFoundError(f"eGeMAPSv02.confが見つかりません: {config_path}")

    command = [
        str(exe_path),
        "-C", str(config_path),
        *[str(x) for x in args],
        "-loglevel", "1",
    ]

    result = subprocess.run(
        command,
        cwd=str(config_path.parent),
        **subprocess_options(),
    )

    if result.returncode != 0:
        raise RuntimeError(
            "公式openSMILEの実行に失敗しました。\n\n"
            f"実行ファイル: {exe_path}\n"
            f"設定ファイル: {config_path}\n\n"
            f"標準出力:\n{result.stdout}\n\n"
            f"エラー出力:\n{result.stderr}"
        )


def run_opensmile_lld(wav_path, exe_path, config_path):
    temp_dir = Path(tempfile.gettempdir()) / "egemaps_simple_analyzer"
    temp_dir.mkdir(parents=True, exist_ok=True)
    output_path = temp_dir / f"lld_{uuid.uuid4().hex}.csv"

    run_opensmile_command(
        exe_path,
        config_path,
        [
            "-I", Path(wav_path).resolve(),
            "-lldcsvoutput", output_path,
            "-appendcsvlld", "0",
            "-headercsvlld", "1",
            "-timestampcsvlld", "1",
        ],
    )
    return read_opensmile_csv(output_path)


def run_opensmile_functionals(wav_path, exe_path, config_path):
    temp_dir = Path(tempfile.gettempdir()) / "egemaps_simple_analyzer"
    temp_dir.mkdir(parents=True, exist_ok=True)
    output_path = temp_dir / f"functionals_{uuid.uuid4().hex}.csv"

    run_opensmile_command(
        exe_path,
        config_path,
        [
            "-I", Path(wav_path).resolve(),
            "-csvoutput", output_path,
            "-appendcsv", "0",
            "-headercsv", "1",
            "-timestampcsv", "0",
        ],
    )

    df = read_opensmile_csv(output_path)
    metadata_names = {
        "name", "frametime", "frameindex", "timestamp", "instance",
    }
    keep_columns = [
        c for c in df.columns
        if c.strip().lower() not in metadata_names
    ]
    df = df[keep_columns].copy()

    for col in df.columns:
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().any():
            df[col] = converted

    if len(df) > 1:
        df = df.iloc[[0]].reset_index(drop=True)
    else:
        df = df.reset_index(drop=True)
    return df


def moving_average(values, window_size):
    if window_size <= 1:
        return values
    kernel = np.ones(window_size) / window_size
    return np.convolve(values, kernel, mode="same")


def find_first_sustained_active(active, min_frames):
    count = 0
    for i, flag in enumerate(active):
        if flag:
            count += 1
            if count >= min_frames:
                return i - min_frames + 1
        else:
            count = 0
    return None


def find_last_sustained_active(active, min_frames):
    count = 0
    for i in range(len(active) - 1, -1, -1):
        if active[i]:
            count += 1
            if count >= min_frames:
                return i + min_frames - 1
        else:
            count = 0
    return None


def compute_egemaps_loudness_lld(wav_path, total_duration, exe_path, config_path):
    lld = run_opensmile_lld(wav_path, exe_path, config_path)

    loudness_cols = [c for c in lld.columns if "loudness" in str(c).lower()]
    if not loudness_cols:
        raise ValueError("eGeMAPSv02 LLD出力内にloudness列が見つかりませんでした。")

    loudness_col = loudness_cols[0]
    values = pd.to_numeric(lld[loudness_col], errors="coerce").to_numpy(dtype=float)

    lower_map = {str(c).lower(): c for c in lld.columns}
    time_col = None
    for candidate in ["frametime", "timestamp", "time"]:
        if candidate in lower_map:
            time_col = lower_map[candidate]
            break

    if time_col is not None:
        times = pd.to_numeric(lld[time_col], errors="coerce").to_numpy(dtype=float)
    else:
        times = np.linspace(0, total_duration, len(values), endpoint=False)

    valid = np.isfinite(values) & np.isfinite(times)
    if valid.sum() < 5:
        raise ValueError("有効なloudness値が少なすぎます。")

    values = values[valid]
    times = times[valid]

    order = np.argsort(times)
    times = times[order]
    values = values[order]

    if len(times) >= 2:
        positive_diffs = np.diff(times)
        positive_diffs = positive_diffs[positive_diffs > 0]
        frame_step = float(np.median(positive_diffs)) if len(positive_diffs) else 0.01
    else:
        frame_step = 0.01

    smooth_frames = max(1, int(round(SMOOTH_WINDOW_SEC / frame_step)))
    values_smooth = moving_average(values, smooth_frames)

    return {
        "times": times,
        "values": values,
        "values_smooth": values_smooth,
        "frame_step": frame_step,
        "feature": loudness_col,
    }


def compute_pause_and_speech_metrics(
    times,
    active,
    frame_step,
    speech_onset_candidate_sec,
    speech_offset_candidate_sec,
    analysis_duration_sec,
):
    in_speech_window = (
        (times >= speech_onset_candidate_sec) &
        (times <= speech_offset_candidate_sec)
    )

    if in_speech_window.sum() == 0:
        return {
            "total_speaking_sec": 0.0,
            "speech_ratio": 0.0,
            "pause_count": 0,
            "mean_pause_duration_sec": np.nan,
        }

    active_window = active[in_speech_window]

    total_speaking_sec = float(np.sum(active_window) * frame_step)
    total_speaking_sec = min(
        total_speaking_sec,
        max(0.0, speech_offset_candidate_sec - speech_onset_candidate_sec)
    )

    speech_ratio = (
        total_speaking_sec / analysis_duration_sec
        if analysis_duration_sec > 0 else 0.0
    )

    pause_durations = []
    count = 0

    for flag in active_window:
        if not flag:
            count += 1
        else:
            if count > 0:
                duration = count * frame_step
                if duration >= MIN_PAUSE_SEC:
                    pause_durations.append(duration)
                count = 0

    if count > 0:
        duration = count * frame_step
        if duration >= MIN_PAUSE_SEC:
            pause_durations.append(duration)

    pause_count = len(pause_durations)
    mean_pause_duration_sec = (
        float(np.mean(pause_durations)) if pause_durations else np.nan
    )

    return {
        "total_speaking_sec": round(total_speaking_sec, 3),
        "speech_ratio": round(speech_ratio, 4),
        "pause_count": pause_count,
        "mean_pause_duration_sec": (
            round(mean_pause_duration_sec, 3)
            if np.isfinite(mean_pause_duration_sec) else np.nan
        ),
    }


def estimate_segment_from_reference_silence(
    wav_path,
    total_duration,
    initial_silence_start,
    initial_silence_end,
    final_silence_start,
    final_silence_end,
    exe_path,
    config_path,
):
    if not (0 <= initial_silence_start < initial_silence_end <= total_duration):
        raise ValueError("発話前無音基準区間の指定が不正です。")

    if not (0 <= final_silence_start < final_silence_end <= total_duration):
        raise ValueError("発話後無音基準区間の指定が不正です。")

    if initial_silence_end >= final_silence_start:
        raise ValueError("発話前無音基準区間と発話後無音基準区間が重なっています。")

    loudness_info = compute_egemaps_loudness_lld(
        wav_path,
        total_duration,
        exe_path,
        config_path,
    )

    times = loudness_info["times"]
    values_smooth = loudness_info["values_smooth"]
    frame_step = loudness_info["frame_step"]

    noise_mask = (
        ((times >= initial_silence_start) & (times <= initial_silence_end)) |
        ((times >= final_silence_start) & (times <= final_silence_end))
    )

    noise_values = values_smooth[noise_mask]
    if len(noise_values) < 3:
        raise ValueError("指定された無音基準区間内のloudnessフレームが少なすぎます。")

    noise_p95 = np.percentile(noise_values, 95)
    global_p95 = np.percentile(values_smooth, 95)
    threshold = noise_p95
    active = values_smooth > threshold

    search_mask = (times >= initial_silence_end) & (times <= final_silence_start)
    active_search = active & search_mask

    min_active_frames = max(1, int(round(MIN_ACTIVE_SEC / frame_step)))
    first_idx = find_first_sustained_active(active_search, min_active_frames)
    last_idx = find_last_sustained_active(active_search, min_active_frames)

    if first_idx is None or last_idx is None or last_idx <= first_idx:
        raise ValueError(
            "発話開始・終了の自動推定に失敗しました。"
            "発話前後の無音基準区間を見直してください。"
        )

    speech_onset_candidate_sec = max(0.0, float(times[first_idx]) - frame_step / 2)
    speech_offset_candidate_sec = min(
        total_duration,
        float(times[last_idx]) + frame_step / 2,
    )

    start_sec = max(0.0, speech_onset_candidate_sec - PRE_MARGIN_SEC)
    end_sec = min(total_duration, speech_offset_candidate_sec + POST_MARGIN_SEC)
    analysis_duration_sec = max(0.0, end_sec - start_sec)

    pause_metrics = compute_pause_and_speech_metrics(
        times=times,
        active=active,
        frame_step=frame_step,
        speech_onset_candidate_sec=speech_onset_candidate_sec,
        speech_offset_candidate_sec=speech_offset_candidate_sec,
        analysis_duration_sec=analysis_duration_sec,
    )

    loudness_info["threshold"] = float(threshold)
    loudness_info["noise_p95"] = float(noise_p95)
    loudness_info["global_p95"] = float(global_p95)
    loudness_info["active"] = active

    return {
        "start_sec": round(start_sec, 3),
        "end_sec": round(end_sec, 3),
        "speech_onset_candidate_sec": round(speech_onset_candidate_sec, 3),
        "speech_offset_candidate_sec": round(speech_offset_candidate_sec, 3),
        "onset_latency_sec": round(speech_onset_candidate_sec, 3),
        "initial_silence_sec": round(start_sec, 3),
        "final_silence_sec": round(max(0.0, total_duration - end_sec), 3),
        "threshold": float(threshold),
        "noise_p95": float(noise_p95),
        "global_p95": float(global_p95),
        "feature": loudness_info["feature"],
        "loudness_info": loudness_info,
        "total_speaking_sec": pause_metrics["total_speaking_sec"],
        "speech_ratio": pause_metrics["speech_ratio"],
        "pause_count": pause_metrics["pause_count"],
        "mean_pause_duration_sec": pause_metrics["mean_pause_duration_sec"],
        "message": (
            "指定された発話前・発話後の無音基準区間における"
            "eGeMAPSv02 LLD loudnessの95パーセンタイル値を閾値として、"
            "発話開始時刻と発話終了時刻を自動推定しました。"
        ),
    }


class App(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(f"eGeMAPS Simple Analyzer v{APP_VERSION}")
        self.resize(1080, 960)

        self.original_file_path = None
        self.analysis_wav_path = None
        self.convert_info = {}

        self.signal = None
        self.sampling_rate = None
        self.total_duration = None
        self.result_df = None
        self.loudness_info = None

        self.default_initial_noise = None
        self.default_final_noise = None

        self.opensmile_root = None
        self.opensmile_exe = None
        self.opensmile_config = None
        self.opensmile_version = "unknown"

        self.segment_selection_method = (
            "automatic_reference_silence_external_openSMILE_"
            "eGeMAPSv02_LLD_loudness"
        )
        self.last_estimation_info = {
            "initial_silence_sec": np.nan,
            "final_silence_sec": np.nan,
            "threshold": np.nan,
            "noise_p95": np.nan,
            "global_p95": np.nan,
            "feature": "",
            "message": "",
            "speech_onset_candidate_sec": np.nan,
            "speech_offset_candidate_sec": np.nan,
            "onset_latency_sec": np.nan,
            "total_speaking_sec": np.nan,
            "speech_ratio": np.nan,
            "pause_count": np.nan,
            "mean_pause_duration_sec": np.nan,
        }

        layout = QVBoxLayout()

        title = QLabel(f"eGeMAPS Simple Analyzer v{APP_VERSION}")
        layout.addWidget(title)

        opensmile_layout = QHBoxLayout()
        self.opensmile_status_label = QLabel("公式openSMILE：未設定")
        self.opensmile_button = QPushButton("公式openSMILEフォルダを選択")
        self.opensmile_button.clicked.connect(self.select_opensmile_folder)
        opensmile_layout.addWidget(self.opensmile_status_label, 1)
        opensmile_layout.addWidget(self.opensmile_button)
        layout.addLayout(opensmile_layout)

        self.id_input = QLineEdit()
        self.id_input.setPlaceholderText("例：P001")
        layout.addWidget(QLabel("Participant ID"))
        layout.addWidget(self.id_input)

        self.file_label = QLabel("音声ファイル未選択")
        self.file_button = QPushButton(
            "音声ファイルを選択（wav / m4a / mp3 / mp4 / aac / flac）"
        )
        self.file_button.clicked.connect(self.select_file)
        layout.addWidget(QLabel("音声ファイル"))
        layout.addWidget(self.file_label)
        layout.addWidget(self.file_button)

        self.audio_info_label = QLabel("音声情報：未読み込み")
        layout.addWidget(self.audio_info_label)

        self.figure = Figure(figsize=(9, 4.5))
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(QLabel(
            "上段：波形 / 下段：eGeMAPSv02 LLD loudness と閾値ライン"
        ))
        layout.addWidget(self.canvas)

        layout.addWidget(QLabel("発話前無音基準区間：初期値 1.0〜4.0秒"))
        initial_noise_layout = QHBoxLayout()
        self.initial_noise_start_input = QLineEdit()
        self.initial_noise_end_input = QLineEdit()
        initial_noise_layout.addWidget(QLabel("開始秒"))
        initial_noise_layout.addWidget(self.initial_noise_start_input)
        initial_noise_layout.addWidget(QLabel("終了秒"))
        initial_noise_layout.addWidget(self.initial_noise_end_input)
        layout.addLayout(initial_noise_layout)

        layout.addWidget(QLabel(
            "発話後無音基準区間：初期値 音声長−4.0秒〜音声長−1.0秒"
        ))
        final_noise_layout = QHBoxLayout()
        self.final_noise_start_input = QLineEdit()
        self.final_noise_end_input = QLineEdit()
        final_noise_layout.addWidget(QLabel("開始秒"))
        final_noise_layout.addWidget(self.final_noise_start_input)
        final_noise_layout.addWidget(QLabel("終了秒"))
        final_noise_layout.addWidget(self.final_noise_end_input)
        layout.addLayout(final_noise_layout)

        estimate_layout = QHBoxLayout()
        self.reestimate_button = QPushButton("基準無音区間から再推定")
        self.reestimate_button.clicked.connect(
            lambda: self.estimate_from_reference_intervals(show_message=True)
        )
        estimate_layout.addWidget(self.reestimate_button)

        self.reset_reference_button = QPushButton("基準無音区間を初期値に戻す")
        self.reset_reference_button.clicked.connect(self.reset_reference_intervals)
        estimate_layout.addWidget(self.reset_reference_button)
        layout.addLayout(estimate_layout)

        self.start_input = QLineEdit()
        self.start_input.setReadOnly(True)
        self.end_input = QLineEdit()
        self.end_input.setReadOnly(True)

        layout.addWidget(QLabel("自動決定された解析開始秒"))
        layout.addWidget(self.start_input)
        layout.addWidget(QLabel("自動決定された解析終了秒"))
        layout.addWidget(self.end_input)

        self.silence_info_label = QLabel("無音・閾値情報：未実行")
        layout.addWidget(self.silence_info_label)

        self.additional_info_label = QLabel("補助指標：未実行")
        layout.addWidget(self.additional_info_label)

        self.analyze_button = QPushButton("解析開始")
        self.analyze_button.clicked.connect(self.analyze)
        layout.addWidget(self.analyze_button)

        self.status_label = QLabel("状態：待機中")
        layout.addWidget(self.status_label)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Feature", "Value"])
        layout.addWidget(QLabel("主要特徴量"))
        layout.addWidget(self.table)

        self.save_button = QPushButton("全解析結果をCSV保存")
        self.save_button.clicked.connect(self.save_csv)
        layout.addWidget(self.save_button)

        self.setLayout(layout)
        self.draw_empty_plot()
        self.auto_configure_opensmile()

    def auto_configure_opensmile(self):
        settings = load_settings()
        candidates = [get_app_dir()]
        saved_root = settings.get("opensmile_root")
        if saved_root:
            candidates.append(Path(saved_root))

        for root in candidates:
            components = find_opensmile_components(root)
            if components:
                self.apply_opensmile_components(components, save=True)
                return

        self.opensmile_status_label.setText(
            "公式openSMILE：未設定（フォルダを選択してください）"
        )

    def apply_opensmile_components(self, components, save=True):
        self.opensmile_root = components["root"]
        self.opensmile_exe = components["exe"]
        self.opensmile_config = components["config"]
        self.opensmile_version = detect_opensmile_version(self.opensmile_exe)

        self.opensmile_status_label.setText(
            f"公式openSMILE：設定済み / version {self.opensmile_version} / "
            f"{self.opensmile_exe}"
        )

        if save:
            settings = load_settings()
            settings["opensmile_root"] = self.opensmile_root
            save_settings(settings)

    def select_opensmile_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "公式openSMILEを展開したフォルダを選択",
            str(get_app_dir()),
        )
        if not folder:
            return

        components = find_opensmile_components(folder)
        if not components:
            QMessageBox.critical(
                self,
                "openSMILEが見つかりません",
                "選択したフォルダ以下に、SMILExtract.exeと"
                "eGeMAPSv02.confの両方が見つかりませんでした。\n\n"
                "公式openSMILEのZIPを展開した最上位フォルダを選択してください。",
            )
            return

        self.apply_opensmile_components(components, save=True)
        QMessageBox.information(
            self,
            "設定完了",
            "公式openSMILEを設定しました。\n\n"
            f"SMILExtract:\n{self.opensmile_exe}\n\n"
            f"eGeMAPSv02.conf:\n{self.opensmile_config}\n\n"
            f"検出バージョン: {self.opensmile_version}",
        )

    def ensure_opensmile_ready(self):
        if not self.opensmile_exe or not Path(self.opensmile_exe).exists():
            raise ValueError(
                "公式openSMILEが設定されていません。"
                "「公式openSMILEフォルダを選択」から設定してください。"
            )
        if not self.opensmile_config or not Path(self.opensmile_config).exists():
            raise ValueError(
                "eGeMAPSv02.confが見つかりません。"
                "公式openSMILEフォルダを再設定してください。"
            )

    def draw_empty_plot(self):
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.set_title("No audio loaded")
        ax.set_xlabel("Time (sec)")
        ax.set_ylabel("Amplitude")
        self.canvas.draw()

    def select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "音声ファイルを選択",
            "",
            "Audio Files (*.wav *.m4a *.mp3 *.mp4 *.aac *.flac);;All Files (*.*)",
        )

        if file_path:
            self.original_file_path = file_path
            self.file_label.setText(file_path)
            self.result_df = None
            self.loudness_info = None

            try:
                self.ensure_opensmile_ready()
                self.status_label.setText("状態：音声ファイルをWAVに変換中...")
                QApplication.processEvents()

                self.convert_info = convert_audio_to_analysis_wav(file_path)
                self.analysis_wav_path = self.convert_info["converted_wav_path"]

                self.signal, self.sampling_rate = self.load_audio_mono()
                self.total_duration = len(self.signal) / self.sampling_rate

                self.audio_info_label.setText(
                    f"音声情報：{self.total_duration:.3f} 秒 / "
                    f"{self.sampling_rate} Hz / "
                    f"入力形式 {self.convert_info.get('input_format', '')} → WAV変換済み"
                )

                if self.total_duration <= 8.0:
                    QMessageBox.warning(
                        self,
                        "注意",
                        "音声長が8秒以下です。初期基準区間 1.0〜4.0秒 および "
                        "末尾−4.0〜−1.0秒 が重なる可能性があります。",
                    )

                initial_start = 1.0
                initial_end = min(4.0, self.total_duration)
                final_start = max(0.0, self.total_duration - 4.0)
                final_end = max(0.0, self.total_duration - 1.0)

                self.default_initial_noise = (initial_start, initial_end)
                self.default_final_noise = (final_start, final_end)

                self.initial_noise_start_input.setText(str(round(initial_start, 3)))
                self.initial_noise_end_input.setText(str(round(initial_end, 3)))
                self.final_noise_start_input.setText(str(round(final_start, 3)))
                self.final_noise_end_input.setText(str(round(final_end, 3)))

                self.start_input.setText("")
                self.end_input.setText("")
                self.silence_info_label.setText("無音・閾値情報：未実行")
                self.additional_info_label.setText("補助指標：未実行")

                self.status_label.setText("状態：WAV変換完了。自動推定中...")
                QApplication.processEvents()
                self.estimate_from_reference_intervals(show_message=False)

            except Exception as e:
                self.audio_info_label.setText("音声情報：読み込みまたは変換失敗")
                self.status_label.setText("状態：音声読み込みまたは推定エラー")
                QMessageBox.critical(self, "エラー", str(e))
                self.plot_all()

    def load_audio_mono(self):
        if not self.analysis_wav_path:
            raise ValueError("解析用WAVファイルがありません。")

        signal, sampling_rate = sf.read(self.analysis_wav_path)
        if signal.ndim == 2:
            signal = np.mean(signal, axis=1)
        return signal, sampling_rate

    def get_reference_intervals_from_inputs(self):
        if self.total_duration is None:
            raise ValueError("音声ファイルを選択してください。")

        initial_start = float(self.initial_noise_start_input.text())
        initial_end = float(self.initial_noise_end_input.text())
        final_start = float(self.final_noise_start_input.text())
        final_end = float(self.final_noise_end_input.text())

        if not (0 <= initial_start < initial_end <= self.total_duration):
            raise ValueError("発話前無音基準区間の指定が不正です。")
        if not (0 <= final_start < final_end <= self.total_duration):
            raise ValueError("発話後無音基準区間の指定が不正です。")
        if initial_end >= final_start:
            raise ValueError("発話前無音基準区間と発話後無音基準区間が重なっています。")

        return initial_start, initial_end, final_start, final_end

    def get_reference_silence_quality(self):
        initial_start, initial_end, final_start, final_end = (
            self.get_reference_intervals_from_inputs()
        )
        initial_duration = initial_end - initial_start
        final_duration = final_end - final_start
        initial_short = initial_duration < MIN_REFERENCE_SILENCE_SEC
        final_short = final_duration < MIN_REFERENCE_SILENCE_SEC
        return {
            "initial_duration": round(initial_duration, 3),
            "final_duration": round(final_duration, 3),
            "minimum_duration": round(min(initial_duration, final_duration), 3),
            "initial_too_short": "yes" if initial_short else "no",
            "final_too_short": "yes" if final_short else "no",
            "any_too_short": initial_short or final_short,
        }

    def get_auto_segment_from_inputs(self):
        if self.total_duration is None:
            raise ValueError("音声ファイルを選択してください。")

        start_sec = float(self.start_input.text())
        end_sec = float(self.end_input.text())

        if start_sec < 0:
            raise ValueError("解析開始秒は0以上にしてください。")
        if end_sec <= start_sec:
            raise ValueError("解析終了秒は開始秒より大きくしてください。")
        if end_sec > self.total_duration:
            raise ValueError(
                f"解析終了秒が音声長を超えています。"
                f"音声長は {self.total_duration:.3f} 秒です。"
            )
        return start_sec, end_sec

    def reference_silence_adjusted(self):
        try:
            current_initial = (
                float(self.initial_noise_start_input.text()),
                float(self.initial_noise_end_input.text()),
            )
            current_final = (
                float(self.final_noise_start_input.text()),
                float(self.final_noise_end_input.text()),
            )
        except Exception:
            return "unknown"

        if self.default_initial_noise is None or self.default_final_noise is None:
            return "unknown"

        tolerance = 1e-6
        initial_same = (
            abs(current_initial[0] - self.default_initial_noise[0]) < tolerance and
            abs(current_initial[1] - self.default_initial_noise[1]) < tolerance
        )
        final_same = (
            abs(current_final[0] - self.default_final_noise[0]) < tolerance and
            abs(current_final[1] - self.default_final_noise[1]) < tolerance
        )
        return "no" if initial_same and final_same else "yes"

    def plot_all(self):
        if self.signal is None or self.sampling_rate is None:
            self.draw_empty_plot()
            return

        try:
            start_sec, end_sec = self.get_auto_segment_from_inputs()
        except Exception:
            start_sec, end_sec = None, None

        try:
            initial_start, initial_end, final_start, final_end = (
                self.get_reference_intervals_from_inputs()
            )
        except Exception:
            initial_start = initial_end = final_start = final_end = None

        signal = self.signal
        sr = self.sampling_rate
        total_duration = self.total_duration

        max_points = 20000
        if len(signal) > max_points:
            step = int(np.ceil(len(signal) / max_points))
            plot_signal = signal[::step]
            plot_times = np.arange(len(plot_signal)) * step / sr
        else:
            plot_signal = signal
            plot_times = np.arange(len(signal)) / sr

        self.figure.clear()
        ax1 = self.figure.add_subplot(211)
        ax2 = self.figure.add_subplot(212, sharex=ax1)

        ax1.plot(plot_times, plot_signal, linewidth=0.5)

        if initial_start is not None:
            ax1.axvspan(initial_start, initial_end, alpha=0.15)
            ax1.axvspan(final_start, final_end, alpha=0.15)

        if start_sec is not None and end_sec is not None and end_sec > start_sec:
            ax1.axvspan(start_sec, end_sec, alpha=0.25)
            ax1.axvline(start_sec, linewidth=1.2)
            ax1.axvline(end_sec, linewidth=1.2)

        ax1.set_xlim(0, total_duration)
        ax1.set_ylabel("Amplitude")
        ax1.set_title(
            "Waveform: reference silence intervals and automatically determined segment"
        )

        if self.loudness_info is not None:
            times = self.loudness_info["times"]
            values_smooth = self.loudness_info["values_smooth"]
            ax2.plot(times, values_smooth, linewidth=0.8)

            threshold = self.last_estimation_info.get("threshold", np.nan)
            if np.isfinite(threshold):
                ax2.axhline(threshold, linestyle="--", linewidth=1.2)

            if initial_start is not None:
                ax2.axvspan(initial_start, initial_end, alpha=0.15)
                ax2.axvspan(final_start, final_end, alpha=0.15)

            if start_sec is not None and end_sec is not None and end_sec > start_sec:
                ax2.axvspan(start_sec, end_sec, alpha=0.25)
                ax2.axvline(start_sec, linewidth=1.2)
                ax2.axvline(end_sec, linewidth=1.2)

            ax2.set_ylabel("LLD loudness")
            ax2.set_title(
                "eGeMAPSv02 LLD loudness: dashed line = reference_silence_p95"
            )
        else:
            ax2.text(
                0.02, 0.5, "LLD loudness is not calculated yet.",
                transform=ax2.transAxes,
            )
            ax2.set_ylabel("LLD loudness")

        ax2.set_xlabel("Time (sec)")
        self.figure.tight_layout()
        self.canvas.draw()

    def reset_reference_intervals(self):
        if self.default_initial_noise is None or self.default_final_noise is None:
            QMessageBox.warning(self, "注意", "音声ファイルを選択してください。")
            return

        self.initial_noise_start_input.setText(
            str(round(self.default_initial_noise[0], 3))
        )
        self.initial_noise_end_input.setText(
            str(round(self.default_initial_noise[1], 3))
        )
        self.final_noise_start_input.setText(
            str(round(self.default_final_noise[0], 3))
        )
        self.final_noise_end_input.setText(
            str(round(self.default_final_noise[1], 3))
        )
        self.estimate_from_reference_intervals(show_message=True)

    def estimate_from_reference_intervals(self, show_message=True):
        try:
            self.ensure_opensmile_ready()
            if self.signal is None or self.sampling_rate is None:
                raise ValueError("音声ファイルを選択してください。")

            initial_start, initial_end, final_start, final_end = (
                self.get_reference_intervals_from_inputs()
            )
            quality = self.get_reference_silence_quality()

            if quality["any_too_short"] and show_message:
                QMessageBox.warning(
                    self,
                    "基準無音区間が短いです",
                    f"発話前基準無音区間：{quality['initial_duration']:.3f} 秒\n"
                    f"発話後基準無音区間：{quality['final_duration']:.3f} 秒\n\n"
                    f"いずれかが {MIN_REFERENCE_SILENCE_SEC:.1f} 秒未満です。"
                    "推定は続行しますが、可能であれば1秒以上、"
                    "できれば約3秒の静かな区間を指定してください。",
                )

            self.status_label.setText(
                "状態：公式openSMILEでLLDを抽出し、解析区間を推定中..."
            )
            QApplication.processEvents()

            info = estimate_segment_from_reference_silence(
                self.analysis_wav_path,
                self.total_duration,
                initial_start,
                initial_end,
                final_start,
                final_end,
                self.opensmile_exe,
                self.opensmile_config,
            )

            self.start_input.setText(str(info["start_sec"]))
            self.end_input.setText(str(info["end_sec"]))
            self.last_estimation_info = info
            self.loudness_info = info["loudness_info"]

            adjusted = self.reference_silence_adjusted()
            short_text = " / 1秒未満警告あり" if quality["any_too_short"] else ""

            self.silence_info_label.setText(
                f"無音・閾値情報：閾値 {info['threshold']:.6f} / "
                f"解析区間 {info['start_sec']}〜{info['end_sec']} 秒 / "
                f"基準無音 前{quality['initial_duration']:.3f}秒・"
                f"後{quality['final_duration']:.3f}秒 / "
                f"修正 {adjusted}{short_text}"
            )

            mean_pause = info["mean_pause_duration_sec"]
            mean_pause_text = (
                f"{mean_pause} 秒" if np.isfinite(mean_pause) else "N/A（休止なし）"
            )
            self.additional_info_label.setText(
                f"補助指標：onset {info['onset_latency_sec']} 秒 / "
                f"speaking {info['total_speaking_sec']} 秒 / "
                f"speech_ratio {info['speech_ratio']} / "
                f"pause_count {info['pause_count']} / "
                f"mean_pause {mean_pause_text}"
            )

            self.plot_all()
            self.status_label.setText("状態：解析区間を自動推定しました")

            if show_message:
                QMessageBox.information(
                    self,
                    "推定完了",
                    f"{info['message']}\n\n"
                    f"自動推定開始秒: {info['start_sec']}\n"
                    f"自動推定終了秒: {info['end_sec']}\n"
                    f"発話開始候補: {info['speech_onset_candidate_sec']}\n"
                    f"発話終了候補: {info['speech_offset_candidate_sec']}\n"
                    f"onset_latency_sec: {info['onset_latency_sec']}\n"
                    f"total_speaking_sec: {info['total_speaking_sec']}\n"
                    f"speech_ratio: {info['speech_ratio']}\n"
                    f"pause_count: {info['pause_count']}\n"
                    f"mean_pause_duration_sec: {mean_pause_text}\n"
                    f"発話前基準無音長: {quality['initial_duration']} 秒\n"
                    f"発話後基準無音長: {quality['final_duration']} 秒\n"
                    f"基準無音区間を修正したか: {adjusted}\n"
                    f"使用特徴量: {info['feature']}\n"
                    f"loudness閾値: {info['threshold']:.6f}\n"
                    f"閾値法: {THRESHOLD_METHOD}\n"
                    f"openSMILE version: {self.opensmile_version}\n\n"
                    "明らかな誤りがある場合のみ、発話前後の基準無音区間を"
                    "修正して再推定してください。",
                )

        except Exception as e:
            self.status_label.setText("状態：推定エラー")
            self.plot_all()
            if show_message:
                QMessageBox.critical(self, "エラー", str(e))
            else:
                raise

    def analyze(self):
        try:
            self.ensure_opensmile_ready()
            participant_id = self.id_input.text().strip()
            if not participant_id:
                raise ValueError("Participant IDを入力してください。")
            if self.signal is None or self.sampling_rate is None:
                raise ValueError("音声ファイルを選択してください。")

            start_sec, end_sec = self.get_auto_segment_from_inputs()
            quality = self.get_reference_silence_quality()

            if quality["any_too_short"]:
                QMessageBox.warning(
                    self,
                    "基準無音区間が短い状態で解析します",
                    f"発話前：{quality['initial_duration']:.3f} 秒 / "
                    f"発話後：{quality['final_duration']:.3f} 秒\n"
                    "警告情報はCSVに保存されます。",
                )

            self.status_label.setText("状態：音声区間を切り出し中...")
            QApplication.processEvents()

            start_sample = int(start_sec * self.sampling_rate)
            end_sample = int(end_sec * self.sampling_rate)
            segment = self.signal[start_sample:end_sample]
            if len(segment) == 0:
                raise ValueError("解析区間が空です。")

            temp_dir = Path(tempfile.gettempdir()) / "egemaps_simple_analyzer"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_wav = temp_dir / "segment_for_opensmile.wav"
            sf.write(str(temp_wav), segment, self.sampling_rate, subtype="PCM_16")

            self.status_label.setText(
                "状態：利用者が取得した公式openSMILE/eGeMAPSv02で解析中..."
            )
            QApplication.processEvents()

            df = run_opensmile_functionals(
                temp_wav,
                self.opensmile_exe,
                self.opensmile_config,
            )

            initial_start, initial_end, final_start, final_end = (
                self.get_reference_intervals_from_inputs()
            )
            info = self.last_estimation_info

            metadata = [
                ("app_version", APP_VERSION),
                ("participant_id", participant_id),
                ("original_file", Path(self.original_file_path).name),
                ("input_format", self.convert_info.get("input_format", "")),
                ("converted_to_wav", self.convert_info.get("converted_to_wav", "yes")),
                ("source_frame_rate_hz", self.convert_info.get("source_frame_rate_hz", np.nan)),
                ("source_channels", self.convert_info.get("source_channels", np.nan)),
                ("source_sample_width_bytes", self.convert_info.get("source_sample_width_bytes", np.nan)),
                ("source_duration_sec", self.convert_info.get("source_duration_sec", np.nan)),
                ("sampling_rate_hz", self.sampling_rate),
                ("audio_total_duration_sec", round(self.total_duration, 3)),
                ("auto_trim_start_sec", start_sec),
                ("auto_trim_end_sec", end_sec),
                ("final_trim_start_sec", start_sec),
                ("final_trim_end_sec", end_sec),
                ("analysis_duration_sec", round(end_sec - start_sec, 3)),
                ("speech_onset_candidate_sec", info.get("speech_onset_candidate_sec", np.nan)),
                ("speech_offset_candidate_sec", info.get("speech_offset_candidate_sec", np.nan)),
                ("onset_latency_sec", info.get("onset_latency_sec", np.nan)),
                ("total_speaking_sec", info.get("total_speaking_sec", np.nan)),
                ("speech_ratio", info.get("speech_ratio", np.nan)),
                ("pause_count", info.get("pause_count", np.nan)),
                ("mean_pause_duration_sec", info.get("mean_pause_duration_sec", np.nan)),
                ("initial_silence_sec", round(start_sec, 3)),
                ("final_silence_sec", round(max(0.0, self.total_duration - end_sec), 3)),
                ("reference_initial_silence_start_sec", initial_start),
                ("reference_initial_silence_end_sec", initial_end),
                ("reference_initial_silence_duration_sec", quality["initial_duration"]),
                ("reference_final_silence_start_sec", final_start),
                ("reference_final_silence_end_sec", final_end),
                ("reference_final_silence_duration_sec", quality["final_duration"]),
                ("reference_silence_min_duration_sec", quality["minimum_duration"]),
                ("reference_initial_silence_too_short", quality["initial_too_short"]),
                ("reference_final_silence_too_short", quality["final_too_short"]),
                ("reference_silence_adjusted", self.reference_silence_adjusted()),
                ("segment_selection_method", self.segment_selection_method),
                ("silence_estimation_feature", info.get("feature", "")),
                ("threshold_method", THRESHOLD_METHOD),
                ("silence_estimation_threshold_loudness", info.get("threshold", np.nan)),
                ("silence_noise_p95_loudness", info.get("noise_p95", np.nan)),
                ("global_p95_loudness", info.get("global_p95", np.nan)),
                ("smooth_window_sec", SMOOTH_WINDOW_SEC),
                ("min_active_sec", MIN_ACTIVE_SEC),
                ("min_pause_sec", MIN_PAUSE_SEC),
                ("pre_margin_sec", PRE_MARGIN_SEC),
                ("post_margin_sec", POST_MARGIN_SEC),
                ("min_reference_silence_sec", MIN_REFERENCE_SILENCE_SEC),
                ("feature_set", "eGeMAPSv02"),
                ("feature_level", "Functionals"),
                ("opensmile_included_with_gui", "no"),
                ("opensmile_acquisition", "obtained_separately_by_user"),
                ("opensmile_version", self.opensmile_version),
                ("opensmile_executable_path", self.opensmile_exe),
                ("opensmile_config_path", self.opensmile_config),
            ]

            for index, (name, value) in enumerate(metadata):
                df.insert(index, name, value)

            self.result_df = df
            self.show_main_features(df)
            self.plot_all()
            self.status_label.setText("状態：解析完了")

        except Exception as e:
            QMessageBox.critical(self, "エラー", str(e))
            self.status_label.setText("状態：エラー")

    def show_main_features(self, df):
        self.table.setRowCount(len(MAIN_FEATURES))
        for i, feature_name in enumerate(MAIN_FEATURES):
            self.table.setItem(i, 0, QTableWidgetItem(feature_name))
            if feature_name in df.columns:
                value = df[feature_name].iloc[0]
                self.table.setItem(i, 1, QTableWidgetItem(str(value)))
            else:
                self.table.setItem(i, 1, QTableWidgetItem("N/A"))
        self.table.resizeColumnsToContents()

    def save_csv(self):
        if self.result_df is None:
            QMessageBox.warning(self, "注意", "先に解析してください。")
            return

        participant_id = self.id_input.text().strip() or "unknown"
        default_name = f"{participant_id}_egemaps_result.csv"
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "CSV保存",
            default_name,
            "CSV Files (*.csv)",
        )

        if save_path:
            self.result_df.to_csv(save_path, index=False, encoding="utf-8-sig")
            QMessageBox.information(self, "保存完了", "CSVを保存しました。")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = App()
    window.show()
    sys.exit(app.exec())
