"""Experimental local desktop interface for Stasrift 1.0.1.

Run with: python desktop/stasrift_desktop.py
Requires the Stasrift CLI installed in the current Python environment.
Tkinter is included in many Python distributions but may need separate installation on Linux.
"""
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

class App:
    def __init__(self, root):
        self.root = root
        root.title("Stasrift Desktop — Prototype")
        root.geometry("850x600")
        self.old = tk.StringVar()
        self.new = tk.StringVar()
        self.contract = tk.StringVar()
        self.repo = tk.StringVar(value=str(Path.home()))
        self.status = tk.StringVar(value="Ready. All checks run locally.")
        frame = ttk.Frame(root, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Stasrift Desktop", font=("TkDefaultFont", 18, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Semantic contract verification • local prototype").pack(anchor="w", pady=(0, 12))
        for label, var, folder in [
            ("Contract", self.contract, False), ("Old contract", self.old, False),
            ("New contract", self.new, False), ("Repository", self.repo, True)
        ]:
            row = ttk.Frame(frame)
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=label, width=15).pack(side="left")
            ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True)
            ttk.Button(row, text="Browse", command=lambda v=var, f=folder: self.browse(v, f)).pack(side="left", padx=(8, 0))
        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=12)
        for label, args in [
            ("Validate", lambda: ["validate", "--contract", self.contract.get()]),
            ("Compare", lambda: ["diff", "--old", self.old.get(), "--new", self.new.get()]),
            ("Doctor", lambda: ["doctor", "--repo", self.repo.get()]),
        ]:
            ttk.Button(actions, text=label, command=lambda a=args: self.run(a())).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Save report", command=self.save).pack(side="right")
        ttk.Label(frame, textvariable=self.status).pack(anchor="w")
        output_frame = ttk.Frame(frame)
        output_frame.pack(fill="both", expand=True, pady=(8, 0))
        self.output = tk.Text(output_frame, wrap="word", state="disabled")
        scroll = ttk.Scrollbar(output_frame, command=self.output.yview)
        self.output.configure(yscrollcommand=scroll.set)
        self.output.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.last_report = ""

    def browse(self, var, folder):
        value = filedialog.askdirectory() if folder else filedialog.askopenfilename(filetypes=[("Contracts", "*.yaml *.yml *.json"), ("All files", "*")])
        if value:
            var.set(value)

    def run(self, args):
        if not all(args):
            messagebox.showerror("Missing input", "Select the required files or repository first.")
            return
        self.status.set("Running local check…")
        threading.Thread(target=self.worker, args=(args,), daemon=True).start()

    def worker(self, args):
        try:
            result = subprocess.run([sys.executable, "-c", "import sys; from stasrift.cli import main; sys.exit(main())", *args],
                                    capture_output=True, text=True, errors="replace",
                                    timeout=120, stdin=subprocess.DEVNULL)
            report = "Command: stasrift " + " ".join(args) + "\nExit code: " + str(result.returncode) + "\n\n" + result.stdout + result.stderr
            status = {0: "Completed (exit 0)", 1: "Compatibility warning (exit 1)", 2: "Invalid input (exit 2)"}.get(result.returncode, "Check completed")
        except (OSError, subprocess.TimeoutExpired) as exc:
            report, status = str(exc), "Unable to complete check"
        self.root.after(0, lambda: self.show(report, status))

    def show(self, report, status):
        self.last_report = report
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", report)
        self.output.configure(state="disabled")
        self.status.set(status)

    def save(self):
        if not self.last_report:
            messagebox.showinfo("No report", "Run a check first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text report", "*.txt")])
        if path:
            Path(path).write_text(self.last_report, encoding="utf-8")
            self.status.set("Report saved locally.")

if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
