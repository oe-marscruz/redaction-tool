import pathlib
import shutil
import sys

def stage_spacy_model():
    """
    Extracts the installed en_core_web_sm model to the vendor directory
    for PyInstaller bundling.
    """
    try:
        import en_core_web_sm
    except ImportError:
        print("Error: en_core_web_sm not installed in the current environment.")
        sys.exit(1)

    src = pathlib.Path(en_core_web_sm.__file__).parent
    dst = pathlib.Path("vendor/en_core_web_sm")

    print(f"Staging spaCy model from {src} to {dst}...")

    dst.mkdir(parents=True, exist_ok=True)

    # Copy meta.json
    meta_src = src / "meta.json"
    meta_dst = dst / "meta.json"
    if meta_src.exists():
        shutil.copy2(meta_src, meta_dst)
        print(f"  Copied meta.json")
    else:
        print(f"  Warning: meta.json not found at {meta_src}")

    # Copy the model data directory
    model_dir_name = next((d.name for d in src.iterdir() if d.is_dir() and d.name.startswith("en_core_web_sm-")), None)
    
    if model_dir_name:
        model_src = src / model_dir_name
        model_dst = dst / model_dir_name
        shutil.copytree(model_src, model_dst, dirs_exist_ok=True)
        print(f"  Copied {model_dir_name}")
    else:
        print("Error: Could not find the model data directory (en_core_web_sm-*) in the package.")
        sys.exit(1)

    print("spaCy model successfully staged.")

if __name__ == "__main__":
    stage_spacy_model()