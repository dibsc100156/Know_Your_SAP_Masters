#!/usr/bin/env python3
"""
install_deps.py — Install all SAP Masters backend dependencies.
=========================================================
Run this ONCE after cloning the repo, or whenever packages are missing.

Usage:
    python install_deps.py
    python install_deps.py --venv     # Install into .venv (default)
    python install_deps.py --system   # Install into system Python
"""

import sys
import subprocess
import os
import argparse

def get_pip_cmd(venv):
    """Get the pip command for the target Python environment."""
    if venv:
        if sys.platform == "win32":
            pip = os.path.join(venv, "Scripts", "pip.exe")
        else:
            pip = os.path.join(venv, "bin", "pip")
    else:
        pip = sys.executable + " -m pip"
    return pip


def install(packages, venv_path=None, upgrade=False):
    """Install a list of packages."""
    pip = get_pip_cmd(venv_path)
    cmd = [pip, "install", "--quiet"]
    if upgrade:
        cmd.append("--upgrade")
    cmd.extend(packages)
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode == 0


REQUIREMENTS = [
    # API Server
    "fastapi==0.110.0",
    "uvicorn[standard]==0.28.0",
    "pydantic==2.6.4",
    # Vector Stores
    "qdrant-client==1.9.0",
    "chromadb==0.4.24",
    # Embeddings
    "sentence-transformers==2.5.1",
    "torch==2.2.1",
    # Graph RAG
    "networkx==3.2.1",
]


def main():
    parser = argparse.ArgumentParser(description="Install SAP Masters backend dependencies")
    parser.add_argument("--venv", action="store_true", help="Install into .venv (default: check .venv first)")
    parser.add_argument("--system", action="store_true", help="Install into system Python")
    parser.add_argument("--upgrade", action="store_true", help="Upgrade existing packages")
    args = parser.parse_args()

    # Detect .venv
    script_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = script_dir
    venv_path = None

    if args.system:
        print("[INFO] Installing into system Python")
    else:
        # Check for .venv
        venv_scripts = os.path.join(backend_dir, ".venv", "Scripts")
        if os.path.exists(venv_scripts):
            venv_path = os.path.join(backend_dir, ".venv")
            print(f"[INFO] Found .venv at: {venv_path}")
        else:
            print("[WARN] No .venv found. Installing into system Python.")
            print("[WARN] To use a virtual environment, create one with:")
            print("       python -m venv .venv && .venv\\Scripts\\activate")

    pip_cmd = get_pip_cmd(venv_path)
    print(f"\nUsing pip: {pip_cmd}\n")

    print("=" * 60)
    print("  Installing SAP Masters Backend Dependencies")
    print("=" * 60)

    for pkg in REQUIREMENTS:
        print(f"\n[INSTALL] {pkg}")
        cmd = [pip_cmd, "install", "--quiet"]
        if args.upgrade:
            cmd.append("--upgrade")
        cmd.append(pkg)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"  ✓ OK")
            else:
                print(f"  ✗ FAILED: {result.stderr[:200]}")
        except Exception as e:
            print(f"  ✗ ERROR: {e}")

    print("\n" + "=" * 60)
    print("  Done!")
    print("=" * 60)
    print("\nNext steps:")
    print("  1. Seed vector stores: python seed_all.py")
    print("  2. Start backend:       python -m uvicorn app.main:app --reload")
    print("  3. Start frontend:     cd ../frontend && streamlit run app.py")
    print("\nOr use the quick-start script:  ./start.ps1  (Windows)")


if __name__ == "__main__":
    main()
