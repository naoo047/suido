"""python -m generator.build → _site/ を作る（GitHub Actions から）"""
from .water_site import build_site

if __name__ == "__main__":
    print(f"built {len(build_site())} pages")
