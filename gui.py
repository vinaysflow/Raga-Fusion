#!/usr/bin/env python3
"""
gui.py — Simple desktop GUI for the Raga-Fusion Music Generator

Provides a file picker, buttons to run each pipeline step (Analyze,
Extract phrases, Assemble, Add production, Validate), and a results
area showing tool output. Runs tools in a background thread so the
window stays responsive.

Usage:
    python gui.py

Requires: Python 3.10+, tkinter (standard library), and the other
project scripts (analyze_raga, extract_phrases, assemble_track,
add_production, validate_track) in the same directory or on PATH.
"""

import json
import queue
import subprocess
import sys
import threading
from pathlib import Path

# Project root = directory containing this script
PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_PHRASE_LIB = PROJECT_ROOT / "data" / "phrases" / "yaman"
DEFAULT_ASSEMBLE_OUT = PROJECT_ROOT / "yaman_test_30s.wav"
DEFAULT_LOFI_OUT = PROJECT_ROOT / "yaman_lofi_final.wav"
DEFAULT_PHRASE_OUT = PROJECT_ROOT / "data" / "phrases" / "yaman"

# Script names (run from PROJECT_ROOT)
SCRIPT_ANALYZE = "analyze_raga.py"
SCRIPT_EXTRACT = "extract_phrases.py"
SCRIPT_ASSEMBLE = "assemble_track.py"
SCRIPT_PRODUCTION = "add_production.py"
SCRIPT_VALIDATE = "validate_track.py"
SCRIPT_GENERATE_MELODY = "generate_melody.py"

DEFAULT_GENERATED_LIB = PROJECT_ROOT / "data" / "phrases" / "yaman_generated"
YAMAN_RULES = PROJECT_ROOT / "data" / "raga_rules" / "yaman.json"
STYLES_JSON = PROJECT_ROOT / "data" / "styles.json"


def run_tool(args: list[str], cwd: Path, log_queue: queue.Queue, emit_final_code: bool = True) -> int:
    """Run a command and put (line, None) for stdout/stderr. If emit_final_code, put (None, code) at end. Returns exit code."""
    try:
        proc = subprocess.Popen(
            args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        stdout = proc.stdout
        if stdout is not None:
            for line in iter(stdout.readline, ""):
                log_queue.put((line, None))
        proc.wait()
        if emit_final_code:
            log_queue.put((None, proc.returncode))
        return proc.returncode
    except FileNotFoundError as e:
        log_queue.put((f"ERROR: Command not found: {args}\n{e}\n", None))
        if emit_final_code:
            log_queue.put((None, 1))
        return 1
    except Exception as e:
        log_queue.put((f"ERROR: {e}\n", None))
        if emit_final_code:
            log_queue.put((None, 1))
        return 1


def start_tool_thread(args: list[str], cwd: Path, log_queue: queue.Queue) -> threading.Thread:
    """Start a thread that runs the tool and feeds log_queue."""
    t = threading.Thread(target=run_tool, args=(args, cwd, log_queue), daemon=True)
    t.start()
    return t


def run_commands_sequence(
    commands: list[tuple[list[str], str]],
    cwd: Path,
    log_queue: queue.Queue,
) -> int:
    """Run each command in sequence; log each with a header. Emits a single (None, code) at the end."""
    exit_code = 0
    for i, (args, title) in enumerate(commands):
        log_queue.put((f"\n{'─' * 40}\n  {title}\n{'─' * 40}\n\n", None))
        is_last = i == len(commands) - 1
        exit_code = run_tool(args, cwd, log_queue, emit_final_code=is_last)
    return exit_code


def main():
    try:
        import tkinter as tk
        from tkinter import filedialog, scrolledtext, messagebox
    except ImportError as e:
        print("Tkinter is not available. Install it for your Python (e.g. on macOS: brew install python-tk).")
        sys.exit(1)

    root = tk.Tk()
    root.title("Raga-Fusion Music Generator")
    root.minsize(640, 480)
    root.geometry("720x560")

    # State
    input_path = tk.StringVar(value="")
    output_path = tk.StringVar(value="")
    phrase_library = tk.StringVar(value=str(DEFAULT_PHRASE_LIB))
    duration_var = tk.StringVar(value="30")
    log_queue = queue.Queue()
    running = [False]  # use list so closure can mutate
    last_output_wav = [str(DEFAULT_LOFI_OUT)]  # for Play button

    def load_styles():
        try:
            if STYLES_JSON.exists():
                with open(STYLES_JSON) as f:
                    return list(json.load(f).keys())
        except Exception:
            pass
        return ["lofi", "ambient", "calm", "upbeat"]

    styles_list = load_styles()
    raga_var = tk.StringVar(value="Yaman")
    style_var = tk.StringVar(value=styles_list[0] if styles_list else "lofi")
    source_var = tk.StringVar(value="From library")

    def poll_log():
        """Drain log_queue and append to results area."""
        while True:
            try:
                line, code = log_queue.get_nowait()
            except queue.Empty:
                break
            if code is not None:
                results.insert(tk.END, f"\n[Exit code: {code}]\n", "exit")
                results.see(tk.END)
                running[0] = False
                status_var.set("Ready")
                continue
            if line:
                results.insert(tk.END, line)
                results.see(tk.END)
        root.after(100, poll_log)

    def browse_input():
        path = filedialog.askopenfilename(
            title="Select audio file",
            initialdir=PROJECT_ROOT,
            filetypes=[
                ("Audio", "*.wav *.mp3"),
                ("WAV", "*.wav"),
                ("MP3", "*.mp3"),
                ("All", "*.*"),
            ],
        )
        if path:
            input_path.set(path)

    def browse_output(is_dir: bool = False):
        if is_dir:
            path = filedialog.askdirectory(title="Select output directory", initialdir=PROJECT_ROOT)
        else:
            path = filedialog.asksaveasfilename(
                title="Save output as",
                initialdir=PROJECT_ROOT,
                defaultextension=".wav",
                filetypes=[("WAV", "*.wav"), ("All", "*.*")],
            )
        if path:
            output_path.set(path)

    def browse_phrase_lib():
        path = filedialog.askdirectory(
            title="Select phrase library (e.g. data/phrases/yaman)",
            initialdir=PROJECT_ROOT,
        )
        if path:
            phrase_library.set(path)

    def append_header(title: str):
        results.insert(tk.END, f"\n{'═' * 60}\n  {title}\n{'═' * 60}\n\n", "header")

    def run_analyze():
        if running[0]:
            messagebox.showwarning("Busy", "A tool is already running.")
            return
        inp = input_path.get().strip()
        if not inp or not Path(inp).exists():
            messagebox.showerror("Missing input", "Please select an audio file (Analyze recording).")
            return
        append_header("ANALYZE RAGA")
        running[0] = True
        status_var.set("Running: Analyze…")
        args = [sys.executable, str(PROJECT_ROOT / SCRIPT_ANALYZE), inp]
        start_tool_thread(args, PROJECT_ROOT, log_queue)

    def run_extract():
        if running[0]:
            messagebox.showwarning("Busy", "A tool is already running.")
            return
        inp = input_path.get().strip()
        if not inp or not Path(inp).exists():
            messagebox.showerror("Missing input", "Please select the long recording (e.g. yaman_full.mp3).")
            return
        out = output_path.get().strip() or str(DEFAULT_PHRASE_OUT)
        Path(out).mkdir(parents=True, exist_ok=True)
        append_header("EXTRACT PHRASES")
        running[0] = True
        status_var.set("Running: Extract phrases…")
        args = [
            sys.executable,
            str(PROJECT_ROOT / SCRIPT_EXTRACT),
            inp,
            "--output", out,
            "--count", "20",
        ]
        start_tool_thread(args, PROJECT_ROOT, log_queue)

    def run_assemble():
        if running[0]:
            messagebox.showwarning("Busy", "A tool is already running.")
            return
        lib = phrase_library.get().strip() or str(DEFAULT_PHRASE_LIB)
        out = output_path.get().strip() or str(DEFAULT_ASSEMBLE_OUT)
        try:
            dur = float(duration_var.get())
        except ValueError:
            dur = 30.0
        if not Path(lib).joinpath("phrases_metadata.json").exists():
            messagebox.showerror("Missing library", f"Phrase library not found: {lib}")
            return
        append_header("ASSEMBLE TRACK")
        running[0] = True
        status_var.set("Running: Assemble…")
        args = [
            sys.executable,
            str(PROJECT_ROOT / SCRIPT_ASSEMBLE),
            "--library", lib,
            "--duration", str(dur),
            "--output", out,
        ]
        start_tool_thread(args, PROJECT_ROOT, log_queue)

    def run_production():
        if running[0]:
            messagebox.showwarning("Busy", "A tool is already running.")
            return
        inp = input_path.get().strip() or str(DEFAULT_ASSEMBLE_OUT)
        if not Path(inp).exists():
            messagebox.showerror("Missing input", "Select the assembled track (e.g. yaman_test_30s.wav) or run Assemble first.")
            return
        out = output_path.get().strip() or str(DEFAULT_LOFI_OUT)
        append_header("ADD LOFI PRODUCTION")
        running[0] = True
        status_var.set("Running: Add production…")
        args = [
            sys.executable,
            str(PROJECT_ROOT / SCRIPT_PRODUCTION),
            inp,
            "--genre", "lofi",
            "--output", out,
        ]
        start_tool_thread(args, PROJECT_ROOT, log_queue)

    def run_validate():
        if running[0]:
            messagebox.showwarning("Busy", "A tool is already running.")
            return
        inp = input_path.get().strip() or str(DEFAULT_LOFI_OUT)
        if not Path(inp).exists():
            messagebox.showerror("Missing input", "Select the final mix (e.g. yaman_lofi_final.wav) or run Add production first.")
            return
        append_header("VALIDATE TRACK")
        running[0] = True
        status_var.set("Running: Validate…")
        args = [sys.executable, str(PROJECT_ROOT / SCRIPT_VALIDATE), inp]
        melody = output_path.get().strip()  # optional: use output field as melody path
        if melody and Path(melody).exists() and melody != inp:
            args.extend(["--melody", melody])
        start_tool_thread(args, PROJECT_ROOT, log_queue)

    def run_generate():
        if running[0]:
            messagebox.showwarning("Busy", "A tool is already running.")
            return
        try:
            dur = float(duration_var.get())
        except ValueError:
            dur = 30.0
        style = style_var.get() if style_var.get() in styles_list else "lofi"
        use_generated = source_var.get() == "Generated"
        lib = str(DEFAULT_GENERATED_LIB) if use_generated else (phrase_library.get().strip() or str(DEFAULT_PHRASE_LIB))
        assembled = PROJECT_ROOT / "yaman_assembled.wav"
        final_out = PROJECT_ROOT / f"yaman_{int(dur)}s_{style}_final.wav"
        last_output_wav[0] = str(final_out)

        commands = []
        if use_generated:
            if not YAMAN_RULES.exists():
                messagebox.showerror("Missing rules", f"Raga rules not found: {YAMAN_RULES}")
                return
            Path(lib).mkdir(parents=True, exist_ok=True)
            commands.append((
                [
                    sys.executable,
                    str(PROJECT_ROOT / SCRIPT_GENERATE_MELODY),
                    "--rules", str(YAMAN_RULES),
                    "--output", lib,
                    "--count", "20",
                ],
                "GENERATE MELODY",
            ))
        if not Path(lib).joinpath("phrases_metadata.json").exists():
            messagebox.showerror("Missing library", f"Phrase library not found: {lib}")
            return
        commands.append((
            [
                sys.executable, str(PROJECT_ROOT / SCRIPT_ASSEMBLE),
                "--library", lib,
                "--duration", str(dur),
                "--output", str(assembled),
            ],
            "ASSEMBLE TRACK",
        ))
        commands.append((
            [
                sys.executable, str(PROJECT_ROOT / SCRIPT_PRODUCTION),
                str(assembled),
                "--style", style,
                "--output", str(final_out),
            ],
            "ADD PRODUCTION",
        ))
        append_header("GENERATE FLOW")
        running[0] = True
        status_var.set("Running: Generate…")

        def workflow():
            run_commands_sequence(commands, PROJECT_ROOT, log_queue)

        threading.Thread(target=workflow, daemon=True).start()

    def play_last():
        path = last_output_wav[0]
        if not path or not Path(path).exists():
            messagebox.showerror("No file", "No generated output to play. Run Generate first.")
            return
        try:
            subprocess.Popen(["afplay", path], cwd=PROJECT_ROOT)
        except FileNotFoundError:
            try:
                subprocess.Popen(["ffplay", "-nodisp", "-autoexit", path], cwd=PROJECT_ROOT)
            except FileNotFoundError:
                messagebox.showerror("Playback", "Neither afplay (macOS) nor ffplay (ffmpeg) found.")

    def apply_preset(duration: int, style_name: str):
        duration_var.set(str(duration))
        style_var.set(style_name)

    top = tk.Frame(root, padx=10, pady=10)
    top.pack(fill=tk.X)

    tk.Label(top, text="Input file:", width=12, anchor=tk.W).grid(row=0, column=0, sticky=tk.W, pady=2)
    tk.Entry(top, textvariable=input_path, width=50).grid(row=0, column=1, padx=4, pady=2)
    tk.Button(top, text="Browse…", command=browse_input).grid(row=0, column=2, pady=2)

    tk.Label(top, text="Output path:", width=12, anchor=tk.W).grid(row=1, column=0, sticky=tk.W, pady=2)
    tk.Entry(top, textvariable=output_path, width=50).grid(row=1, column=1, padx=4, pady=2)
    tk.Button(top, text="Browse…", command=lambda: browse_output(is_dir=False)).grid(row=1, column=2, pady=2)

    tk.Label(top, text="Phrase library:", width=12, anchor=tk.W).grid(row=2, column=0, sticky=tk.W, pady=2)
    tk.Entry(top, textvariable=phrase_library, width=50).grid(row=2, column=1, padx=4, pady=2)
    tk.Button(top, text="Browse…", command=browse_phrase_lib).grid(row=2, column=2, pady=2)

    dur_frame = tk.Frame(top)
    dur_frame.grid(row=3, column=0, columnspan=3, sticky=tk.W, pady=4)
    tk.Label(dur_frame, text="Duration (s):").pack(side=tk.LEFT)
    tk.Entry(dur_frame, textvariable=duration_var, width=6).pack(side=tk.LEFT, padx=4)

    gen_frame = tk.LabelFrame(root, text="Generate", padx=10, pady=8)
    gen_frame.pack(fill=tk.X, padx=10, pady=6)
    g = gen_frame
    tk.Label(g, text="Raga:").grid(row=0, column=0, sticky=tk.W, padx=(0, 4))
    tk.OptionMenu(g, raga_var, "Yaman").grid(row=0, column=1, sticky=tk.W)
    tk.Label(g, text="Duration (s):").grid(row=0, column=2, sticky=tk.W, padx=(12, 4))
    tk.Entry(g, textvariable=duration_var, width=6).grid(row=0, column=3, sticky=tk.W)
    tk.Label(g, text="Style:").grid(row=0, column=4, sticky=tk.W, padx=(12, 4))
    style_menu = tk.OptionMenu(g, style_var, *styles_list)
    style_menu.grid(row=0, column=5, sticky=tk.W)
    tk.Label(g, text="Source:").grid(row=1, column=0, sticky=tk.W, padx=(0, 4), pady=(6, 0))
    tk.OptionMenu(g, source_var, "From library", "Generated").grid(row=1, column=1, sticky=tk.W, pady=(6, 0))
    pre = tk.Frame(g)
    pre.grid(row=2, column=0, columnspan=6, sticky=tk.W, pady=(8, 4))
    tk.Label(pre, text="Presets:").pack(side=tk.LEFT, padx=(0, 6))
    tk.Button(pre, text="30s lofi", command=lambda: apply_preset(30, "lofi")).pack(side=tk.LEFT, padx=2)
    tk.Button(pre, text="60s ambient", command=lambda: apply_preset(60, "ambient")).pack(side=tk.LEFT, padx=2)
    tk.Button(pre, text="90s calm", command=lambda: apply_preset(90, "calm")).pack(side=tk.LEFT, padx=2)
    tk.Button(pre, text="60s upbeat", command=lambda: apply_preset(60, "upbeat")).pack(side=tk.LEFT, padx=2)
    tk.Button(g, text="Generate", command=run_generate, width=12).grid(row=3, column=0, columnspan=2, pady=(6, 0))
    tk.Button(g, text="Play", command=play_last, width=10).grid(row=3, column=2, columnspan=2, pady=(6, 0), padx=(8, 0))

    btn_frame = tk.Frame(root, padx=10, pady=4)
    btn_frame.pack(fill=tk.X)
    tk.Button(btn_frame, text="Analyze", command=run_analyze, width=14).pack(side=tk.LEFT, padx=2)
    tk.Button(btn_frame, text="Extract phrases", command=run_extract, width=14).pack(side=tk.LEFT, padx=2)
    tk.Button(btn_frame, text="Assemble", command=run_assemble, width=14).pack(side=tk.LEFT, padx=2)
    tk.Button(btn_frame, text="Add production", command=run_production, width=14).pack(side=tk.LEFT, padx=2)
    tk.Button(btn_frame, text="Validate", command=run_validate, width=14).pack(side=tk.LEFT, padx=2)

    results = scrolledtext.ScrolledText(root, wrap=tk.WORD, font=("Consolas", 10), height=20)
    results.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
    results.tag_configure("header", font=("Consolas", 10, "bold"))
    results.tag_configure("exit", foreground="gray")

    status_var = tk.StringVar(value="Ready")
    tk.Label(root, textvariable=status_var, anchor=tk.W).pack(fill=tk.X, padx=10, pady=4)

    root.after(100, poll_log)
    root.mainloop()


if __name__ == "__main__":
    main()
